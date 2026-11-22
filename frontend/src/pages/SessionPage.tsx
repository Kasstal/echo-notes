import { useCallback, useState } from 'react'
import { getSession, isTerminal, type SessionDetail, type Status } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { StatusStepper } from '../components/StatusStepper'
import { SummaryPanel } from '../components/SummaryPanel'
import { formatDate, formatDuration, sessionTitle } from '../format'
import { usePolling } from '../usePolling'

const LANGUAGES: Record<string, string> = { en: 'English', ru: 'Russian', kk: 'Kazakh' }

export function SessionPage({ id }: { id: string }) {
  const [lastActive, setLastActive] = useState<Status | null>(null)

  const load = useCallback(async () => {
    const session = await getSession(id)
    if (!isTerminal(session.status)) setLastActive(session.status)
    return session
  }, [id])

  const { data: session, error } = usePolling<SessionDetail>(load, (s) => !isTerminal(s.status))

  if (!session) {
    return (
      <div className="session-page">
        <a className="back" href="#/">All sessions</a>
        {error ? (
          <p className="form-error" role="alert">
            {error.message}
          </p>
        ) : (
          <p className="muted">Loading session…</p>
        )}
      </div>
    )
  }

  const transcript = session.transcript
  const language = transcript?.language

  return (
    <div className="session-page">
      <a className="back" href="#/">All sessions</a>

      <header className="session-head">
        <div className="session-head__text">
          <h1>{sessionTitle(session.title, session.created_at)}</h1>
          <ul className="session-meta">
            <li>{session.source === 'bot' ? 'Recorded by Meet bot' : 'Uploaded'} {formatDate(session.created_at)}</li>
            <li>{formatDuration(session.duration ?? transcript?.duration_sec)}</li>
            {language && <li>{LANGUAGES[language] ?? language.toUpperCase()}</li>}
            <li>
              <StatusBadge status={session.status} />
            </li>
          </ul>
        </div>
      </header>

      <StatusStepper status={session.status} source={session.source} lastActive={lastActive} />

      {session.error && (session.status === 'failed' || session.status === 'done_with_warnings') && (
        <p className={session.status === 'failed' ? 'banner banner--danger' : 'banner banner--warn'} role="alert">
          {session.error}
        </p>
      )}
      {error && <p className="banner banner--warn">Lost connection to the backend. Retrying…</p>}

      <div className="session-body">
        <SummaryPanel summary={session.summary} status={session.status} />
        <section className="transcript-panel" aria-labelledby="transcript-heading">
          <h2 id="transcript-heading">Transcript</h2>
          {!transcript && <p className="muted">The transcript appears once speakers have been identified.</p>}
        </section>
      </div>
    </div>
  )
}
