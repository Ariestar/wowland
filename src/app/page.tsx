import type { Metadata } from 'next'
import ShangyuanWorld from '@/components/ShangyuanWorld'

type PageProps = { searchParams: Promise<{ lang?: string }> }

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { lang } = await searchParams
  return lang === 'en'
    ? {
        title: 'Shangyuan Lantern Night',
        description: 'A walkable Song-dynasty water town at the lantern festival, built for the Web preview.',
        robots: { index: false, follow: false },
      }
    : {
        title: '上元灯夜',
        description: '一个可以走进去的宋代水城上元灯会：领灯、猜谜、放河灯，看一场灯会。',
        robots: { index: false, follow: false },
      }
}

export default async function ShangyuanPage({ searchParams }: PageProps) {
  const { lang } = await searchParams
  return <ShangyuanWorld language={lang === 'en' ? 'en' : 'zh'} />
}
