import './App.css'
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
        {route.page === 'session' ? <p>Session {route.id}</p> : <p>Sessions</p>}
      </main>
    </div>
  )
}

export default App
