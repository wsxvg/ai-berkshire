'use client'

import { useState, useEffect } from 'react'

interface SectorSummary {
  pe_pct: number | null
  pb_pct: number | null
  valuation_status: string
  signal_score: number | null
  description?: string
  pe_history?: { date: string; pe: number; pb: number; pe_pct: number; pb_pct: number }[]
}

interface SectorData {
  [code: string]: {
    name: string
    pe_pct: number | null
    pb_pct: number | null
    valuation_status: string
    signal_score: number | null
  }
}

const STATUS_COLORS: Record<string, string> = {
  '高估': '#ff5577',
  '低估': '#00d4aa',
  '中性': '#5b8def',
  '未知': '#888',
}

const STATUS_BG: Record<string, string> = {
  '高估': 'rgba(255, 85, 119, 0.15)',
  '低估': 'rgba(0, 212, 170, 0.15)',
  '中性': 'rgba(91, 141, 239, 0.15)',
  '未知': 'rgba(136, 136, 136, 0.15)',
}

const ADVICE: Record<string, { text: string; color: string }> = {
  '高估': { text: '建议减仓/止盈', color: '#ff5577' },
  '低估': { text: '建议加仓/建仓', color: '#00d4aa' },
  '中性': { text: '正常持有', color: '#5b8def' },
  '未知': { text: '数据不足', color: '#888' },
}

export default function SectorPage() {
  const [data, setData] = useState<SectorData>({})
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<SectorSummary | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    fetch('/api/sector')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { console.error(e); setLoading(false) })
  }, [])

  const loadDetail = async (code: string) => {
    setSelected(code)
    setDetailLoading(true)
    try {
      const r = await fetch(`/api/sector?code=${code}`)
      const d = await r.json()
      setDetail(d)
    } catch (e) {
      console.error(e)
    } finally {
      setDetailLoading(false)
    }
  }

  const sectors = Object.entries(data)
  const summary = {
    high: sectors.filter(([, v]) => v.valuation_status === '高估').length,
    low: sectors.filter(([, v]) => v.valuation_status === '低估').length,
    mid: sectors.filter(([, v]) => v.valuation_status === '中性').length,
  }

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>行业估值仪表盘</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', fontSize: '14px' }}>
        基于历史 PE/PB 百分位判断行业估值水平。低估值机会大于风险, 高估值建议谨慎。
      </p>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>加载中...</div>
      ) : sectors.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>暂无行业数据</div>
      ) : (
        <>
          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '20px' }}>
            <div style={{ background: STATUS_BG['低估'], padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 700, color: STATUS_COLORS['低估'] }}>{summary.low}</div>
              <div style={{ fontSize: '13px', color: STATUS_COLORS['低估'] }}>低估机会</div>
            </div>
            <div style={{ background: STATUS_BG['中性'], padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 700, color: STATUS_COLORS['中性'] }}>{summary.mid}</div>
              <div style={{ fontSize: '13px', color: STATUS_COLORS['中性'] }}>估值中性</div>
            </div>
            <div style={{ background: STATUS_BG['高估'], padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 700, color: STATUS_COLORS['高估'] }}>{summary.high}</div>
              <div style={{ fontSize: '13px', color: STATUS_COLORS['高估'] }}>高估风险</div>
            </div>
          </div>

          {/* Sector grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
            {sectors
              .sort((a, b) => (a[1].pe_pct ?? 50) - (b[1].pe_pct ?? 50))
              .map(([code, v]) => {
                const pePct = v.pe_pct ?? 0
                const status = v.valuation_status
                const advice = ADVICE[status] || ADVICE['未知']
                return (
                  <div
                    key={code}
                    onClick={() => loadDetail(code)}
                    style={{
                      background: 'var(--bg-card)',
                      border: `1px solid ${selected === code ? STATUS_COLORS[status] : 'var(--border)'}`,
                      borderRadius: '12px',
                      padding: '16px',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div style={{ fontSize: '14px', fontWeight: 600 }}>{v.name}</div>
                      <div style={{
                        fontSize: '11px',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: STATUS_BG[status],
                        color: STATUS_COLORS[status],
                        fontWeight: 600,
                      }}>
                        {status}
                      </div>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px' }}>{code}</div>
                    {/* PE 百分位条 */}
                    <div style={{ marginBottom: '6px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '2px' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>PE 百分位</span>
                        <span style={{ color: STATUS_COLORS[status], fontWeight: 600 }}>{pePct.toFixed(1)}%</span>
                      </div>
                      <div style={{ height: '6px', background: 'var(--border)', borderRadius: '3px', position: 'relative' }}>
                        <div style={{
                          height: '100%',
                          width: `${pePct}%`,
                          background: `linear-gradient(90deg, ${STATUS_COLORS['低估']}, ${STATUS_COLORS['中性']}, ${STATUS_COLORS['高估']})`,
                          borderRadius: '3px',
                        }} />
                        <div style={{
                          position: 'absolute',
                          left: '70%',
                          top: '-2px',
                          width: '1px',
                          height: '10px',
                          background: 'var(--text-secondary)',
                        }} />
                      </div>
                    </div>
                    {v.pb_pct !== null && (
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                        PB 百分位: {v.pb_pct.toFixed(1)}%
                      </div>
                    )}
                    <div style={{ marginTop: '8px', fontSize: '11px', color: advice.color, fontWeight: 600 }}>
                      {advice.text}
                    </div>
                  </div>
                )
              })}
          </div>

          {/* Detail panel */}
          {selected && detail && (
            <div style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, width: '420px',
              background: 'var(--bg-card)', boxShadow: '-4px 0 12px rgba(0,0,0,0.1)',
              padding: '20px', overflowY: 'auto', zIndex: 100,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{detail.name}</h2>
                <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '20px', color: 'var(--text-secondary)' }}>×</button>
              </div>
              {detailLoading ? (
                <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-secondary)' }}>加载中...</div>
              ) : detail.latest ? (
                <>
                  <div style={{ background: 'var(--bg-secondary)', padding: '12px', borderRadius: '8px', marginBottom: '12px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>最新 ({detail.latest.date})</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                      <div>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>PE</div>
                        <div style={{ fontSize: '18px', fontWeight: 700 }}>{detail.latest.pe.toFixed(2)}</div>
                        <div style={{ fontSize: '11px', color: STATUS_COLORS[detail.latest.pe_pct > 70 ? '高估' : detail.latest.pe_pct < 30 ? '低估' : '中性'] }}>
                          百分位 {detail.latest.pe_pct.toFixed(1)}%
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>PB</div>
                        <div style={{ fontSize: '18px', fontWeight: 700 }}>{detail.latest.pb.toFixed(2)}</div>
                        <div style={{ fontSize: '11px', color: STATUS_COLORS[detail.latest.pb_pct > 70 ? '高估' : detail.latest.pb_pct < 30 ? '低估' : '中性'] }}>
                          百分位 {detail.latest.pb_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    历史数据: {detail.history_days} 个交易日
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--text-secondary)' }}>无数据</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
