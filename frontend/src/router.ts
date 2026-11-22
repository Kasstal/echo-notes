import { useEffect, useState } from 'react'

export type Route =
  | { page: 'sessions' }
  | { page: 'session'; id: string; t: number | null }

export function parseHash(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#/, '').split('?')
  const match = path.match(/^\/sessions\/([^/]+)\/?$/)
  if (match) {
    const t = new URLSearchParams(query).get('t')
    return { page: 'session', id: decodeURIComponent(match[1]), t: t === null ? null : Number(t) }
  }
  return { page: 'sessions' }
}

export function sessionHref(id: string, t?: number): string {
  const base = `#/sessions/${encodeURIComponent(id)}`
  return t === undefined ? base : `${base}?t=${Math.floor(t)}`
}

export function navigate(hash: string) {
  window.location.hash = hash
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      const next = parseHash(window.location.hash)
      setRoute((prev) => {
        const samePage = prev.page === 'session' && next.page === 'session' && prev.id === next.id
        if (!samePage) window.scrollTo(0, 0)
        return next
      })
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
