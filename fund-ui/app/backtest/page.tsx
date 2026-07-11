'use client'

import { useState, useEffect } from 'react'

interface BacktestResult {
  config: any
  annualized?: number
  total_return?: number
  sharpe_ratio?: number
  max_drawdown?: number
  calmar_ratio?: number
  trade_count?: number
  benchmark_return?: number
  total_fees?: number
  final_value?: number
}

export default function BacktestPage() {
  const [data, setData] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/backtest')
      .then(r => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载回测数据...</div>

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>回测结果</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          进化最优参数 · 2024-03-11 ~ 2026-07-01 · 初始 100,000
        </span>
      </div>

      {data ? (
        <>
          <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
            <Stat label="年化回报" value={`${data.annualized?.toFixed(1) ?? '?'}%`} color="var(--accent-red)" />
            <Stat label="总收益" value={`${(data.total_return ?? 0) >= 0 ? '+' : ''}${data.total_return?.toFixed(1) ?? '?'}%`} />
            <Stat label="夏普比率" value={data.sharpe_ratio?.toFixed(2) ?? '?'} />
            <Stat label="最大回撤" value={`${data.max_drawdown?.toFixed(1) ?? '?'}%`} />
            <Stat label="Calmar" value={data.calmar_ratio?.toFixed(2) ?? '?'} />
            <Stat label="交易次数" value={`${data.trade_count ?? '?'} 笔`} />
            <Stat label="最终资产" value={`${(data.final_value ?? 0).toLocaleString()} 元`} />
          </div>

          <div className="glass" style={{ padding: '16px', marginBottom: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>进化最优参数</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px', fontSize: '13px' }}>
              {data.config && Object.entries(data.config).filter(([k]) =>
                ['bear_market_no_buy','take_profit_pct','stop_loss_pct','ml_weight',
                 'min_score_bull','min_score_neutral','min_score_bear',
                 'trailing_tp_activate','cooldown_days','kelly_cap'].includes(k)
              ).map(([k, v]: any) => (
                <div key={k} style={{ background: 'rgba(255,255,255,0.03)', padding: '8px 12px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{k}</div>
                  <div style={{ fontWeight: 600 }}>{typeof v === 'boolean' ? (v ? '是' : '否') : v}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="glass" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          暂无回测数据。运行 <code style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px' }}>py -3.10 -c "from backtest.engine.backtest import run_backtest; ..."</code> 后查看。
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="glass" style={{ padding: '16px', textAlign: 'center', minWidth: '120px', flex: 1 }}>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '20px', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}
