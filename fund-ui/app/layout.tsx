import './globals.css'
import type { Metadata } from 'next'
import { NavClient } from './nav-client'

export const metadata: Metadata = {
  title: 'AI Berkshire Fund',
  description: '智能基金评分 + 大佬信号追踪 + GitHub Actions 日报',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body>
        <NavClient />
        <main style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
          {children}
        </main>
      </body>
    </html>
  )
}
