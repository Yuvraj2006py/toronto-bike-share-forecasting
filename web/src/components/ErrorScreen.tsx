import type { ApiError } from '../api/client'
import { useMapApp } from '../state/MapAppContext'

function copyFor(error: ApiError): { title: string; body: string; command: string | null } {
  switch (error.kind) {
    case 'not-prepared':
      return {
        title: "Predictions aren't prepared yet",
        body: 'The service is running but has no prediction files. Build them once from the project folder, then retry.',
        command: 'python -m src.phase6_prep',
      }
    case 'network':
      return {
        title: "Can't reach the prediction service",
        body: 'Start the API on port 8000 (or the Docker stack), then retry.',
        command: 'uvicorn src.api:app --port 8000',
      }
    case 'not-found':
      return { title: 'That hour is outside the test month', body: error.message, command: null }
    case 'server':
      return { title: 'The prediction service hit an error', body: error.message, command: null }
    default: {
      const unreachable: never = error.kind
      return unreachable
    }
  }
}

export function ErrorScreen({ error }: { error: ApiError }) {
  const { actions } = useMapApp()
  const copy = copyFor(error)
  return (
    <main className="error-screen">
      <section className="panel error-card" role="alert" aria-labelledby="error-title">
        <p className="eyebrow">Toronto bike demand map</p>
        <h1 id="error-title">{copy.title}</h1>
        <p>{copy.body}</p>
        {copy.command && <pre className="mono"><code>{copy.command}</code></pre>}
        <div className="error-card__actions">
          <button type="button" className="btn btn--primary" onClick={actions.retry}>Retry the request</button>
          {error.kind === 'not-found' && (
            <button type="button" className="btn btn--secondary" onClick={actions.goNow}>Show my hour</button>
          )}
        </div>
      </section>
    </main>
  )
}
