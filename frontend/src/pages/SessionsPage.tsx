import { isTerminal, listSessions } from '../api'
import { BotForm, UploadForm } from '../components/StartForms'
import { StatusBadge } from '../components/StatusBadge'
import { formatDate, formatDuration, sessionTitle } from '../format'
import { sessionHref } from '../router'
import { usePolling } from '../usePolling'

export function SessionsPage() {
  const { data: sessions, error } = usePolling(listSessions, (list) =>
    list.some((s) => !isTerminal(s.status)),
  )

  return (
    <>
      <section className="intro">
        <h1>Meeting notes</h1>
        <p>Upload a recording or send the bot to a call. Each session gets a transcript with speakers and a summary.</p>
      </section>

      <section className="start" aria-label="Start a session">
        <UploadForm />
        <BotForm />
      </section>

      <section className="sessions" aria-labelledby="sessions-heading">
        <h2 id="sessions-heading">Sessions</h2>
        {error && !sessions && <p className="form-error" role="alert">{error.message}</p>}
        {sessions === null && !error && <p className="muted">Loading sessions…</p>}
        {sessions?.length === 0 && (
          <p className="empty">No sessions yet. Upload a recording above to create the first one.</p>
        )}
        {sessions && sessions.length > 0 && (
          <div className="table-wrap">
            <table className="sessions-table">
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Source</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                  <th scope="col" className="num">Length</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <a href={sessionHref(s.id)}>{sessionTitle(s.title, s.created_at)}</a>
                    </td>
                    <td>{s.source === 'bot' ? 'Meet bot' : 'Upload'}</td>
                    <td>
                      <StatusBadge status={s.status} />
                    </td>
                    <td>{formatDate(s.created_at)}</td>
                    <td className="num">{formatDuration(s.duration)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
