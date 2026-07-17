import { NextRequest, NextResponse } from 'next/server'

/**
 * 统一 404
 * GET/POST/DELETE /api/[...path]  - 任何未知路径
 */
function notFound(path: string) {
  return NextResponse.json({
    error: 'API endpoint not found',
    path,
    hint: 'Available: /api/fund /api/detail /api/score /api/ranking /api/ranking/featured /api/sector /api/news /api/notices /api/feed /api/backtest /api/run-backtest /api/compare /api/report /api/search /api/status /api/health /api/cache/clear /api/insights',
    ts: Date.now(),
  }, { status: 404, headers: { 'Cache-Control': 'no-store' } })
}

export async function GET(req: NextRequest) { return notFound(req.nextUrl.pathname) }
export async function POST(req: NextRequest) { return notFound(req.nextUrl.pathname) }
export async function PUT(req: NextRequest) { return notFound(req.nextUrl.pathname) }
export async function DELETE(req: NextRequest) { return notFound(req.nextUrl.pathname) }
export async function PATCH(req: NextRequest) { return notFound(req.nextUrl.pathname) }
export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Allow': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    }
  })
}
