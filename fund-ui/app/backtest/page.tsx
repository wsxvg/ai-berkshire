'use client'

import { useState, useEffect } from 'react'

interface BacktestResult {
  config?: any
  annualized?: number; total_return?: number; sharpe?: number
  max_drawdown?: number; calmar?: number; trade_count?: number
  benchmark?: number; final_value?: number; fees?: number
}

export default function BacktestPage() {
  const [data, setData] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [startDate, setStartDate] = useState('2024-03-11')
  const [endDate, setEndDate] = useState('2026-07-01')
  const [cash, setCash] = useState(100000)
  const [runResult, setRunResult] = useState<any>(null)

  useEffect(() => {
    fetch('/api/backtest').then(r => r.json()).then(setData).finally(() => setLoading(false))
  }, [])

  const runNow = async () => {
    setRunning(true); setRunResult(null)
    try {
      const r = await fetch('/api/run-backtest', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start: startDate, end: endDate, cash })
      })
      setRunResult(await r.json())
    } catch (e: any) { setRunResult({ error: e.message }) }
    finally { setRunning(false) }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载...</div>

  return (
    <div>
      <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>回测结果</h2>

      {/* 运行回测 */}
      <div className="glass" style={{ padding: '16px', marginBottom: '16px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>自定义回测</h3>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input value={startDate} onChange={e => setStartDate(e.target.value)} placeholder="开始日期" style={inpStyle} />
          <span>~</span>
          <input value={endDate} onChange={e => setEndDate(e.target.value)} placeholder="结束日期" style={inpStyle} />
          <input type="number" value={cash} onChange={e => setCash(Number(e.target.value))} placeholder="本金" style={{ ...inpStyle, width: '100px' }} />
          <button onClick={runNow} disabled={running} style={{ padding: '8px 16px', borderRadius: '8px', background: 'var(--accent-red)', border:'none', color:'#fff', cursor:'pointer', fontWeight:600 }}>
            {running ? '运行中...' : '运行回测'}
          </button>
        </div>
        {runResult && !runResult.error && (
          <div style={{ display: 'flex', gap: '12px', marginTop: '12px', flexWrap: 'wrap' }}>
            <Mini label="总收益" val={`${(runResult.total_return ?? 0) >= 0 ? '+' : ''}${runResult.total_return?.toFixed(1)}%`} />
            <Mini label="年化" val={`${runResult.annualized?.toFixed(1)}%`} />
            <Mini label="夏普" val={runResult.sharpe?.toFixed(2)} />
            <Mini label="回撤" val={`${runResult.max_drawdown?.toFixed(1)}%`} />
            <Mini label="交易" val={`${runResult.trade_count}笔`} />
            <Mini label="最终" val={`${(runResult.final_value ?? 0).toLocaleString()}元`} />
          </div>
        )}
        {runResult?.error && <div style={{ marginTop: '12px', color: 'var(--accent-green)' }}>错误: {runResult.error}</div>}
      </div>

      {/* 进化参数 */}
      {data && (
        <>
          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
            <Stat label="年化回报" value={`${data.annualized?.toFixed(1) ?? '?'}%`} color="var(--accent-red)" />
            <Stat label="总收益" value={`${(data.total_return ?? 0) >= 0 ? '+' : ''}${data.total_return?.toFixed(1) ?? '?'}%`} />
            <Stat label="夏普" value={data.sharpe?.toFixed(2) ?? '?'} />
            <Stat label="回撤" value={`${data.max_drawdown?.toFixed(1) ?? '?'}%`} />
            <Stat label="交易" value={`${data.trade_count ?? '?'} 笔`} />
          </div>
          <div className="glass" style={{ padding: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>进化最优参数</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px', fontSize: '13px' }}>
              {data.config && Object.entries(data.config).filter(([k]) =>
                ['bear_market_no_buy','take_profit_pct','stop_loss_pct','ml_weight','min_score_bull','min_score_neutral','min_score_bear','trailing_tp_activate','cooldown_days','kelly_cap'].includes(k)
              ).map(([k, v]: any) => (
                <div key={k} style={{ background: 'rgba(255,255,255,0.03)', padding: '8px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{k}</div>
                  <div style={{ fontWeight: 600 }}>{typeof v === 'boolean' ? (v ? '是' : '否') : v}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

const inpStyle: React.CSSProperties = { padding: '8px', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(255,255,255,0.05)', color: 'var(--text-primary)', width: '130px' }

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return <div className="glass" style={{ padding: '14px', textAlign: 'center', minWidth: '100px', flex: 1 }}>
    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{label}</div>
    <div style={{ fontSize: '18px', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
  </div>
}

function Mini({ label, val }: { label: string; val: string }) {
  return <div style={{ background: 'rgba(255,255,255,0.03)', padding: '8px 12px', borderRadius: '8px', textAlign: 'center' }}>
    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{label}</div>
    <div style={{ fontSize: '14px', fontWeight: 600 }}>{val}</div>
  </div>
}
