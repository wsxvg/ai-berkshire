import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'AI Berkshire Fund',
  description: '智能基金评分 + 大佬信号追踪 + GitHub Actions 日报',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body>
        <nav style={{
          position: 'sticky', top: 0, zIndex: 100,
          backdropFilter: 'blur(20px)',
          borderBottom: '1px solid rgba(100,140,255,0.15)',
          padding: '12px 24px',
          display: 'flex', alignItems: 'center', gap: '24px',
        }}>
          <h1 style={{ fontSize: '20px', fontWeight: 700 }}>
            <span className="gold">AI</span> Berkshire Fund
          </h1>
          <a href="/" style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>首页</a>
          <a href="/ranking" style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>排行</a>
          <a href="/dca" style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>定投</a>
          <a href="/backtest" style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>回测</a>
          <a href="/report" style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>日报</a>
          <a href="https://github.com/wsxvg/ai-berkshire" target="_blank"
             style={{ color: 'var(--text-secondary)', fontSize: '14px', marginLeft: 'auto' }}>
            GitHub
          </a>
        </nav>
        <main style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
          {children}
        </main>
      </body>
    </html>
  )
}
