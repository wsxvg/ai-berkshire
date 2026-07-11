'use client'

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'

interface RankItem {
  code: string
  name: string
  type: string
  r1m: number | null
  r3m: number | null
  r6m: number | null
  r1y: number | null
  r3y: number | null
  rSince: number
  sharpe: number
  maxdd: number
  vol: number
}

const SORT_OPTIONS = [
  { key: 'r1y', label: '近1年' },
  { key: 'r6m', label: '近6月' },
  { key: 'r3m', label: '近3月' },
  { key: 'r1m', label: '近1月' },
  { key: 'r3y', label: '近3年' },
  { key: 'rSince', label: '成立以来' },
  { key: 'sharpe', label: '夏普比率' },
  { key: 'maxdd', label: '最大回撤' },
]

export default function RankingPage() {
  const [items, setItems] = useState<RankItem[]>([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState('r1y')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  useEffect(() => {
    fetch('/api/ranking?limit=300').then(r => r.json()).then(d => {
      setItems(Array.isArray(d) ? d : [])
    }).finally(() => setLoading(false))
  }, [])

  const types = useMemo(() => {
    const set = new Set<string>()
    items.forEach(it => { if (it.type) set.add(it.type) })
    return Array.from(set).sort()
  }, [items])

  const filtered = useMemo(() => {
    let r = items
    if (search) {
      const q = search.toLowerCase()
      r = r.filter(it => it.name.toLowerCase().includes(q) || it.code.includes(q))
    }
    if (typeFilter) {
      r = r.filter(it => it.type === typeFilter)
    }
    r = [...r].sort((a, b) => {
      const va = (a as any)[sortBy] ?? -99999
      const vb = (b as any)[sortBy] ?? -99999
      return sortBy === 'maxdd' ? va - vb : vb - va
    })
    return r
  }, [items, sortBy, search, typeFilter])

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载全市场排行...</div>

  const fmt = (v: number | null | undefined) => {
    if (v == null) return <span style={{ color: 'var(--text-secondary)' }}>-</span>
    return <span style={{ color: v >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
      {v >= 0 ? '+' : ''}{v.toFixed(1)}%
    </span>
  }

  return (
    <div>
      <div style={{ marginBottom: '16px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>基金排行</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          {filtered.length} / {items.length} 只 · 基于京东金融净值数据
        </span>
      </div>

      {/* 搜索 + 筛选 */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <input
          type="text" placeholder="搜索基金名称或代码..." value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: 1, minWidth: '200px', padding: '8px 12px', borderRadius: '8px',
            border: '1px solid var(--glass-border)', background: 'var(--bg-card)',
            color: 'var(--text-primary)', fontSize: '14px'
          }}
        />
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--glass-border)',
            background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: '14px'
          }}>
          <option value="">全部类型</option>
          {types.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {/* 排序 */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {SORT_OPTIONS.map(k => (
          <button key={k.key} onClick={() => setSortBy(k.key)} style={{
            padding: '6px 14px', borderRadius: '8px', border: '1px solid var(--glass-border)',
            background: sortBy === k.key ? 'rgba(255,85,119,0.2)' : 'var(--bg-card)',
            color: sortBy === k.key ? 'var(--accent-red)' : 'var(--text-secondary)',
            cursor: 'pointer', fontSize: '13px', fontWeight: sortBy === k.key ? 600 : 400
          }}>{k.label}</button>
        ))}
      </div>

      <div className="glass" style={{ padding: '0', overflowX: 'auto' }}>
        <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse', minWidth: '900px' }}>
          <thead>
            <tr style={{ fontSize: '11px', color: 'var(--text-secondary)', textAlign: 'left', background: 'rgba(0,0,0,0.1)' }}>
              <th style={{ padding: '12px 8px', width: '40px' }}>#</th>
              <th style={{ padding: '12px 8px' }}>基金</th>
              <th style={{ padding: '12px 8px' }}>类型</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>近1月</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>近3月</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>近6月</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>近1年</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>近3年</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>成立以来</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>夏普</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>回撤</th>
              <th style={{ padding: '12px 8px', textAlign: 'right' }}>年化波动</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item, i) => (
              <tr key={item.code} onClick={() => window.location.href = `/fund/${item.code}`}
                style={{ borderTop: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer' }}>
                <td style={{ padding: '10px 8px', color: 'var(--text-secondary)', fontSize: '12px' }}>{i + 1}</td>
                <td style={{ padding: '10px 8px' }}>
                  <div style={{ fontWeight: 500 }}>{item.name}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>{item.code}</div>
                </td>
                <td style={{ padding: '10px 8px', fontSize: '11px', color: 'var(--text-secondary)' }}>{item.type || '-'}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{fmt(item.r1m)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{fmt(item.r3m)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{fmt(item.r6m)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>{fmt(item.r1y)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{fmt(item.r3y)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{fmt(item.rSince)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right' }}>{item.sharpe.toFixed(2)}</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: 'var(--accent-green)' }}>{item.maxdd.toFixed(1)}%</td>
                <td style={{ padding: '10px 8px', textAlign: 'right', color: 'var(--text-secondary)' }}>{item.vol.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          没有匹配的基金
        </div>
      )}
    </div>
  )
}
