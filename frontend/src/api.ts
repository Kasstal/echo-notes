// Typed client for the backend REST API (see the MVP spec, section 5).
// In dev, Vite proxies /api to the backend, so the base is empty by default.
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '') + '/api'

export type Status =
  | 'queued'
  | 'recording'
  | 'normalizing'
  | 'transcribing'
  | 'diarizing'
  | 'summarizing'
  | 'done'
  | 'done_with_warnings'
  | 'failed'

export const TERMINAL_STATUSES: Status[] = ['done', 'done_with_warnings', 'failed']

export function isTerminal(status: Status): boolean {
  return TERMINAL_STATUSES.includes(status)
}

export interface Segment {
  start: number
  end: number
  speaker: string
  text: string
}

export interface Transcript {
  language: string
  duration_sec: number
  speakers: Record<string, string>
  segments: Segment[]
}

export interface ActionItem {
  owner: string | null
  task: string
  due: string | null
}

export interface Summary {
  tldr: string
  key_points: string[]
  decisions: string[]
  action_items: ActionItem[]
}

export interface SessionListItem {
  id: string
  title: string | null
  source: 'upload' | 'bot'
  status: Status
  created_at: string
  duration: number | null
}

export interface SessionDetail extends SessionListItem {
  error?: string | null
  transcript?: Transcript | null
  summary?: Summary | null
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const UNREACHABLE = 'Cannot reach the EchoNotes backend. Check that it is running.'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, init)
  } catch {
    throw new ApiError(0, UNREACHABLE)
  }
  // The Vite dev proxy answers 502/504 with an empty body when the backend is down.
  if (res.status === 502 || res.status === 504) throw new ApiError(res.status, UNREACHABLE)
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') message = body.detail
      else if (typeof body?.error === 'string') message = body.error
    } catch {
      // Non-JSON error body: keep the status line.
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export function listSessions(): Promise<SessionListItem[]> {
  return request('/sessions')
}

export function getSession(id: string): Promise<SessionDetail> {
  return request(`/sessions/${encodeURIComponent(id)}`)
}

export function uploadRecording(file: File, title?: string): Promise<{ id: string; status: Status }> {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  return request('/sessions/upload', { method: 'POST', body: form })
}

export function sendBot(meetingUrl: string, title?: string): Promise<{ id: string; status: Status }> {
  return request('/sessions/bot', json('POST', { meeting_url: meetingUrl, ...(title ? { title } : {}) }))
}

export function renameSpeakers(id: string, names: Record<string, string>): Promise<unknown> {
  return request(`/sessions/${encodeURIComponent(id)}/speakers`, json('PATCH', names))
}

export async function searchSession(id: string, query: string): Promise<Segment[]> {
  const body = await request<Segment[] | { results?: Segment[]; matches?: Segment[] }>(
    `/sessions/${encodeURIComponent(id)}/search?q=${encodeURIComponent(query)}`,
  )
  if (Array.isArray(body)) return body
  return body?.results ?? body?.matches ?? []
}

export function exportUrl(id: string): string {
  return `${API_BASE}/sessions/${encodeURIComponent(id)}/export?format=md`
}

export function retrySummary(id: string): Promise<unknown> {
  return request(`/sessions/${encodeURIComponent(id)}/retry-summary`, { method: 'POST' })
}

export function deleteSession(id: string): Promise<unknown> {
  return request(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
