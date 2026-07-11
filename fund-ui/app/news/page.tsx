'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

interface NewsItem {
  author: string
  time: string
  headline: string
  content_id: string
  url: string
}

export default function NewsPage() {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [date, setDate] = useState('')

  useEffect(() => {
    fetch('/api/news')
      .then(r => r.json())
      .then(d => {
        if (d.error) setError(d.error)
        else {
          setItems(d.items || [])
          setDate(d.date)
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载资讯...</div>

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>每日基金资讯</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          {date} · {items.length} 条 · 来自京东金融官方
        </span>
      </div>

      {error && (
        <div className="glass" style={{ padding: '16px', marginBottom: '16px', color: 'var(--accent-red)', fontSize: '13px' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {items.map((item, i) => (
          <a key={i} href={item.url || '#'} target="_blank" rel="noopener noreferrer"
             className="glass" style={{ padding: '16px', textDecoration: 'none', display: 'block' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
              <span style={{
                fontSize: '12px', padding: '2px 8px', borderRadius: '6px',
                background: 'rgba(255,85,119,0.15)', color: 'var(--accent-red)', fontWeight: 600
              }}>{item.author || '官方'}</span>
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{item.time}</span>
            </div>
            <div style={{ fontSize: '15px', lineHeight: 1.6, color: 'var(--text-primary)' }}>
              {item.headline}
            </div>
          </a>
        ))}
      </div>

      {items.length === 0 && !error && (
        <div className="glass" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          暂无资讯
        </div>
      )}
    </div>
  )
}
