'use client'

import { useState } from 'react'

export default function DCAPage() {
  const [amount, setAmount] = useState(2000)
  const [years, setYears] = useState(5)
  const [annualReturn, setAnnualReturn] = useState(15)
  const [result, setResult] = useState({ total: 0, profit: 0, profitRate: 0 } as any)

  const calc = () => {
    const monthly = amount
    const months = years * 12
    const r = annualReturn / 100 / 12
    let total = 0
    for (let i = 0; i < months; i++) {
      total = (total + monthly) * (1 + r)
    }
    const invested = monthly * months
    setResult({
      total: Math.round(total),
      profit: Math.round(total - invested),
      profitRate: Math.round(((total - invested) / invested) * 100),
      invested,
    })
  }

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 700 }}>定投计算器</h2>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>模拟每月定投收益</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
        <div className="glass" style={{ padding: '24px' }}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>每月定投金额 (元)</label>
            <input type="number" value={amount} onChange={e => setAmount(Number(e.target.value))}
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(255,255,255,0.05)', color: 'var(--text-primary)' }} />
          </div>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>投资年限</label>
            <input type="number" value={years} onChange={e => setYears(Number(e.target.value))}
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(255,255,255,0.05)', color: 'var(--text-primary)' }} />
          </div>
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>预期年化收益率 (%)</label>
            <input type="number" value={annualReturn} onChange={e => setAnnualReturn(Number(e.target.value))}
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(255,255,255,0.05)', color: 'var(--text-primary)' }} />
          </div>
          <button onClick={calc} style={{
            width: '100%', padding: '12px', borderRadius: '12px', border: 'none',
            background: 'var(--accent-red)', color: '#fff', fontWeight: 600, fontSize: '16px', cursor: 'pointer'
          }}>计算</button>
        </div>
        {result.total > 0 && (
          <div className="glass" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>定投结果</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <StatBox label="投入本金" value={`${(result.invested).toLocaleString()} 元`} />
              <StatBox label="最终资产" value={`${(result.total).toLocaleString()} 元`} color="var(--accent-red)" />
              <StatBox label="总收益" value={`${(result.profit).toLocaleString()} 元`} color="var(--accent-red)" />
              <StatBox label="收益率" value={`${result.profitRate}%`} color="var(--accent-red)" />
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '16px' }}>
              每月定投 {amount.toLocaleString()} 元，{years} 年后预计 {result.total.toLocaleString()} 元
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
      <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '16px', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}
