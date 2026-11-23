import { useState, type CSSProperties, type FormEvent } from 'react'
import { displayName } from '../speakers'

interface Props {
  labels: string[]
  speakers: Record<string, string>
  colors: Record<string, string>
  onRename: (label: string, name: string) => Promise<void>
}

export function SpeakerLegend({ labels, speakers, colors, onRename }: Props) {
  return (
    <ul className="legend" aria-label="Speakers">
      {labels.map((label) => (
        <SpeakerChip
          key={label}
          label={label}
          name={displayName(label, speakers)}
          color={colors[label]}
          renamable={label !== 'UNKNOWN'}
          onRename={onRename}
        />
      ))}
    </ul>
  )
}

interface ChipProps {
  label: string
  name: string
  color: string
  renamable: boolean
  onRename: (label: string, name: string) => Promise<void>
}

function SpeakerChip({ label, name, color, renamable, onRename }: ChipProps) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(name)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function startEditing() {
    setValue(name)
    setError(null)
    setEditing(true)
  }

  async function save(e?: FormEvent) {
    e?.preventDefault()
    const next = value.trim()
    if (!next || next === name) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await onRename(label, next)
      setEditing(false)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="legend__item" style={{ '--speaker': color } as CSSProperties}>
      <span className="legend__swatch" aria-hidden />
      {editing ? (
        <form className="legend__form" onSubmit={save}>
          <input
            aria-label={`New name for ${name}`}
            value={value}
            autoFocus
            disabled={saving}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
          />
          <button className="btn btn--small btn--primary" type="submit" disabled={saving}>
            Save
          </button>
          <button className="btn btn--small" type="button" onClick={() => setEditing(false)} disabled={saving}>
            Cancel
          </button>
          {error && <span className="legend__error" role="alert">{error}</span>}
        </form>
      ) : renamable ? (
        <button className="legend__name" type="button" onClick={startEditing} aria-label={`Rename ${name}`}>
          {name}
          <span className="legend__edit">Rename</span>
        </button>
      ) : (
        <span className="legend__name legend__name--static">{name}</span>
      )}
    </li>
  )
}
