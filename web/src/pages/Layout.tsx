import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { DisplayMenu } from '../components/DisplayMenu'

function initials(name: string | undefined): string {
  return (name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

const ICONS = {
  missions: 'M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z M9 3v15 M15 6v15',
  new: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 8v8 M8 12h8',
  history: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 7v5l3 2',
  evaluation: 'M4 20V10 M10 20V4 M16 20v-7 M22 20H2',
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

export function Layout() {
  const { user, logout } = useAuth()
  const role = user?.role === 'supervisor' ? 'Supervisor' : 'Field operator'
  // The seed names already say the role ("Mission Supervisor"), so the role line only shows when it adds something.
  const showRole = !(user?.full_name ?? '').toLowerCase().includes(role.toLowerCase())
  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label="UAV Landmine Survey, all missions">
          <span className="brand-mark">
            <svg viewBox="0 0 24 21" aria-hidden="true">
              <path d="M12 1.5 L22.5 19.5 H1.5 Z" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="brand-text">
            UAV Landmine Survey
            <small>Detection prototype</small>
          </span>
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>
            <Icon d={ICONS.missions} />
            Missions
          </NavLink>
          {user?.role === 'supervisor' && (
            <NavLink to="/missions/new">
              <Icon d={ICONS.new} />
              New mission
            </NavLink>
          )}
          <NavLink to="/history">
            <Icon d={ICONS.history} />
            History
          </NavLink>
          <NavLink to="/evaluation">
            <Icon d={ICONS.evaluation} />
            Evaluation
          </NavLink>
        </nav>
        <div className="side-grow" />
        <p className="sim-note">
          <b>Simulated data.</b> UAV flights and sensor readings are simulated. Every marker is a potential detection.
        </p>
        <DisplayMenu />
        <div className="who">
          <span className="avatar" aria-hidden="true">
            {initials(user?.full_name)}
          </span>
          <span className="who-name">
            {user?.full_name}
            {showRole && <span className="role">{role}</span>}
          </span>
          <button type="button" className="link-button" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="app-main">
        <Outlet />
      </div>
    </div>
  )
}
