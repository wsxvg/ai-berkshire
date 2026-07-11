'use client'

import { useState, useEffect } from 'react'
import { fetchWatchlist, fetchScores, FundInfo, FundScore } from './lib/jd-api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

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
                </div>
              </div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
