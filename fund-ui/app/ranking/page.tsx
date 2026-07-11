'use client'

import { useState, useEffect } from 'react'

interface RankItem {
  code: string; name: string; nav: string; day: number | null
  week: number | null; month: number | null; y1: number | null
  y3: number | null; sharpe: number | null; maxdd: number | null
}

export default function RankingPage() {
  const [items, setItems] = useState<RankItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/ranking').then(r => r.json()).then(setItems).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载全市场排行...</div>

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>全市场基金排行</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>近1年收益 TOP 20</span>
      </div>
      <div className="glass" style={{ padding: '16px', overflowX: 'auto' }}>
        <table style={{ width: '100%', fontSize: '14px', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'left' }}>
              <th style={{ padding: '8px', width: '40px' }}>#</th>
              <th style={{ padding: '8px' }}>基金名称</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>净值</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>日涨跌</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近1月</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近1年</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近3年</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>夏普</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={item.code || i} style={{ borderTop: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer' }}
                onClick={() => window.location.href = `/fund/${item.code}`}>
                <td style={{ padding: '10px 8px', color: 'var(--text-secondary)' }}>{i + 1}</td>
                <td style={{ padding: '10px 8px' }}>
                  {item.name || item.code}
                  <span style={{ color: 'var(--text-secondary)', fontSize: '12px', marginLeft: '8px' }}>{item.code}</span>
                </td>
                <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>{item.nav || '-'}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: (item.day ?? 0) >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                  {(item.day ?? 0) >= 0 ? '+' : ''}{item.day?.toFixed(2) ?? '-'}%
                </td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{item.month != null ? `${item.month >= 0 ? '+' : ''}${item.month.toFixed(1)}%` : '-'}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: 'var(--accent-red)' }}>
                  {item.y1 != null ? `${item.y1 >= 0 ? '+' : ''}${item.y1.toFixed(1)}%` : '-'}
                </td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{item.y3 != null ? `${item.y3 >= 0 ? '+' : ''}${item.y3.toFixed(1)}%` : '-'}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{item.sharpe?.toFixed(2) ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-secondary)' }}>暂无排行数据（需Cookie连接京东API）</div>}
      </div>
    </div>
  )
}
