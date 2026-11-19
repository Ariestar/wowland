import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'
import './globals.css'

export const metadata: Metadata = {
  title: '上元灯夜',
  description: '一个可以走进去的宋代水城上元灯会：领灯、猜谜、放河灯，看一场灯会。',
  icons: { icon: '/favicon.svg' },
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#0d1020',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
