"""Export the Lantern River lookdev scene as a web-ready static world GLB.

    blender -b exports/SM_Scene_LanternRiver_Night.blend --python scripts/export_web_world.py

The lookdev scene uses hundreds of linked kit instances plus small hand-built
props.  For the browser we bake those transforms into one mesh and collapse the
material slots, so the whole street costs roughly one draw call per material.
Water, sky and FX particles stay out of the GLB: the web scene builds those at
runtime.  The authored boats are exported with the world so their placement in
the level is the only placement the browser sees.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "web" / "world.glb"
DEFAULT_LAYOUT = ROOT / "web" / "layout.json"
TEXTURE_MANIFEST = ROOT / "textures" / "manifest.json"

# The kit was smart-unwrapped per piece, which packs each piece into 0..1.  That
# is right for an atlas but wrong for tiled detail: a 4 m facade and a 0.3 m
# bracket would get the same number of texels.  A second, world-scale box
# projection gives every material the same texel density in metres.
DETAIL_UV = "UVDetail"
DETAIL_TILE_METERS = 2.4

INCLUDE_COLLECTIONS = (
    "COL_Environment",
    "COL_Banks",
    "COL_Buildings",
    "COL_Landmarks",
    "COL_Props",
    "COL_Trees",
)

SKIP_NAMES = {
    "ENV_Water",
    "ENV_Underlay",
}


def collect_meshes() -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []
    for name in INCLUDE_COLLECTIONS:
        collection = bpy.data.collections.get(name)
        if collection is None:
            print("WEB_EXPORT_MISSING_COLLECTION", name)
            continue
        for obj in collection.all_objects:
            if obj.type != "MESH":
                continue
            if obj.name in SKIP_NAMES:
                continue
            if obj.name.startswith("FX_"):
                continue
            objects.append(obj)
    return objects


def flatten_procedural_base_colors() -> None:
    """glTF cannot carry Blender's brick/noise color graphs.

    The paving is the one material whose Base Color comes from a procedural
    brick node; without this it exports as pure white.  Give the exporter the
    brick's average colour instead.
    """
    material = bpy.data.materials.get("MAT_SCENE_Paving")
    if material is None or not material.use_nodes:
        return
    nodes = material.node_tree.nodes
    bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return
    socket = bsdf.inputs["Base Color"]
    for link in list(material.node_tree.links):
        if link.to_socket == socket:
            material.node_tree.links.remove(link)
    socket.default_value = (0.101, 0.096, 0.129, 1.0)


def _image_node(nt: bpy.types.NodeTree, path: Path, colorspace: str) -> bpy.types.ShaderNodeTexImage:
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = colorspace
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.extension = "REPEAT"
    node.interpolation = "Linear"
    return node


def wire_pbr_textures() -> int:
    """Connect the generated base colour, normal and roughness maps.

    glTF cannot carry Blender's procedural bump graphs.  These maps are the
    exported equivalent, wired through a second world-scale UV set so the
    texel density stays constant across the whole merged world.
    """
    if not TEXTURE_MANIFEST.exists():
        print("WEB_EXPORT_NO_TEXTURES", TEXTURE_MANIFEST)
        return 0
    manifest = json.loads(TEXTURE_MANIFEST.read_text(encoding="utf-8"))
    wired = 0
    for material_name, spec in manifest["materials"].items():
        material = bpy.data.materials.get(material_name)
        if material is None or not material.use_nodes:
            continue
        nt = material.node_tree
        bsdf = next((node for node in nt.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        for socket_name in ("Base Color", "Normal", "Roughness"):
            socket = bsdf.inputs[socket_name]
            for link in list(nt.links):
                if link.to_socket == socket:
                    nt.links.remove(link)

        uv = next((node for node in nt.nodes if node.type == "UVMAP" and node.uv_map == DETAIL_UV), None)
        if uv is None:
            uv = nt.nodes.new("ShaderNodeUVMap")
            uv.uv_map = DETAIL_UV

        # Fine-grained materials (bark) need a tighter repeat than the shared
        # 2.4 m detail tile, so each material can scale the shared UV.
        uv_out = uv.outputs["UV"]
        uv_scale = float(spec.get("uv_scale", 1.0))
        if uv_scale != 1.0:
            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (uv_scale, uv_scale, 1.0)
            nt.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
            uv_out = mapping.outputs["Vector"]

        base = _image_node(nt, ROOT / spec["base_color"], "sRGB")
        nt.links.new(uv_out, base.inputs["Vector"])
        nt.links.new(base.outputs["Color"], bsdf.inputs["Base Color"])

        normal_map = _image_node(nt, ROOT / spec["normal"], "Non-Color")
        normal_node = nt.nodes.new("ShaderNodeNormalMap")
        normal_node.inputs["Strength"].default_value = 1.0
        nt.links.new(uv_out, normal_map.inputs["Vector"])
        nt.links.new(normal_map.outputs["Color"], normal_node.inputs["Color"])
        nt.links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])

        rough_map = _image_node(nt, ROOT / spec["roughness"], "Non-Color")
        separate = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(uv_out, rough_map.inputs["Vector"])
        nt.links.new(rough_map.outputs["Color"], separate.inputs["Color"])
        nt.links.new(separate.outputs["Green"], bsdf.inputs["Roughness"])
        wired += 1
    print("WEB_EXPORT_TEXTURED_MATERIALS", wired)
    return wired


def add_detail_uv(obj: bpy.types.Object) -> None:
    mesh = obj.data
    existing = mesh.uv_layers.get(DETAIL_UV)
    if existing is not None:
        mesh.uv_layers.remove(existing)
    uv_layer = mesh.uv_layers.new(name=DETAIL_UV)
    mesh.uv_layers.active = uv_layer
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(
        cube_size=DETAIL_TILE_METERS,
        correct_aspect=True,
        scale_to_bounds=False,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    # Keep the authored atlas UV active for anyone opening the source mesh; the
    # texture nodes address UVDetail explicitly.
    base = mesh.uv_layers.get("UVMap")
    if base is not None:
        mesh.uv_layers.active = base


def dedupe_materials(obj: bpy.types.Object) -> None:
    old_slots = [slot.material for slot in obj.material_slots]
    unique: list[bpy.types.Material | None] = []
    lookup: dict[str, int] = {}
    remap: dict[int, int] = {}
    for index, material in enumerate(old_slots):
        key = material.name if material else ""
        if key not in lookup:
            lookup[key] = len(unique)
            unique.append(material)
        remap[index] = lookup[key]
    # Clearing the slot list resets every polygon to slot 0, so remember the
    # original indices and restore them after the new slot list exists.
    old_indices = [polygon.material_index for polygon in obj.data.polygons]
    obj.data.materials.clear()
    for material in unique:
        obj.data.materials.append(material)
    for polygon, old_index in zip(obj.data.polygons, old_indices):
        polygon.material_index = remap.get(old_index, 0)


def remove_material_geometry(obj: bpy.types.Object, material_names: set[str]) -> int:
    """Drop polygons whose material has been superseded by an official asset.

    The old alpha cards (blossom, shrub and willow) have dark borders.  The web
    scene places the official sakura, shrub and willow models instead, so
    exporting those cards would leave a second canopy with black frames around
    every leaf.  The old bark and trunk meshes are removed with them.
    """
    slots = [slot.material for slot in obj.material_slots]
    removed_slots = {
        index for index, material in enumerate(slots) if material and material.name in material_names
    }
    if not removed_slots:
        return 0

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    doomed = [face for face in bm.faces if face.material_index in removed_slots]
    for face in doomed:
        bmesh.ops.delete(bm, geom=[face], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()

    for index in sorted(removed_slots, reverse=True):
        obj.data.materials.pop(index=index)
        for polygon in obj.data.polygons:
            if polygon.material_index >= index:
                polygon.material_index -= 1
    return len(doomed)


def purge_unused_material_slots(obj: bpy.types.Object) -> int:
    """Remove material slots that no polygon uses.

    The glTF exporter writes every slot on the mesh, including slots left empty
    after superseded geometry is stripped.  Shipping those names in the GLB
    makes the asset look like it still contains the old tree cards, so drop the
    dead slots and shift the remaining polygon indices down with them.
    """
    used = {polygon.material_index for polygon in obj.data.polygons}
    removed = 0
    for index in range(len(obj.data.materials) - 1, -1, -1):
        if index in used:
            continue
        obj.data.materials.pop(index=index)
        for polygon in obj.data.polygons:
            if polygon.material_index > index:
                polygon.material_index -= 1
        removed += 1
    return removed


def cull_closed_shell_materials(world: bpy.types.Object) -> tuple[int, int]:
    """Enable backface culling only on materials that cover closed shells.

    A closed manifold shell never shows a back face from outside, so culling it
    is invisible while halving the fragments the merged world rasterises.  Open
    geometry (foliage cards, banners, roof shells) must stay double sided, so
    every material is judged by the faces that use it: a boundary or
    non-manifold edge makes all materials touching that edge unsafe.
    """
    slots = [slot.material for slot in world.material_slots]
    risky: set[int] = set()
    bm = bmesh.new()
    bm.from_mesh(world.data)
    for edge in bm.edges:
        faces = edge.link_faces
        if len(faces) == 2:
            continue
        for face in faces:
            risky.add(face.material_index)
    bm.free()

    culled = 0
    for index, material in enumerate(slots):
        if material is None or index in risky:
            continue
        material.use_backface_culling = True
        culled += 1
    print(
        "LR_WEB_BACKFACE_CULL",
        {"materials": len(slots), "culled": culled, "double_sided": len(slots) - culled},
    )
    return culled, len(slots) - culled


# ---------------------------------------------------------------------------
# Collision layout
# ---------------------------------------------------------------------------
#
# The browser used to hand-author walk rectangles that drifted away from the art.
# Here the exported scene is the single source of truth: walkable surfaces come
# from the actual ground, steps, plaza and bridge deck, and every solid prop
# contributes a footprint.  The runtime turns this into a ground sampler plus a
# circle-vs-box character controller.

PLAY_MIN_Y = -140.0
PLAY_MAX_Y = 180.0
BRIDGE_DECK_HALF_WIDTH = 2.95


def _corners(obj: bpy.types.Object) -> list[Vector]:
    return [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]


def _bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = _corners(obj)
    return (
        Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners))),
        Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners))),
    )


def _add_quad(tris: list[float], x0: float, y0: float, x1: float, y1: float, z: float) -> None:
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return
    tris.extend((x0, y0, z, x1, y0, z, x1, y1, z))
    tris.extend((x0, y0, z, x1, y1, z, x0, y1, z))


def _add_box_tris(tris: list[float], obj: bpy.types.Object) -> None:
    low, high = _bounds(obj)
    _add_quad(tris, low.x, low.y, high.x, high.y, high.z)


def _shop_facade_x(side: int) -> float | None:
    prefix = "BLD_R_" if side > 0 else "BLD_L_"
    edges: list[float] = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.name.startswith(prefix):
            continue
        low, high = _bounds(obj)
        edges.append(low.x if side > 0 else high.x)
    if not edges:
        return None
    return min(edges) if side > 0 else max(edges)


def _bridge_triangle_soup(bridge: bpy.types.Object) -> list[float]:
    mesh = bridge.data
    mesh.calc_loop_triangles()
    matrix = bridge.matrix_world
    normal_matrix = matrix.to_3x3()
    low, high = _bounds(bridge)
    center_y = (low.y + high.y) * 0.5
    soup: list[float] = []
    for tri in mesh.loop_triangles:
        normal = (normal_matrix @ tri.normal).normalized()
        if normal.z < 0.45:
            continue
        points = [matrix @ mesh.vertices[index].co for index in tri.vertices]
        cy = sum(point.y for point in points) / 3.0
        cz = sum(point.z for point in points) / 3.0
        # The bridge also has handrails, lantern hooks and roof caps.  Keep the
        # walking band narrow and low enough that only the deck and its steps
        # become ground.
        if abs(cy - center_y) > BRIDGE_DECK_HALF_WIDTH or cz < 0.7 or cz > 6.5:
            continue
        for point in points:
            soup.extend((point.x, point.y, point.z))
    return soup


def build_layout() -> dict:
    tris: list[float] = []
    obstacles: list[dict] = []

    # Read the walking height from the authored ground slab instead of repeating
    # the constant in TypeScript.
    ground_obj = bpy.data.objects["ENV_Ground_1"]
    ground_z = max((ground_obj.matrix_world @ Vector(c)).z for c in ground_obj.bound_box)

    # The water plane is authored at the canal width, so the runtime can derive
    # the bank line, the water shader's bank glow and the spawn from the scene.
    water = bpy.data.objects.get("ENV_Water")
    river_half = (water.dimensions.x * 0.5) if water is not None else 18.0

    right_facade = _shop_facade_x(1)
    left_facade = _shop_facade_x(-1)
    right_edge = (right_facade - 0.05) if right_facade is not None else 23.0
    left_edge = (left_facade + 0.05) if left_facade is not None else -23.0
    quay_outer = max(abs(right_edge), abs(left_edge))

    # Spawn in the middle of the promenade, not against a wall.
    spawn_x = (river_half + right_edge) * 0.5 if right_facade is not None else 16.4

    # The visible bank slabs are the walkable ground.  Exporting the authored
    # slab instead of a hand-picked strip means the player can use the whole
    # paved street, the plaza approach and the backlots the buildings leave
    # open; the buildings themselves supply the obstructions.
    for side in (-1, 1):
        ground = bpy.data.objects.get(f"ENV_Ground_{side}")
        if ground is None:
            continue
        low, high = _bounds(ground)
        _add_quad(tris, low.x, PLAY_MIN_Y, high.x, PLAY_MAX_Y, ground_z)

    # Quay coping is a 12 cm step at the water edge; its top is a real surface.
    for side in (-1, 1):
        coping = bpy.data.objects.get(f"ENV_QuayCoping_{side}")
        if coping is None:
            continue
        low, high = _bounds(coping)
        _add_quad(tris, low.x, low.y, high.x, high.y, high.z)

    # Pavilion square and its low step: these are real paved surfaces, not
    # decoration, so they are walkable.
    for name in ("ENV_PavilionPlaza", "ENV_PlazaStep_0", "ENV_PlazaStep_1", "ENV_PlazaStep_2"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            _add_box_tris(tris, obj)

    # Stairs into the water at each ferry point.
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name.startswith("ENV_WaterStep_"):
            _add_box_tris(tris, obj)

    # The bridge deck is curved; use its own upward faces so the player's eye
    # follows the arch exactly.
    bridge = bpy.data.objects.get("LM_Bridge_Arch")
    bridge_bounds: tuple[Vector, Vector] | None = None
    if bridge is not None:
        bridge_bounds = _bounds(bridge)
        tris.extend(_bridge_triangle_soup(bridge))

    def body_bounds(obj: bpy.types.Object, height: float = 2.2) -> tuple[Vector, Vector]:
        """Footprint of the geometry a person actually walks into.

        The object bounding box includes roof eaves and canopy overhangs.  Those
        are passable underneath, so only vertices below `height` above the base
        contribute to the blocker.
        """
        low, high = _bounds(obj)
        if high.z - low.z <= height:
            return low, high
        matrix = obj.matrix_world
        xs: list[float] = []
        ys: list[float] = []
        ceiling = low.z + height
        for vertex in obj.data.vertices:
            point = matrix @ vertex.co
            if point.z <= ceiling:
                xs.append(point.x)
                ys.append(point.y)
        if not xs:
            return low, high
        return (
            Vector((min(xs), min(ys), low.z)),
            Vector((max(xs), max(ys), high.z)),
        )

    def add_obstacle(
        name: str,
        obj: bpy.types.Object,
        shrink: float,
        kind: str,
        body_height: float | None = 2.2,
    ) -> None:
        low, high = body_bounds(obj, body_height) if body_height is not None else _bounds(obj)
        half_x = (high.x - low.x) * 0.5 - shrink
        half_y = (high.y - low.y) * 0.5 - shrink
        if half_x <= 0.02 or half_y <= 0.02:
            return
        obstacles.append(
            {
                "name": name,
                "kind": kind,
                "x": round((low.x + high.x) * 0.5, 3),
                "y": round((low.y + high.y) * 0.5, 3),
                "hx": round(half_x, 3),
                "hy": round(half_y, 3),
                "top": round(high.z, 3),
                "rot": 0.0,
            }
        )

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        name = obj.name
        if name.startswith("BLD_"):
            add_obstacle(name, obj, 0.05, "building")
        elif name.startswith("PROP_Stall_"):
            add_obstacle(name, obj, 0.05, "stall")
        elif name.startswith(("PROP_CherryTree_", "PROP_WillowTree_")) and name.endswith("_Trunk"):
            add_obstacle(name, obj, 0.02, "tree")
        elif name.startswith("PROP_QuayPost_"):
            add_obstacle(name, obj, 0.0, "post")
        elif name.startswith("PROP_PalaceLantern_"):
            add_obstacle(name, obj, 0.05, "lantern")
        elif name.startswith("PROP_PerformanceStage"):
            add_obstacle(name, obj, 0.05, "stage")
        elif name.startswith("PROP_TeaCart_") and name.endswith("_Body"):
            add_obstacle(name, obj, 0.05, "cart")
        elif name.startswith("PROP_LanternRack_") and "_Post_" in name:
            add_obstacle(name, obj, 0.0, "post")
        elif name.startswith("PROP_StoneLantern_") and name.endswith("_Base"):
            add_obstacle(name, obj, 0.0, "post")
        elif name.startswith("PROP_ApproachPole_"):
            add_obstacle(name, obj, 0.0, "post")
        elif name == "LM_Paifang":
            # A gate is mostly open space: block only the columns, never the
            # whole bounding box, or the street entrance becomes a wall.
            matrix = obj.matrix_world
            points = [matrix @ vertex.co for vertex in obj.data.vertices]
            floor = min(point.z for point in points)
            columns = [point for point in points if point.z <= floor + 1.4]
            low, high = _bounds(obj)
            # The gate is rotated 90° at the entrance, so choose the axis the
            # columns are spread along instead of assuming X.
            axis = 0 if high.x - low.x >= high.y - low.y else 1
            columns.sort(key=lambda point: (point.x, point.y)[axis])
            groups: list[list[Vector]] = []
            last: float | None = None
            for point in columns:
                value = (point.x, point.y)[axis]
                if last is None or value - last > 0.2:
                    groups.append([point])
                else:
                    groups[-1].append(point)
                last = value
            top = max(point.z for point in points)
            for index, group in enumerate(groups):
                x0 = min(point.x for point in group)
                x1 = max(point.x for point in group)
                y0 = min(point.y for point in group)
                y1 = max(point.y for point in group)
                obstacles.append(
                    {
                        "name": f"LM_Paifang_Column_{index}",
                        "kind": "post",
                        "x": round((x0 + x1) * 0.5, 3),
                        "y": round((y0 + y1) * 0.5, 3),
                        "hx": round((x1 - x0) * 0.5, 3),
                        "hy": round((y1 - y0) * 0.5, 3),
                        "top": round(top, 3),
                        "rot": 0.0,
                    }
                )
        elif name == "LM_Pavilion_Hex":
            # The pavilion is open; block its core and let visitors walk the
            # surrounding square instead of an invisible 9 m cube.
            add_obstacle(name, obj, 1.8, "pavilion", body_height=None)

    # Bridge parapets: the deck is walkable, the handrails are not.  Follow the
    # arch with short boxes so the edge reads as solid on both sides.
    if bridge_bounds is not None:
        low, high = bridge_bounds
        center_y = (low.y + high.y) * 0.5
        segments = 18
        span = high.x - low.x
        for side in (-1.0, 1.0):
            for index in range(segments):
                x0 = low.x + (span * index) / segments
                x1 = low.x + (span * (index + 1)) / segments
                obstacles.append(
                    {
                        "name": f"LM_Bridge_Rail_{int(side)}_{index}",
                        "kind": "rail",
                        "x": round((x0 + x1) * 0.5, 3),
                        "y": round(center_y + side * 3.15, 3),
                        "hx": round((x1 - x0) * 0.5 + 0.08, 3),
                        "hy": 0.24,
                        "top": round(high.z, 3),
                        "rot": 0.0,
                    }
                )

    xs = [tris[i] for i in range(0, len(tris), 3)]
    ys = [tris[i + 1] for i in range(0, len(tris), 3)]
    zs = [tris[i + 2] for i in range(0, len(tris), 3)]
    bridge_meta = {"y": 10.0, "halfSpan": 23.6}
    if bridge_bounds is not None:
        bridge_meta = {
            "y": round((bridge_bounds[0].y + bridge_bounds[1].y) * 0.5, 3),
            "halfSpan": round((bridge_bounds[1].x - bridge_bounds[0].x) * 0.5, 3),
        }
    return {
        "version": 1,
        "units": "meters",
        "axes": "blender_xy_z_up",
        "description": "Walkable triangle soup and solid footprints exported from the Blender scene.",
        "groundZ": round(ground_z, 3),
        "riverHalf": round(river_half, 3),
        "quayInner": round(river_half, 3),
        "quayOuter": round(quay_outer, 3),
        "bridge": bridge_meta,
        "spawn": {"x": round(spawn_x, 3), "y": -132.0},
        "bounds": {
            "minX": round(min(xs), 3),
            "maxX": round(max(xs), 3),
            "minY": round(min(ys), 3),
            "maxY": round(max(ys), 3),
            "minZ": round(min(zs), 3),
            "maxZ": round(max(zs), 3),
        },
        "walkable": [round(value, 3) for value in tris],
        "obstacles": obstacles,
    }


def force_alpha_mask(path: Path, suffixes: tuple[str, ...]) -> int:
    """Rewrite alpha-cutout materials to glTF MASK.

    Blender 5.3 no longer honours `blend_method`, so every material with a
    linked alpha exports as alphaMode BLEND.  For foliage cards that is wrong:
    BLEND disables depth writes and hundreds of overlapping quads sort against
    each other.  Patch the JSON chunk instead of fighting the exporter.
    """
    data = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", data, 0)
    chunks: list[tuple[int, bytes]] = []
    offset = 12
    while offset < total:
        length, kind = struct.unpack_from("<II", data, offset)
        chunks.append((kind, data[offset + 8: offset + 8 + length]))
        offset += 8 + length

    patched = 0
    rebuilt = []
    for kind, payload in chunks:
        if kind == 0x4E4F534A:  # 'JSON'
            doc = json.loads(payload.decode("utf-8"))
            for material in doc.get("materials", []):
                if any(material.get("name", "").endswith(s) for s in suffixes):
                    material["alphaMode"] = "MASK"
                    material["alphaCutoff"] = 0.45
                    patched += 1
            payload = json.dumps(doc, separators=(",", ":")).encode("utf-8")
            payload += b" " * ((4 - len(payload) % 4) % 4)
        else:
            payload += b"\x00" * ((4 - len(payload) % 4) % 4)
        rebuilt.append((kind, payload))

    body = b"".join(struct.pack("<II", len(p), k) + p for k, p in rebuilt)
    path.write_bytes(struct.pack("<III", magic, version, 12 + len(body)) + body)
    print("LR_WEB_ALPHA_MASK", patched)
    return patched


def export_layout(path: Path) -> dict:
    layout = build_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(layout, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        "LR_WEB_LAYOUT_OK",
        {
            "triangles": len(layout["walkable"]) // 9,
            "obstacles": len(layout["obstacles"]),
            "bytes": path.stat().st_size,
            "path": str(path),
        },
    )
    return layout


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--layout", default=str(DEFAULT_LAYOUT))
    parser.add_argument("--draco", action="store_true")
    args = parser.parse_args(argv)

    flatten_procedural_base_colors()
    textured = wire_pbr_textures()

    objects = collect_meshes()
    if not objects:
        raise RuntimeError("no meshes found in the lookdev scene")

    # The collision layout is built from the unjoined scene; joining flattens
    # the very object names and bounds this data depends on.
    export_layout(Path(args.layout))

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]

    bpy.ops.object.join()
    world = bpy.context.object
    world.name = "LanternRiver_World"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    add_detail_uv(world)
    removed_legacy_faces = remove_material_geometry(
        world,
        {
            "MAT_SCENE_BlossomCard",
            "MAT_SCENE_Bark",
            "MAT_SCENE_Trunk",
            "MAT_SCENE_ShrubCard",
            "MAT_SCENE_WillowCard",
        },
    )
    dedupe_materials(world)
    removed_material_slots = purge_unused_material_slots(world)
    culled, double_sided = cull_closed_shell_materials(world)

    world.data.calc_loop_triangles()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_draco_mesh_compression_enable=args.draco,
        export_draco_mesh_compression_level=6,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=10,
        export_draco_texcoord_quantization=12,
    )
    force_alpha_mask(out, ("Card",))
    print(
        "LR_WEB_WORLD_OK",
        {
            "objects_merged": len(objects),
            "removed_legacy_faces": removed_legacy_faces,
            "removed_material_slots": removed_material_slots,
            "triangles": len(world.data.loop_triangles),
            "materials": len(world.data.materials),
            "culled_materials": culled,
            "double_sided_materials": double_sided,
            "textured_materials": textured,
            "images": len({image.name for image in bpy.data.images if image.users}),
            "bytes": out.stat().st_size,
            "path": str(out),
        },
    )


if __name__ == "__main__":
    main()
