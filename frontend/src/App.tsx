import './App.css'
import { SessionPage } from './pages/SessionPage'
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
        {route.page === 'session' ? <SessionPage key={route.id} id={route.id} t={route.t} /> : <SessionsPage />}
      </main>
    </div>
  )
}

export default App
