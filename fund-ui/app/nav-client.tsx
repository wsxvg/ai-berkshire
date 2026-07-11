'use client'
import { useTheme } from './stores/theme'

export function NavClient() {
  const { dark, toggle } = useTheme()

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      backdropFilter: 'blur(20px)',
      borderBottom: '1px solid rgba(100,140,255,0.15)',
      padding: '12px 24px',
      display: 'flex', alignItems: 'center', gap: '20px',
      background: dark ? 'rgba(10,14,26,0.85)' : 'rgba(255,255,255,0.85)',
      color: dark ? '#e8ecf4' : '#1a1a2e',
    }}>
      <h1 style={{ fontSize: '20px', fontWeight: 700 }}>
        <span style={{ color: dark ? '#f0b90b' : '#d48b00' }}>AI</span> Berkshire Fund
      </h1>
      <a href="/" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>首页</a>
      <a href="/feed" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>动态</a>
      <a href="/news" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>资讯</a>
      <a href="/ranking" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>排行</a>
      <a href="/sector" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>行业</a>
      <a href="/dca" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>定投</a>
      <a href="/backtest" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>回测</a>
      <a href="/report" style={{ fontSize: '14px', color: dark ? '#8892b0' : '#666' }}>日报</a>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button onClick={toggle} style={{
          background: 'none', border: 'none', cursor: 'pointer', fontSize: '18px',
          color: dark ? '#8892b0' : '#666',
        }} title={dark ? '切换亮色' : '切换暗色'}>
          {dark ? '☀️' : '🌙'}
        </button>
        <a href="https://github.com/wsxvg/ai-berkshire" target="_blank"
          style={{ color: dark ? '#8892b0' : '#666', fontSize: '14px' }}>
          GitHub
        </a>
      </div>
    </nav>
  )
}
