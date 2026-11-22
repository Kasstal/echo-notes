import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getSession, isTerminal, renameSpeakers, type SessionDetail, type Status, type Transcript } from '../api'
import { SpeakerLegend } from '../components/SpeakerLegend'
import { StatusBadge } from '../components/StatusBadge'
import { StatusStepper } from '../components/StatusStepper'
import { SummaryPanel } from '../components/SummaryPanel'
import { TranscriptView } from '../components/TranscriptView'
import { formatDate, formatDuration, segmentDomId, sessionTitle } from '../format'
import { speakerColors, speakerLabels } from '../speakers'
import { usePolling } from '../usePolling'

const LANGUAGES: Record<string, string> = { en: 'English', ru: 'Russian', kk: 'Kazakh' }

function segmentAt(transcript: Transcript, t: number): number | null {
  let found: number | null = null
  transcript.segments.forEach((seg, i) => {
    if (seg.start <= t) found = i
  })
  return found
}

function scrollToSegment(index: number) {
  document.getElementById(segmentDomId(index))?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

export function SessionPage({ id, t }: { id: string; t: number | null }) {
  const [lastActive, setLastActive] = useState<Status | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const jumpedToLinkedTime = useRef(false)

  const load = useCallback(async () => {
    const session = await getSession(id)
    if (!isTerminal(session.status)) setLastActive(session.status)
    return session
  }, [id])

  const { data: session, setData, error, reload } = usePolling<SessionDetail>(load, (s) => !isTerminal(s.status))
  const transcript = session?.transcript ?? null

  const labels = useMemo(() => (transcript ? speakerLabels(transcript) : []), [transcript])
  const colors = useMemo(() => speakerColors(labels), [labels])

  // A shared link like #/sessions/abc?t=95 opens at that moment of the transcript.
  const linkedIndex = transcript && t !== null ? segmentAt(transcript, t) : null
  const activeIndex = selectedIndex ?? linkedIndex

  useEffect(() => {
    if (linkedIndex === null || jumpedToLinkedTime.current) return
    jumpedToLinkedTime.current = true
    requestAnimationFrame(() => scrollToSegment(linkedIndex))
  }, [linkedIndex])

  const onRename = useCallback(
    async (label: string, name: string) => {
      await renameSpeakers(id, { [label]: name })
      setData((prev) =>
        prev?.transcript
          ? { ...prev, transcript: { ...prev.transcript, speakers: { ...prev.transcript.speakers, [label]: name } } }
          : prev,
      )
      reload()
    },
    [id, setData, reload],
  )

  const onSelect = useCallback((index: number) => {
    setSelectedIndex(index)
    scrollToSegment(index)
  }, [])

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
          <div className="transcript-panel__head">
            <h2 id="transcript-heading">Transcript</h2>
          </div>
          {transcript ? (
            <>
              <SpeakerLegend labels={labels} speakers={transcript.speakers} colors={colors} onRename={onRename} />
              <TranscriptView
                sessionId={session.id}
                transcript={transcript}
                colors={colors}
                activeIndex={activeIndex}
                onSelect={onSelect}
              />
            </>
          ) : (
            <p className="muted">The transcript appears once speakers have been identified.</p>
          )}
        </section>
      </div>
    </div>
  )
}
