import type { Status } from '../api'
import { STATUS_LABELS } from '../format'

const PIPELINE: Status[] = ['queued', 'normalizing', 'transcribing', 'diarizing', 'summarizing', 'done']
const BOT_PIPELINE: Status[] = ['recording', 'normalizing', 'transcribing', 'diarizing', 'summarizing', 'done']

interface Props {
  status: Status
  source: 'upload' | 'bot'
  // The last in-progress status seen before a failure, so we can show where it stopped.
  lastActive: Status | null
}

type StepState = 'complete' | 'current' | 'pending' | 'failed' | 'warning'

export function StatusStepper({ status, source, lastActive }: Props) {
  const steps = source === 'bot' ? BOT_PIPELINE : PIPELINE
  const doneIndex = steps.length - 1

  function stateOf(index: number): StepState {
    if (status === 'done') return 'complete'
    if (status === 'done_with_warnings') return index === doneIndex ? 'warning' : 'complete'
    if (status === 'failed') {
      const at = lastActive ? steps.indexOf(lastActive) : -1
      if (index < at) return 'complete'
      if (index === at) return 'failed'
      return 'pending'
    }
    const current = steps.indexOf(status)
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
