import type { Status } from './api'

export const STATUS_LABELS: Record<Status, string> = {
  queued: 'Queued',
  recording: 'Recording',
  normalizing: 'Preparing audio',
  transcribing: 'Transcribing',
  diarizing: 'Identifying speakers',
  summarizing: 'Summarizing',
  done: 'Done',
  done_with_warnings: 'Done with warnings',
  failed: 'Failed',
}

export function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h) return `${h} h ${m} min`
  if (m) return `${m} min ${s} s`
  return `${s} s`
}

export function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function sessionTitle(title: string | null | undefined, createdAt: string): string {
  return title?.trim() || `Recording from ${formatDate(createdAt)}`
}

export function segmentDomId(index: number): string {
  return `seg-${index}`
}
