import { useCallback, useEffect, useRef, useState } from 'react'

// Loads data once, then reloads every `intervalMs` while `shouldPoll(data)` is true.
export function usePolling<T>(
  load: () => Promise<T>,
  shouldPoll: (data: T) => boolean,
  intervalMs = 3000,
) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [tick, setTick] = useState(0)
  const loadRef = useRef(load)
  const pollRef = useRef(shouldPoll)
  useEffect(() => {
    loadRef.current = load
    pollRef.current = shouldPoll
  })

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function run() {
      try {
        const next = await loadRef.current()
        if (cancelled) return
        setData(next)
        setError(null)
        if (pollRef.current(next)) timer = window.setTimeout(run, intervalMs)
      } catch (err) {
        if (cancelled) return
        setError(err as Error)
        timer = window.setTimeout(run, intervalMs)
      }
    }

    run()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [intervalMs, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, setData, error, reload }
}
