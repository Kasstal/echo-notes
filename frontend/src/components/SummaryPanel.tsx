import type { Status, Summary } from '../api'

interface Props {
  summary: Summary | null | undefined
  status: Status
}

function emptyMessage(status: Status): string {
  if (status === 'summarizing') return 'Writing the summary…'
  if (status === 'done_with_warnings') return 'There is no summary for this session. Use Retry summary to try again.'
  if (status === 'failed') return 'Processing failed before a summary could be written.'
  if (status === 'done') return 'This session has no summary.'
  return 'The summary appears once the transcript is ready.'
}

export function SummaryPanel({ summary, status }: Props) {
  return (
    <section className="summary" aria-labelledby="summary-heading">
      <p className="ai-label" role="note">
        AI-generated summary — verify against the transcript
      </p>
      <h2 id="summary-heading">Summary</h2>

      {!summary && <p className="muted">{emptyMessage(status)}</p>}

      {summary && (
        <>
          {summary.tldr && <p className="summary__tldr">{summary.tldr}</p>}

          <SummaryList title="Key points" items={summary.key_points} empty="No key points." />
          <SummaryList title="Decisions" items={summary.decisions} empty="No decisions were recorded." />

          <h3>Action items</h3>
          {summary.action_items.length === 0 ? (
            <p className="muted">Nobody committed to a task.</p>
          ) : (
            <ul className="actions-list">
              {summary.action_items.map((item, i) => (
                <li key={i}>
                  <span className="actions-list__task">{item.task}</span>
                  <span className="actions-list__meta">
                    {item.owner ?? 'Owner not clear'}
                    {item.due ? `, due ${item.due}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}

function SummaryList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className="summary__list">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
    </>
  )
}
