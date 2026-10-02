import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { ThemeToggle } from '../components/ThemeToggle'

export function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="UAV Landmine Survey, all missions">
          <svg viewBox="0 0 24 21" aria-hidden="true">
            <path d="M12 1.5 L22.5 19.5 H1.5 Z" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
          </svg>
          <span className="brand-text">UAV Landmine Survey</span>
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>
            Missions
          </NavLink>
          {user?.role === 'supervisor' && <NavLink to="/missions/new">New mission</NavLink>}
          <NavLink to="/history">History</NavLink>
          <NavLink to="/evaluation">Evaluation</NavLink>
        </nav>
        <div className="who">
          <span className="who-name">
            {user?.full_name}
            <span className="role">{user?.role === 'supervisor' ? 'Supervisor' : 'Field operator'}</span>
          </span>
          <ThemeToggle className="link-button" />
          <button type="button" className="link-button" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
