'use client'

import { useState, useEffect } from 'react'

interface RankItem {
  code: string; name: string
  r1m: number | null; r3m: number | null; r6m: number | null; r1y: number | null
  sharpe: number; maxdd: number
}

export default function RankingPage() {
  const [items, setItems] = useState<RankItem[]>([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState('r1y')

  useEffect(() => {
    fetch('/api/ranking').then(r => r.json()).then(setItems).finally(() => setLoading(false))
  }, [])

  const sorted = [...items].sort((a, b) => {
    const va = (a as any)[sortBy] ?? -999
    const vb = (b as any)[sortBy] ?? -999
    return sortBy === 'maxdd' ? (va - vb) : (vb - va)
  })

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>计算全市场排行...</div>

  const fmt = (v: number | null | undefined) => {
    if (v == null) return '-'
    return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
  }

  const sortBtns = ['r1y','r6m','r3m','r1m','sharpe','maxdd']
  const sortLabels: Record<string,string> = {r1y:'近1年',r6m:'近6月',r3m:'近3月',r1m:'近1月',sharpe:'夏普',maxdd:'回撤'}

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>基金排行</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>{items.length} 只 · 基于京东金融净值数据自算</span>
      </div>
      {/* 排序 */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {sortBtns.map(k => (
          <button key={k} onClick={() => setSortBy(k)} style={{
            padding: '6px 14px', borderRadius: '8px', border: '1px solid var(--glass-border)',
            background: sortBy === k ? 'rgba(255,85,119,0.2)' : 'var(--bg-card)',
            color: sortBy === k ? 'var(--accent-red)' : 'var(--text-secondary)', cursor: 'pointer', fontSize: '13px'
          }}>{sortLabels[k]}</button>
        ))}
      </div>
      <div className="glass" style={{ padding: '16px', overflowX: 'auto' }}>
        <table style={{ width: '100%', fontSize: '14px', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'left' }}>
              <th style={{ padding: '8px', width: '36px' }}>#</th>
              <th style={{ padding: '8px' }}>基金名称</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近1月</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近3月</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近6月</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>近1年</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>夏普</th>
              <th style={{ padding: '8px', textAlign: 'right' }}>回撤</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((item, i) => (
              <tr key={item.code} onClick={() => window.location.href = `/fund/${item.code}`}
                style={{ borderTop: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer' }}>
                <td style={{ padding: '10px 8px', color: 'var(--text-secondary)', fontSize: '12px' }}>{i + 1}</td>
                <td style={{ padding: '10px 8px' }}>
                  {item.name}
                  <span style={{ color: 'var(--text-secondary)', fontSize: '11px', marginLeft: '6px' }}>{item.code}</span>
                </td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: (item.r1m ?? 0) >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>{fmt(item.r1m)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: (item.r3m ?? 0) >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>{fmt(item.r3m)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: (item.r6m ?? 0) >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>{fmt(item.r6m)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: (item.r1y ?? 0) >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>{fmt(item.r1y)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{item.sharpe.toFixed(2)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: 'var(--accent-green)' }}>{item.maxdd.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
