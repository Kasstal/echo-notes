import type { Transcript } from './api'

// Chosen to stay readable as text on white and distinct from each other.
const PALETTE = ['#2f5dd0', '#b4436c', '#23806a', '#9a5b13', '#7046c0', '#c2410c', '#0e7490', '#4d7c0f']
const UNKNOWN_COLOR = '#6b7280'

export function speakerLabels(transcript: Transcript): string[] {
  const labels = new Set(Object.keys(transcript.speakers))
  for (const seg of transcript.segments) labels.add(seg.speaker)
  return [...labels].sort()
}

export function speakerColors(labels: string[]): Record<string, string> {
  const colors: Record<string, string> = {}
  let i = 0
  for (const label of labels) {
    colors[label] = label === 'UNKNOWN' ? UNKNOWN_COLOR : PALETTE[i++ % PALETTE.length]
  }
  return colors
}

export function displayName(label: string, speakers: Record<string, string>): string {
  if (speakers[label]) return speakers[label]
  if (label === 'UNKNOWN') return 'Unknown speaker'
  return label
}
