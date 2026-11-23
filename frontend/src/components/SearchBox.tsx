interface Props {
  query: string
  onQueryChange: (query: string) => void
  status: string | null
  matchCount: number
  onPrev: () => void
  onNext: () => void
}

export function SearchBox({ query, onQueryChange, status, matchCount, onPrev, onNext }: Props) {
  return (
    <div className="search" role="search">
      <input
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && matchCount > 0) {
            e.preventDefault()
            if (e.shiftKey) onPrev()
            else onNext()
          }
        }}
        placeholder="Search this transcript"
        aria-label="Search this transcript"
      />
      {status && (
        <span className="search__status" aria-live="polite">
          {status}
        </span>
      )}
      {matchCount > 1 && (
        <span className="search__nav">
          <button className="btn btn--small" type="button" onClick={onPrev} aria-label="Previous match">
            Previous
          </button>
          <button className="btn btn--small" type="button" onClick={onNext} aria-label="Next match">
            Next
          </button>
        </span>
      )}
    </div>
  )
}
