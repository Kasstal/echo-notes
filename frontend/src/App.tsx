import './App.css'
import { SessionsPage } from './pages/SessionsPage'
import { useHashRoute } from './router'

function App() {
  const route = useHashRoute()

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#/">
          EchoNotes
        </a>
      </header>
      <main className="page">
        {route.page === 'session' ? <p>Session {route.id}</p> : <SessionsPage />}
      </main>
    </div>
  )
}

export default App
