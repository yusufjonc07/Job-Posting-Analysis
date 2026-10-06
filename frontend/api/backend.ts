// Vercel Edge Function: forwards /api/* to the dashboard backend (BACKEND_URL, set in the Vercel project).
// The browser only talks to the Vercel site, so the Telegram login cookie works; responses are streamed,
// so live updates (server-sent events) arrive as they happen. vercel.json rewrites /api/<path> to
// /api/backend?path=<path>.
export const config = { runtime: 'edge' }

/** Headers that belong to one connection and must not be forwarded. */
const HOP_BY_HOP = ['connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'host', 'content-length']

export default async function handler(request: Request): Promise<Response> {
  const backend = process.env.BACKEND_URL
  if (!backend) {
    return Response.json({ detail: 'BACKEND_URL is not set in the Vercel project settings', offline: true }, { status: 502 })
  }
  const incoming = new URL(request.url)
  const path = incoming.searchParams.get('path') ?? ''
  incoming.searchParams.delete('path')
  const target = new URL(`/api/${path}${incoming.search}`, backend)

  const headers = new Headers(request.headers)
  for (const name of HOP_BY_HOP) headers.delete(name)
  headers.set('x-forwarded-host', incoming.host)
  headers.set('x-forwarded-proto', incoming.protocol.replace(':', ''))
  if (path.startsWith('events')) headers.set('accept-encoding', 'identity')

  let response: Response
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer(),
      redirect: 'manual',
    })
  } catch {
    return Response.json({ detail: 'The dashboard backend is unreachable', offline: true }, { status: 502 })
  }

  const out = new Headers(response.headers)
  out.delete('content-encoding') // fetch has already decoded the body
  out.delete('content-length')
  if (path.startsWith('events')) {
    out.set('cache-control', 'no-cache, no-transform')
    out.set('x-accel-buffering', 'no')
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers: out })
}
