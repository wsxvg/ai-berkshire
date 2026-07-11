'use client'

import { useState, useEffect } from 'react'
import { fetchWatchlist, fetchScores, FundInfo, FundScore } from './lib/jd-api'

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = value / 5 * 100
  const color = value >= 4 ? '#00d4aa' : value >= 3 ? '#5b8def' : value >= 2 ? '#f0b90b' : '#ff5577'
  return (
    <div style={{ marginBottom: '4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '2px' }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ color }}>{value.toFixed(1)}</span>
      </div>
      <div className="score-bar">
        <div className="score-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

function FundCard({ fund, score }: { fund: FundInfo; score?: FundScore }) {
  const dayRet = fund.dayReturn ?? 0
  const up = dayRet >= 0
  const color = up ? 'var(--accent-red)' : 'var(--accent-green)'
  const blocked = score?.blocked

  return (
    <div className="glass" style={{
      padding: '16px', opacity: blocked ? 0.6 : 1, cursor: 'pointer',
      borderColor: blocked ? 'rgba(255,85,119,0.4)' : undefined,
    }} onClick={() => window.location.href = `/fund/${fund.code}`}>
      {/* header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '4px' }}>
            {fund.name}
            {blocked && <span style={{ marginLeft: '8px', fontSize: '12px', color: 'var(--accent-red)' }}>⚠ {score?.blockReason}</span>}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{fund.code} · {fund.fundType}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '20px', fontWeight: 700 }}>{fund.nav}</div>
          <div style={{ fontSize: '14px', fontWeight: 600, color }}>
            {dayRet >= 0 ? '+' : ''}{dayRet.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* returns row */}
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: score ? '12px' : '0' }}>
        <span>周 {(fund.weekReturn ?? 0) >= 0 ? '+' : ''}{(fund.weekReturn ?? 0).toFixed(1)}%</span>
        <span>月 {(fund.monthReturn ?? 0) >= 0 ? '+' : ''}{(fund.monthReturn ?? 0).toFixed(1)}%</span>
        <span>年 {(fund.yearReturn ?? 0) >= 0 ? '+' : ''}{(fund.yearReturn ?? 0).toFixed(1)}%</span>
        <span>自选盈亏 {(fund.totalPnl ?? 0) >= 0 ? '+' : ''}{(fund.totalPnl ?? 0)?.toFixed(1)}%</span>
      </div>

      {/* score section */}
      {score && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>综合评分</span>
            <span style={{ fontSize: '18px', fontWeight: 700, color: score.total >= 3 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
              {score.total.toFixed(1)}<span style={{ fontSize: '12px' }}>/5.0</span>
            </span>
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
        </>
      )}
    </div>
  )
}

export default function Home() {
  const [funds, setFunds] = useState<FundInfo[]>([])
  const [scores, setScores] = useState<Record<string, FundScore>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [scoring, setScoring] = useState(false)

  useEffect(() => {
    fetchWatchlist()
      .then(setFunds)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const loadScores = async () => {
    if (funds.length === 0) return
    setScoring(true)
    try {
      const codes = funds.map(f => f.code).join(',')
      const data = await fetchScores(codes)
      const map: Record<string, FundScore> = {}
      data.forEach(s => { map[s.code] = s })
      setScores(map)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setScoring(false)
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载中...</div>
  if (error) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--accent-red)' }}>错误: {error}</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '24px', fontWeight: 700 }}>自选基金</h2>
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>{funds.length} 只 · 实时数据来自京东金融</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={loadScores}
            disabled={scoring}
            style={{
              padding: '10px 24px', borderRadius: '12px', border: '1px solid var(--glass-border)',
              background: 'var(--bg-card)', color: 'var(--text-primary)', cursor: 'pointer',
              fontWeight: 600, fontSize: '14px',
            }}
          >
            {scoring ? '评分中...' : 'AI 评分'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
        {funds.map(f => (
          <FundCard key={f.code} fund={f} score={scores[f.code]} />
        ))}
      </div>
    </div>
  )
}
