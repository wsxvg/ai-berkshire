// 京东金融 API 客户端
// 通过 Next.js API Route 代理调用 Python 脚本

export interface FundInfo {
  code: string
  name: string
  nav: string
  dayReturn: number | null
  weekReturn: number | null
  monthReturn: number | null
  yearReturn: number | null
  totalPnl: number | null
  fundType: string
}

export interface FundScore {
  code: string
  name: string
  total: number
  quality: number
  cost: number
  manager: number
  momentum: number
  smartMoney: number
  pass4433: number
  rsi: number | null
  blocked: boolean
  blockReason: string
}

export interface DailyReport {
  date: string
  market: string
  candidates: Array<{ code: string; name: string; score: number }>
  buys: Array<{ code: string; name: string; amount: number; reason: string }>
  sells: Array<{ code: string; name: string; amount: number; reason: string }>
  blocked: Array<{ code: string; name: string; reason: string }>
  holdings: Record<string, { name: string; cost: number; marketValue: number; pnlPct: number }>
  portfolio: { totalValue: number; cash: number; fees: number }
}

const API = '/api'

export async function fetchWatchlist(): Promise<FundInfo[]> {
  const res = await fetch(`${API}/fund`)
  if (!res.ok) throw new Error('Failed to fetch watchlist')
  const data = await res.json()
  // 防御: API 可能返 error 对象或非数组
  if (!Array.isArray(data)) {
    console.warn('fetchWatchlist: API returned non-array', data)
    return []
  }
  return data
}

export async function fetchScores(codes: string[]): Promise<FundScore[]> {
  const res = await fetch(`${API}/score?codes=${codes.join(',')}`)
  if (!res.ok) throw new Error('Failed to fetch scores')
  const data = await res.json()
  if (!Array.isArray(data)) {
    console.warn('fetchScores: API returned non-array', data)
    return []
  }
  return data
}

export async function fetchDailyReport(): Promise<DailyReport | null> {
  const res = await fetch(`${API}/report`)
  if (!res.ok) return null
  return res.json()
}
