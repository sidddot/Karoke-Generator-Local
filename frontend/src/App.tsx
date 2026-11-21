import { Outlet, NavLink } from 'react-router-dom'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <span className="app-logo">🎤 KarokeGen</span>
        <nav>
          <NavLink to="/" end>Library</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
