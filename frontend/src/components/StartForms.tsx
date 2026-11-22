import { useState, type FormEvent } from 'react'
import { sendBot, uploadRecording } from '../api'
import { navigate, sessionHref } from '../router'

export function UploadForm() {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!file) {
      setError('Choose an audio or video file first.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const { id } = await uploadRecording(file, title.trim() || undefined)
      navigate(sessionHref(id))
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <form className="start-form" onSubmit={onSubmit}>
      <h2>Upload recording</h2>
      <p className="start-form__hint">Audio or video of a meeting or lecture. Processing runs on this machine.</p>
      <label className="field">
        <span>File</span>
        <input
          type="file"
          accept="audio/*,video/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={busy}
        />
      </label>
      <label className="field">
        <span>Title (optional)</span>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Lecture 7: Distributed systems"
          disabled={busy}
        />
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="btn btn--primary" type="submit" disabled={busy}>
        {busy ? 'Uploading…' : 'Upload and process'}
      </button>
    </form>
  )
}

export function BotForm() {
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const link = url.trim()
    if (!/^https:\/\/meet\.google\.com\/\S+$/.test(link)) {
      setError('Paste a Google Meet link, like https://meet.google.com/abc-defg-hij.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const { id } = await sendBot(link, title.trim() || undefined)
      navigate(sessionHref(id))
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <form className="start-form" onSubmit={onSubmit}>
      <h2>Send bot to Meet link</h2>
      <p className="start-form__hint">
        The bot joins as “EchoNotes Notetaker (recording)”. Someone in the call has to admit it.
      </p>
      <label className="field">
        <span>Meet link</span>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://meet.google.com/abc-defg-hij"
          disabled={busy}
        />
      </label>
      <label className="field">
        <span>Title (optional)</span>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Weekly team sync"
          disabled={busy}
        />
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="btn btn--primary" type="submit" disabled={busy}>
        {busy ? 'Sending…' : 'Send bot'}
      </button>
    </form>
  )
}
