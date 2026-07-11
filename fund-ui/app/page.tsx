'use client'

import { useState, useEffect } from 'react'
import { fetchWatchlist, fetchScores, FundInfo, FundScore } from './lib/jd-api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts'

const COLORS = ['#ff5577','#5b8def','#f0b90b','#00d4aa','#ff8c42','#a855f7','#ec4899','#14b8a6']

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = value / 5 * 100
  const color = value >= 4 ? '#ff5577' : value >= 3 ? '#5b8def' : value >= 2 ? '#f0b90b' : '#00d4aa'
  return (
    <div style={{ marginBottom: '4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '2px' }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ color }}>{value.toFixed(1)}</span>
      </div>
      <div className="score-bar"><div className="score-bar-fill" style={{ width: `${pct}%`, background: color }} /></div>
    </div>
  )
}

export default function Home() {
  const [funds, setFunds] = useState<FundInfo[]>([])
  const [scores, setScores] = useState<Record<string, FundScore>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [scoring, setScoring] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [compareData, setCompareData] = useState<any[]>([])
  const [comparing, setComparing] = useState(false)
  const [feed, setFeed] = useState<any[]>([])
  const [showRadar, setShowRadar] = useState<string | null>(null)

  useEffect(() => {
    fetchWatchlist().then(setFunds).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  const loadScores = async () => {
    if (funds.length === 0) return
    setScoring(true)
    try {
      const d = await fetchScores(funds.map(f => f.code).join(','))
      const m: Record<string, FundScore> = {}; d.forEach(s => { m[s.code] = s }); setScores(m)
    } catch (e: any) { setError(e.message) } finally { setScoring(false) }
  }

  const toggleSelect = (code: string) => {
    const n = new Set(selected)
    n.has(code) ? n.delete(code) : n.add(code)
    setSelected(n)
  }

  const [notices, setNotices] = useState<any[]>([])

  useEffect(() => { fetch('/api/feed').then(r => r.json()).then(setFeed).catch(()=>{}) }, [])

  useEffect(() => {
    if (funds.length === 0) return
    const codes = funds.map(f => f.code).slice(0, 50).join(',')
    fetch(`/api/notices?codes=${codes}`)
      .then(r => r.json())
      .then(d => setNotices(d.filter((n: any) => n.is_critical).slice(0, 5)))
      .catch(() => {})
  }, [funds])

  const radarData = (code: string) => {
    const s = scores[code]; if (!s) return []
    return [{dim:'质量',v:s.quality},{dim:'成本',v:s.cost},{dim:'经理',v:s.manager},{dim:'动量',v:s.momentum},{dim:'聪明钱',v:s.smartMoney}]
  }

  const loadCompare = async () => {
    const codes = Array.from(selected).join(',')
    if (!codes) return
    setComparing(true)
    try {
      const r = await fetch(`/api/compare?codes=${codes}`)
      setCompareData(await r.json())
    } catch (e: any) { setError(e.message) } finally { setComparing(false) }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载中...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '24px', fontWeight: 700 }}>自选基金</h2>
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>{funds.length} 只 · 实时数据来自京东金融</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {selected.size >= 2 && (
            <button onClick={loadCompare} disabled={comparing} style={{ padding: '10px 16px', borderRadius: '12px', border: '1px solid var(--glass-border)', background: 'var(--bg-card)', color: 'var(--accent-blue)', cursor: 'pointer', fontWeight: 600, fontSize: '14px' }}>
              {comparing ? '加载中...' : `对比 (${selected.size})`}
            </button>
          )}
          <button onClick={loadScores} disabled={scoring} style={{ padding: '10px 24px', borderRadius: '12px', border: '1px solid var(--glass-border)', background: 'var(--bg-card)', color: 'var(--text-primary)', cursor: 'pointer', fontWeight: 600, fontSize: '14px' }}>
            {scoring ? '评分中...' : 'AI 评分'}
          </button>
        </div>
      </div>

      {/* 对比图表 */}
      {compareData.length > 0 && (
        <div className="glass" style={{ padding: '16px', marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>净值曲线对比</h3>
            <button onClick={() => { setCompareData([]); setSelected(new Set()) }} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '14px' }}>关闭</button>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={compareData}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} tickFormatter={(d: string) => d.slice(5)} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} />
              <Tooltip contentStyle={{ background: 'rgba(15,20,40,0.9)', border: '1px solid var(--glass-border)', borderRadius: '8px' }} />
              <Legend />
              {Array.from(selected).map((c, i) => (
                <Line key={c} type="monotone" dataKey={c} stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={2} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 大佬动态 — 最近 10 笔 */}
      {feed.length > 0 && (
        <div className="glass" style={{ padding: '12px 16px', marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontWeight: 600, color: 'var(--accent-gold)' }}>大佬动态</span>
            <a href="/feed" style={{ fontSize: '12px', color: 'var(--accent-blue)' }}>查看全部 →</a>
          </div>
          <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', fontSize: '12px', alignItems: 'center' }}>
            {feed.slice(0, 12).map((f: any, i: number) => (
              <span key={i} title={`${f.user} ${f.action} ${f.fund} ${f.amount} (${f.time})`}
                style={{ whiteSpace: 'nowrap', padding: '4px 10px', borderRadius: '12px',
                  background: f.isBuy ? 'rgba(255,85,119,0.1)' : 'rgba(0,168,120,0.1)',
                  color: f.isBuy ? 'var(--accent-red)' : 'var(--accent-green)',
                  display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                <span style={{ color: 'var(--text-primary)', fontSize: '11px' }}>{f.user?.slice(0,4)}</span>
                <span>{f.isBuy ? '买入' : '卖出'}</span>
                <span style={{ color: 'var(--text-primary)' }}>{f.fund?.slice(0,10)}</span>
                {f.amt_num > 0 && <span style={{ fontSize: '10px', opacity: 0.8 }}>
                  ¥{f.amt_num >= 10000 ? Math.round(f.amt_num/10000)/10 + '万' : f.amt_num.toFixed(0)}
                </span>}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 公告警告 banner */}
      {notices.length > 0 && (
        <div style={{
          background: 'rgba(255, 85, 119, 0.08)', border: '1px solid rgba(255, 85, 119, 0.3)',
          borderRadius: '12px', padding: '12px 16px', marginBottom: '16px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '16px' }}>⚠️</span>
            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-red)' }}>
              关键公告 ({notices.length})
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {notices.map((n: any, i: number) => (
              <a key={i} href={n.url || '#'} target="_blank"
                style={{ fontSize: '12px', color: 'var(--text-primary)', textDecoration: 'none',
                  display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span style={{ padding: '1px 6px', background: 'rgba(255, 85, 119, 0.15)',
                  color: 'var(--accent-red)', borderRadius: '3px', fontSize: '10px', fontWeight: 600 }}>
                  {n.code}
                </span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {n.title}
                </span>
                {n.date && <span style={{ color: 'var(--text-secondary)', fontSize: '10px' }}>{n.date}</span>}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* radar chart modal */}
      {showRadar && scores[showRadar] && (
        <div className="glass" style={{ padding: '16px', marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{scores[showRadar].name} 五维雷达</h3>
            <button onClick={() => setShowRadar(null)} style={{ background:'none', border:'none', color:'var(--text-secondary)', cursor:'pointer' }}>关闭</button>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={radarData(showRadar)}>
              <PolarGrid stroke="rgba(255,255,255,0.1)" />
              <PolarAngleAxis dataKey="dim" tick={{ fontSize: 12, fill: 'var(--text-secondary)' }} />
              <PolarRadiusAxis domain={[0, 5]} tick={{ fontSize: 10 }} />
              <Radar name={scores[showRadar].name} dataKey="v" stroke="#ff5577" fill="#ff5577" fillOpacity={0.2} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* fund cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
        {funds.map(f => {
          const score = scores[f.code]
          const dayRet = f.dayReturn ?? 0
          const up = dayRet >= 0
          const blocked = score?.blocked
          const sel = selected.has(f.code)
          return (
            <div key={f.code} className="glass" style={{
              padding: '16px', opacity: blocked ? 0.6 : 1, cursor: 'pointer',
              borderColor: sel ? 'var(--accent-blue)' : blocked ? 'rgba(255,85,119,0.4)' : undefined,
              borderWidth: sel ? '2px' : '1px',
            }}>
              {/* checkbox + header */}
              <div style={{ display: 'flex', alignItems: 'start', gap: '8px', marginBottom: '8px' }}>
                <input type="checkbox" checked={sel} onChange={() => toggleSelect(f.code)}
                  style={{ marginTop: '3px', cursor: 'pointer' }} />
                <div style={{ flex: 1 }} onClick={() => window.location.href = `/fund/${f.code}`}>
                  <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '4px' }}>
                    {f.name}
                    {blocked && <span style={{ marginLeft: '8px', fontSize: '12px', color: 'var(--accent-green)' }}>⚠ {score?.blockReason}</span>}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{f.code} · {f.fundType}</div>
                </div>
                <div style={{ textAlign: 'right' }} onClick={() => window.location.href = `/fund/${f.code}`}>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>{f.nav}</div>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: up ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    {up ? '+' : ''}{dayRet.toFixed(2)}%
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: score ? '12px' : '0', paddingLeft: '24px' }}>
                <span>周 {(f.weekReturn ?? 0) >= 0 ? '+' : ''}{(f.weekReturn ?? 0).toFixed(1)}%</span>
                <span>月 {(f.monthReturn ?? 0) >= 0 ? '+' : ''}{(f.monthReturn ?? 0).toFixed(1)}%</span>
                <span>年 {(f.yearReturn ?? 0) >= 0 ? '+' : ''}{(f.yearReturn ?? 0).toFixed(1)}%</span>
              </div>
              {score && <div style={{ paddingLeft: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>综合评分</span>
                  <span style={{ fontSize: '18px', fontWeight: 700, color: score.total >= 3 ? 'var(--accent-red)' : 'var(--accent-green)' }}>{score.total.toFixed(1)}<span style={{ fontSize: '12px' }}>/5.0</span></span>
                </div>
                <ScoreBar label="质量" value={score.quality} />
                <ScoreBar label="动量" value={score.momentum} />
                <ScoreBar label="聪明钱" value={score.smartMoney} />
                <div style={{ display: 'flex', gap: '12px', marginTop: '8px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                  <span>4433: {score.pass4433}/2</span>
                  <span>RSI: {score.rsi ?? 'N/A'}</span>
                  <span>成本: {score.cost.toFixed(1)}</span>
                  <span>经理: {score.manager.toFixed(1)}</span>
                  <span onClick={(e) => { e.stopPropagation(); setShowRadar(f.code) }}
                    style={{ cursor: 'pointer', color: 'var(--accent-blue)', marginLeft: 'auto' }}>雷达图</span>
                </div>
              </div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
