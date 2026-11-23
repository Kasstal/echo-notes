import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getSession,
  isTerminal,
  renameSpeakers,
  searchSession,
  type Segment,
  type SessionDetail,
  type Status,
  type Transcript,
} from '../api'
import { SearchBox } from '../components/SearchBox'
import { SessionActions } from '../components/SessionActions'
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

  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<{ q: string; segments: Segment[]; error?: string } | null>(null)
  const [cursor, setCursor] = useState(-1)
  const hasTranscript = transcript !== null
  const q = query.trim()

  useEffect(() => {
    if (!q || !hasTranscript) return
    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        const segments = await searchSession(id, q)
        if (!cancelled) setSearch({ q, segments })
      } catch (err) {
        if (!cancelled) setSearch({ q, segments: [], error: (err as Error).message })
      }
      if (!cancelled) setCursor(-1)
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [q, id, hasTranscript])

  // Results only count while they belong to what is typed now.
  const activeSearch = q && search?.q === q ? search : null
  const matchIndices = useMemo(() => {
    if (!activeSearch || !transcript) return []
    const keys = new Set(activeSearch.segments.map((s) => `${s.start}|${s.speaker}`))
    return transcript.segments.flatMap((s, i) => (keys.has(`${s.start}|${s.speaker}`) ? [i] : []))
  }, [activeSearch, transcript])
  const matchSet = useMemo(() => new Set(matchIndices), [matchIndices])

  function stepMatch(delta: number) {
    if (matchIndices.length === 0) return
    const next = (cursor + delta + matchIndices.length) % matchIndices.length
    setCursor(next)
    onSelect(matchIndices[next])
  }

  let searchStatus: string | null = null
  if (q && !activeSearch) searchStatus = 'Searching…'
  else if (activeSearch?.error) searchStatus = activeSearch.error
  else if (activeSearch) {
    const n = matchIndices.length
    if (n === 0) searchStatus = 'No matches'
    else if (cursor >= 0) searchStatus = `${cursor + 1} of ${n} ${n === 1 ? 'match' : 'matches'}`
    else searchStatus = `${n} ${n === 1 ? 'match' : 'matches'}`
  }

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
        <SessionActions
          session={session}
          onRetryStarted={() => {
            setData((prev) => (prev ? { ...prev, status: 'summarizing', error: null } : prev))
            reload()
          }}
        />
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
            {transcript && (
              <SearchBox
                query={query}
                onQueryChange={setQuery}
                status={searchStatus}
                matchCount={matchIndices.length}
                onPrev={() => stepMatch(-1)}
                onNext={() => stepMatch(1)}
              />
            )}
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
                highlight={activeSearch ? q : ''}
                matches={matchSet}
              />
            </>
          ) : (
            <p className="muted">
              {session.status === 'failed'
                ? 'Processing failed before a transcript was written.'
                : session.status === 'recording'
                  ? 'The bot is recording. The transcript is made after it leaves the call.'
                  : 'The transcript appears once speakers have been identified.'}
            </p>
          )}
        </section>
      </div>
    </div>
  )
}
