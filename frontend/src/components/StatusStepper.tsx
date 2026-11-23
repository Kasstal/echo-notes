import type { Status } from '../api'
import { STATUS_LABELS } from '../format'

const PIPELINE: Status[] = ['queued', 'normalizing', 'transcribing', 'diarizing', 'summarizing', 'done']
const BOT_PIPELINE: Status[] = ['recording', 'normalizing', 'transcribing', 'diarizing', 'summarizing', 'done']

interface Props {
  status: Status
  source: 'upload' | 'bot'
  // The last in-progress status seen before a failure, so we can show where it stopped.
  lastActive: Status | null
  hasTranscript: boolean
  hasSummary: boolean
}

type StepState = 'complete' | 'current' | 'pending' | 'failed' | 'warning'

// Where processing is, as a step index. Bot sessions go recording -> queued -> normalizing, and a
// summary retry goes back to queued with the transcript already written, so `status` alone is not
// enough to place it.
function activeIndex(steps: Status[], status: Status, source: Props['source'], hasTranscript: boolean): number {
  const summarizing = steps.indexOf('summarizing')
  if (hasTranscript && (status === 'queued' || status === 'summarizing')) return summarizing
  if (source === 'bot' && status === 'queued') return steps.indexOf('normalizing')
  return steps.indexOf(status)
}

function failedIndex(steps: Status[], source: Props['source'], props: Props): number {
  if (props.lastActive) {
    const at = activeIndex(steps, props.lastActive, source, props.hasTranscript)
    if (at >= 0) return at
  }
  // Opened after it failed: infer the step from what was written before the failure.
  if (props.hasSummary) return steps.length - 1
  if (props.hasTranscript) return steps.indexOf('summarizing')
  return source === 'bot' ? 0 : steps.indexOf('normalizing')
}

export function StatusStepper(props: Props) {
  const { status, source, hasTranscript } = props
  const steps = source === 'bot' ? BOT_PIPELINE : PIPELINE
  const doneIndex = steps.length - 1

  function stateOf(index: number): StepState {
    if (status === 'done') return 'complete'
    if (status === 'done_with_warnings') return index === doneIndex ? 'warning' : 'complete'
    if (status === 'failed') {
      const at = failedIndex(steps, source, props)
      if (index < at) return 'complete'
      if (index === at) return 'failed'
      return 'pending'
    }
    const current = activeIndex(steps, status, source, hasTranscript)
    if (index < current) return 'complete'
    if (index === current) return 'current'
    return 'pending'
  }

  return (
    <ol className="stepper" aria-label="Processing progress">
      {steps.map((step, i) => {
        const state = stateOf(i)
        const label =
          i === doneIndex && status === 'done_with_warnings' ? STATUS_LABELS.done_with_warnings : STATUS_LABELS[step]
        return (
          <li key={step} className={`stepper__step stepper__step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
            <span className="stepper__marker" aria-hidden />
            <span className="stepper__label">{label}</span>
          </li>
        )
      })}
    </ol>
  )
}
