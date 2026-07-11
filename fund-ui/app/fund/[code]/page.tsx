'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

interface FundDetail {
  code: string; name: string; type: string; scale: string
  risk: string; company: string; rating: number
  established: string
  chart: Array<{ date: string; value: number }>
  performance: Array<{ period: string; r: number | null }>
  allocation: Record<string, number>
  topStocks: Array<{ name: string; code: string; ratio: string; rate: string }>
  notices: Array<{ date: string; title: string }>
}

export default function FundDetailPage() {
  const { code } = useParams<{ code: string }>()
  const [data, setData] = useState<FundDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`/api/detail?code=${code}`)
      .then(r => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [code])

  if (loading) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载中...</div>
  if (!data) return <div style={{ textAlign: 'center', padding: '40px', color: 'var(--accent-red)' }}>无法加载基金数据</div>

  const totalReturn = data.chart.length >= 2
    ? ((data.chart[data.chart.length - 1].value - data.chart[0].value)).toFixed(2)
    : '0'

  return (
    <div>
      <a href="/" style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px', display: 'block' }}>← 返回自选列表</a>

      {/* header */}
      <div className="glass" style={{ padding: '20px', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '8px' }}>
          {data.name}
        </h2>
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '13px', color: 'var(--text-secondary)' }}>
          <span>{data.code}</span>
          <span>{data.type}</span>
          <span>{data.scale}</span>
          <span>风险: {data.risk}</span>
          <span>晨星: {'★'.repeat(data.rating || 0)}</span>
          <span>成立: {data.established}</span>
          <span>{data.company}</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
        {/* 净值曲线 */}
        <div className="glass" style={{ padding: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>
            累计收益率 (近90天 · {totalReturn}%)
          </h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={data.chart}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                     tickFormatter={(d: string) => d.slice(5)} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: 'rgba(15,20,40,0.9)', border: '1px solid var(--glass-border)', borderRadius: '8px' }}
                labelStyle={{ color: 'var(--text-secondary)' }}
                formatter={(v: number) => [`${v.toFixed(2)}%`, '累计收益']}
              />
              <Line type="monotone" dataKey="value" stroke="#ff5577" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* 业绩排名 */}
        <div className="glass" style={{ padding: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>历史业绩</h3>
          <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--text-secondary)' }}>
                <th style={{ textAlign: 'left', padding: '6px' }}>周期</th>
                <th style={{ textAlign: 'right', padding: '6px' }}>收益率</th>
              </tr>
            </thead>
            <tbody>
              {data.performance?.map((p, i) => (
                <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  <td style={{ padding: '6px' }}>{p.period}</td>
                  <td style={{
                    padding: '6px', textAlign: 'right',
                    color: (p.r ?? 0) >= 0 ? 'var(--accent-red)' : 'var(--accent-green)'
                  }}>
                    {(p.r ?? 0) >= 0 ? '+' : ''}{p.r?.toFixed(2) ?? 'N/A'}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* 资产配置 */}
        {Object.keys(data.allocation).length > 0 && (
          <div className="glass" style={{ padding: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>资产配置</h3>
            {Object.entries(data.allocation).map(([name, val]) => (
              <div key={name} style={{ marginBottom: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '2px' }}>
                  <span>{name}</span><span>{val}%</span>
                </div>
                <div className="score-bar">
                  <div className="score-bar-fill" style={{ width: `${val}%`, background: 'var(--accent-blue)' }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 前十大持仓 */}
        {data.topStocks?.length > 0 && (
          <div className="glass" style={{ padding: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>前十大重仓股</h3>
            {data.topStocks.map((s, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0',
                borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '13px' }}>
                <span>
                  {s.name}
                  <span style={{ color: 'var(--text-secondary)', marginLeft: '8px', fontSize: '11px' }}>{s.code}</span>
                </span>
                <span style={{ color: 'var(--accent-blue)' }}>{s.ratio}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
