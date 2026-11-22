import { isTerminal, type Status } from '../api'
import { STATUS_LABELS } from '../format'

function tone(status: Status): string {
  if (status === 'done') return 'ok'
  if (status === 'done_with_warnings') return 'warn'
  if (status === 'failed') return 'danger'
  return 'busy'
}

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`badge badge--${tone(status)}`}>
      <span className={isTerminal(status) ? 'badge__dot' : 'badge__dot badge__dot--pulse'} aria-hidden />
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
