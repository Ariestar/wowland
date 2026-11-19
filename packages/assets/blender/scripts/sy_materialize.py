"""Add UVs and shared PBR detail maps to the Shangyuan runtime materials.

Run after `sy_build.py` and `sy_generate_textures.py`:
    blender -b packages/assets/blender/shangyuan-lantern-night.blend \
        --python-exit-code 1 --python packages/assets/blender/scripts/sy_materialize.py

The source master stays geometry-only; this stage writes
`shangyuan-lantern-night-textured.blend` for `sy_export.py`.
"""

import json
import math
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
TEXTURE_DIR = ROOT / "textures"
MANIFEST_PATH = TEXTURE_DIR / "manifest.json"
OUTPUT_BLEND = ROOT / "shangyuan-lantern-night-textured.blend"
TEXTURE_SCALE_M = 2.5


def load_image(path):
    image = bpy.data.images.load(str(path), check_existing=True)
    image.filepath = str(path)
    return image


def principled_node(material):
    nodes = material.node_tree.nodes
    node = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if node is None:
        raise RuntimeError(f"no Principled BSDF in {material.name}")
    return node


def add_uvs(obj):
    if obj.data.uv_layers:
        return False
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    uv_layer = obj.data.uv_layers.active
    if not uv_layer:
        return False
    max_dim = max(obj.dimensions)
    repeat = max(1.0, max_dim / TEXTURE_SCALE_M)
    for loop_uv in uv_layer.data:
        loop_uv.uv = ((loop_uv.uv[0] - 0.5) * repeat + 0.5, (loop_uv.uv[1] - 0.5) * repeat + 0.5)
    return True


def set_texture(material, name, spec):
    base = load_image(TEXTURE_DIR / Path(spec["base_color"]).name)
    normal = load_image(TEXTURE_DIR / Path(spec["normal"]).name)
    base.colorspace_settings.name = "sRGB"
    normal.colorspace_settings.name = "Non-Color"

    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    for node in list(nodes):
        if node.type in {"TEX_IMAGE", "NORMAL_MAP"} and node.name.startswith("SY_"):
            nodes.remove(node)
    p = principled_node(material)
    base_node = nodes.new("ShaderNodeTexImage")
    base_node.name = f"SY_{name}_BaseColor"
    base_node.label = f"T_SY_{name}_BaseColor"
    base_node.image = base
    base_node.location = (-520, 240)
    links.new(base_node.outputs["Color"], p.inputs["Base Color"])
    if name in {"Paper", "Lantern"}:
        links.new(base_node.outputs["Color"], p.inputs["Emission Color"])

    normal_node = nodes.new("ShaderNodeTexImage")
    normal_node.name = f"SY_{name}_Normal"
    normal_node.label = f"T_SY_{name}_Normal"
    normal_node.image = normal
    normal_node.location = (-520, -80)
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.name = f"SY_{name}_NormalMap"
    normal_map.inputs["Strength"].default_value = 0.65
    normal_map.location = (-260, -80)
    links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], p.inputs["Normal"])
    material["texture_set"] = f"T_SY_{name}"


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    textures = manifest["materials"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    added_uvs = 0
    for obj in meshes:
        try:
            if add_uvs(obj):
                added_uvs += 1
        except Exception as exc:
            print("SY_UV_WARNING", obj.name, repr(exc))
    textured = 0
    for name, spec in textures.items():
        material = bpy.data.materials.get(f"SY_{name}")
        if material is None:
            print("SY_MATERIAL_MISSING", name)
            continue
        set_texture(material, name, spec)
        textured += 1
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
    print(
        "SY_MATERIALIZE_OK",
        json.dumps(
            {"meshes": len(meshes), "added_uvs": added_uvs, "materials": textured,
             "texture_size": manifest["size"], "output": str(OUTPUT_BLEND)},
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
