'use client'

import { useState, useEffect } from 'react'

interface FeedItem {
  user: string
  uid: string
  fund: string
  code: string
  action: string
  amount: string
  detail: string
  time: string
  price: string
  isBuy: boolean
}

function timeAgo(t: string) {
  if (!t) return ''
  try {
    const d = new Date(t.replace(' ', 'T'))
    const now = new Date()
    const diff = (now.getTime() - d.getTime()) / 1000
    if (diff < 60) return '刚刚'
    if (diff < 3600) return `${Math.floor(diff/60)}分钟前`
    if (diff < 86400) return `${Math.floor(diff/3600)}小时前`
    if (diff < 86400*7) return `${Math.floor(diff/86400)}天前`
    return d.toISOString().slice(0, 10)
  } catch { return t }
}

function parseAmount(s: string) {
  if (!s) return 0
  const n = parseFloat(String(s).replace(/[^\d.]/g, ''))
  return isNaN(n) ? 0 : n
}

export default function FeedPage() {
  const [items, setItems] = useState<FeedItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all')

  useEffect(() => {
    fetch('/api/feed').then(r => r.json()).then(d => {
      setItems(Array.isArray(d) ? d : [])
    }).finally(() => setLoading(false))
  }, [])

  const filtered = items.filter(it => {
    if (filter === 'all') return true
    return filter === 'buy' ? it.isBuy : !it.isBuy
  })

  const summary = {
    total: items.length,
    buys: items.filter(i => i.isBuy).length,
    sells: items.filter(i => !i.isBuy).length,
    buyAmount: items.filter(i => i.isBuy).reduce((s, i) => s + parseAmount(i.amount), 0),
    sellAmount: items.filter(i => !i.isBuy).reduce((s, i) => s + parseAmount(i.amount), 0),
    users: new Set(items.map(i => i.user)).size,
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载大佬动态...</div>

  return (
    <div>
      <div style={{ marginBottom: '16px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>大佬实时交易动态</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          来自 {summary.users} 位关注的大佬 · 共 {summary.total} 笔
        </span>
      </div>

      {/* 汇总卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        <div className="glass" style={{ padding: '14px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>总交易</div>
          <div style={{ fontSize: '22px', fontWeight: 700, marginTop: '4px' }}>{summary.total}</div>
        </div>
        <div className="glass" style={{ padding: '14px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>买入笔数</div>
          <div style={{ fontSize: '22px', fontWeight: 700, marginTop: '4px', color: 'var(--accent-red)' }}>{summary.buys}</div>
        </div>
        <div className="glass" style={{ padding: '14px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>卖出笔数</div>
          <div style={{ fontSize: '22px', fontWeight: 700, marginTop: '4px', color: 'var(--accent-green)' }}>{summary.sells}</div>
        </div>
        <div className="glass" style={{ padding: '14px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>买入金额</div>
          <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px', color: 'var(--accent-red)' }}>
            {summary.buyAmount > 0 ? `¥${(summary.buyAmount/10000).toFixed(1)}万` : '-'}
          </div>
        </div>
        <div className="glass" style={{ padding: '14px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>卖出金额</div>
          <div style={{ fontSize: '18px', fontWeight: 700, marginTop: '4px', color: 'var(--accent-green)' }}>
            {summary.sellAmount > 0 ? `¥${(summary.sellAmount/10000).toFixed(1)}万` : '-'}
          </div>
        </div>
      </div>

      {/* 筛选 */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        {([['all','全部'],['buy','买入'],['sell','卖出']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k as any)} style={{
            padding: '6px 14px', borderRadius: '8px', border: '1px solid var(--glass-border)',
            background: filter === k ? 'rgba(255,85,119,0.2)' : 'var(--bg-card)',
            color: filter === k ? 'var(--accent-red)' : 'var(--text-secondary)',
            cursor: 'pointer', fontSize: '13px', fontWeight: filter === k ? 600 : 400
          }}>{label}</button>
        ))}
      </div>

      {/* 列表 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {filtered.map((it, i) => {
          const amt = parseAmount(it.amount)
          return (
            <div key={i} className="glass" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
              {/* 大佬 */}
              <div style={{ minWidth: '90px' }}>
                <div style={{ fontSize: '13px', fontWeight: 600 }}>{it.user}</div>
                <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>{timeAgo(it.time)}</div>
              </div>

              {/* 方向 */}
              <div style={{
                minWidth: '50px', textAlign: 'center', padding: '4px 8px', borderRadius: '6px',
                background: it.isBuy ? 'rgba(255,85,119,0.15)' : 'rgba(0,168,120,0.15)',
                color: it.isBuy ? 'var(--accent-red)' : 'var(--accent-green)',
                fontSize: '12px', fontWeight: 600
              }}>{it.isBuy ? '买入' : '卖出'}</div>

              {/* 基金 */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '14px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {it.fund}
                </div>
                {it.code && (
                  <a href={`/fund/${it.code}`} style={{ fontSize: '11px', color: 'var(--accent-blue)' }}>
                    {it.code} →
                  </a>
                )}
              </div>

              {/* 金额 */}
              <div style={{ textAlign: 'right' }}>
                {amt > 0 && (
                  <div style={{ fontSize: '14px', fontWeight: 600, color: it.isBuy ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    ¥{amt >= 10000 ? (amt/10000).toFixed(1) + '万' : amt.toFixed(0)}
                  </div>
                )}
                {it.price && (
                  <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>净值 {it.price}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          没有匹配的交易记录
        </div>
      )}
    </div>
  )
}
