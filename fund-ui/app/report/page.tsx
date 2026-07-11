'use client'

import { useState, useEffect } from 'react'
import { fetchDailyReport, DailyReport } from '../lib/jd-api'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

function StatCard({ label, value, unit = '' }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="glass" style={{ padding: '16px', textAlign: 'center', minWidth: '120px' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '20px', fontWeight: 700 }}>
        <span className={typeof value === 'string' && value.startsWith('+') ? 'up' : ''}>
          {value}
        </span>
        {unit}
      </div>
    </div>
  )
}

export default function ReportPage() {
  const [data, setData] = useState<DailyReport | null>(null)
  const [snapshots, setSnapshots] = useState<Array<{ date: string; total_value: number }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/report')
      .then(r => r.json())
      .then(d => { setData(d.latest); setSnapshots(d.snapshots || []) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载日报...</div>
  if (error) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
    暂无日报数据（首次运行后生成）
  </div>
  if (!data) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>无数据</div>

  const { portfolio, candidates, buys, sells, blocked, holdings, date, market } = data
  const pnl = portfolio.totalValue - 100000
  const pnlPct = (pnl / 100000 * 100)

  // 持仓用于图表
  const holdingEntries = Object.entries(holdings || {}).map(([code, h]) => ({
    code, name: h.name, cost: h.cost, marketValue: h.marketValue, pnl: h.pnlPct
  }))

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>模拟实盘日报</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          {date} · 市场: {market}
        </span>
      </div>

      {/* 组合概览 */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <StatCard label="总资产" value={(portfolio.totalValue).toLocaleString()} unit=" 元" />
        <StatCard label="总收益" value={`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}`} unit="%" />
        <StatCard label="现金" value={portfolio.cash.toLocaleString()} unit=" 元" />
        <StatCard label="手续费" value={portfolio.fees.toLocaleString()} unit=" 元" />
      </div>

      {/* 净值趋势 */}
      {snapshots.length > 1 && (
        <div className="glass" style={{ padding: '16px', marginBottom: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>组合净值走势</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={snapshots}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                     tickFormatter={(d: string) => d.slice(5)} />
              <YAxis domain={['dataMin - 1000', 'dataMax + 1000']} tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} />
              <Tooltip
                contentStyle={{ background: 'rgba(15,20,40,0.9)', border: '1px solid var(--glass-border)', borderRadius: '8px' }}
                formatter={(v: number) => [`${v.toLocaleString()} 元`, '总资产']}
              />
              <Area type="monotone" dataKey="total_value" stroke="#ff5577" fill="rgba(255,85,119,0.15)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 操作建议 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        {/* 推荐买入 */}
        <div className="glass" style={{ padding: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--accent-green)', marginBottom: '12px' }}>
            推荐买入 ({buys?.length || 0})
          </h3>
          {buys?.length ? buys.map((b, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: '14px', fontWeight: 500 }}>{b.name}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {b.amount.toLocaleString()} 元 · {b.reason}
              </div>
            </div>
          )) : <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>今日无推荐买入</div>}
        </div>

        {/* 推荐卖出 */}
        <div className="glass" style={{ padding: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--accent-red)', marginBottom: '12px' }}>
            建议卖出 ({sells?.length || 0})
          </h3>
          {sells?.length ? sells.map((s, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: '14px', fontWeight: 500 }}>{s.name}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {s.amount.toLocaleString()} 元 · {s.reason}
              </div>
            </div>
          )) : <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>今日无卖出建议</div>}
        </div>

        {/* 风控拦截 */}
        <div className="glass" style={{ padding: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--accent-gold)', marginBottom: '12px' }}>
            风控拦截 ({blocked?.length || 0})
          </h3>
          {blocked?.length ? blocked.map((b, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontSize: '14px', fontWeight: 500 }}>{b.name}</div>
              <div style={{ fontSize: '12px', color: 'var(--accent-gold)' }}>{b.reason}</div>
            </div>
          )) : <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>今日无风控拦截</div>}
        </div>
      </div>

      {/* 候选评分 TOP 5 */}
      <div className="glass" style={{ padding: '16px', marginBottom: '24px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>评分 TOP 5</h3>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {candidates?.slice(0, 5).map((c, i) => (
            <span key={i} style={{
              padding: '6px 14px', borderRadius: '8px',
              background: 'rgba(91,141,239,0.15)', fontSize: '13px',
            }}>
              {c.name} <strong>{c.score.toFixed(1)}</strong>
            </span>
          ))}
        </div>
      </div>

      {/* 持仓表格 */}
      {holdingEntries.length > 0 && (
        <div className="glass" style={{ padding: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>当前持仓</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '14px', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'left' }}>
                  <th style={{ padding: '8px' }}>基金</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>成本</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>市值</th>
                  <th style={{ padding: '8px', textAlign: 'right' }}>盈亏</th>
                </tr>
              </thead>
              <tbody>
                {holdingEntries.map(h => (
                  <tr key={h.code} style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '10px 8px' }}>{h.name} <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>({h.code})</span></td>
                    <td style={{ padding: '10px 8px', textAlign: 'right' }}>{h.cost?.toLocaleString()}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right' }}>{h.marketValue?.toLocaleString()}</td>
                    <td style={{ padding: '10px 8px', textAlign: 'right', color: (h.pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                      {(h.pnl ?? 0) >= 0 ? '+' : ''}{h.pnl?.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* AI 审计入口 */}
      <div className="glass" style={{ padding: '16px', marginTop: '24px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '8px' }}>AI 审计</h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          在本地 IDE 中打开日报，CodeBuddy 自动调用 SKILL 深度分析
        </p>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {buys?.length > 0 && (
            <span style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(0,212,170,0.1)', fontSize: '12px' }}>
              fund-checklist {buys.map(b => b.code).join(' ')}
            </span>
          )}
          <span style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(240,185,11,0.1)', fontSize: '12px' }}>
            fund-sell {Object.keys(holdings || {}).join(' ')}
          </span>
        </div>
      </div>
    </div>
  )
}
