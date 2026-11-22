import { useState } from 'react'
import { deleteSession, exportUrl, isTerminal, retrySummary, type SessionDetail } from '../api'
import { navigate } from '../router'

interface Props {
  session: SessionDetail
  onRetryStarted: () => void
}

export function SessionActions({ session, onRetryStarted }: Props) {
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [busy, setBusy] = useState<'retry' | 'delete' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const hasTranscript = Boolean(session.transcript)
  const canRetry = hasTranscript && isTerminal(session.status)

  async function onRetry() {
    setBusy('retry')
    setError(null)
    try {
      await retrySummary(session.id)
      onRetryStarted()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function onDelete() {
    setBusy('delete')
    setError(null)
    try {
      await deleteSession(session.id)
      navigate('#/')
    } catch (err) {
      setError((err as Error).message)
      setBusy(null)
    }
  }

  return (
    <div className="session-actions">
      <div className="session-actions__row">
        {hasTranscript ? (
          <a className="btn" href={exportUrl(session.id)} download>
            Export Markdown
          </a>
        ) : (
          <button className="btn" type="button" disabled>
            Export Markdown
          </button>
        )}
        <button
          className="btn"
          type="button"
          onClick={onRetry}
          disabled={!canRetry || busy !== null}
          title={canRetry ? undefined : 'Available once the transcript is ready and processing has finished'}
        >
          {busy === 'retry' ? 'Starting…' : 'Retry summary'}
        </button>
        {!confirmingDelete && (
          <button className="btn btn--danger" type="button" onClick={() => setConfirmingDelete(true)} disabled={busy !== null}>
            Delete
          </button>
        )}
      </div>

      {confirmingDelete && (
        <div className="confirm" role="alertdialog" aria-labelledby="confirm-delete-text">
          <p id="confirm-delete-text">Delete this session? The recording, transcript and summary are removed for good.</p>
          <div className="session-actions__row">
            <button className="btn btn--danger-solid" type="button" onClick={onDelete} disabled={busy !== null} autoFocus>
              {busy === 'delete' ? 'Deleting…' : 'Delete session'}
            </button>
            <button className="btn" type="button" onClick={() => setConfirmingDelete(false)} disabled={busy !== null}>
              Keep it
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
