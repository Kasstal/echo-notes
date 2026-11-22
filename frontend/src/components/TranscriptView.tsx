import type { CSSProperties, MouseEvent } from 'react'
import type { Transcript } from '../api'
import { formatTimestamp, segmentDomId } from '../format'
import { sessionHref } from '../router'
import { displayName } from '../speakers'

interface Props {
  sessionId: string
  transcript: Transcript
  colors: Record<string, string>
  activeIndex: number | null
  onSelect: (index: number) => void
}

export function TranscriptView({ sessionId, transcript, colors, activeIndex, onSelect }: Props) {
  if (transcript.segments.length === 0) {
    return <p className="muted">No speech was detected in this recording.</p>
  }

  function select(e: MouseEvent<HTMLAnchorElement>, index: number) {
    e.preventDefault()
    // replaceState keeps the link shareable without adding a history entry per click.
    window.history.replaceState(null, '', sessionHref(sessionId, transcript.segments[index].start))
    onSelect(index)
  }

  return (
    <ol className="transcript">
      {transcript.segments.map((seg, i) => {
        const prev = transcript.segments[i - 1]
        const showName = !prev || prev.speaker !== seg.speaker
        const classes = ['seg']
        if (showName) classes.push('seg--turn')
        if (i === activeIndex) classes.push('seg--active')
        return (
          <li
            key={i}
            id={segmentDomId(i)}
            className={classes.join(' ')}
            style={{ '--speaker': colors[seg.speaker] } as CSSProperties}
          >
            <a className="seg__time" href={sessionHref(sessionId, seg.start)} onClick={(e) => select(e, i)}>
              {formatTimestamp(seg.start)}
            </a>
            <div className="seg__body">
              {showName && <span className="seg__speaker">{displayName(seg.speaker, transcript.speakers)}</span>}
              <p className="seg__text">{seg.text}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
