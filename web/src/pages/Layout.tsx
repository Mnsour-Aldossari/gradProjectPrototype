import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { DisplayMenu } from '../components/DisplayMenu'
import { RosButton } from '../components/RosButton'

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
  sensors: 'M12 13a1 1 0 1 0 0 .01 M8.5 9.5a5 5 0 0 0 0 7 M15.5 9.5a5 5 0 0 1 0 7 M5.6 6.6a9 9 0 0 0 0 12.8 M18.4 6.6a9 9 0 0 1 0 12.8',
  database: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6 M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6',
  signOut: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3 M10 16l4-4-4-4 M14 12H4',
}

const SIM_NOTE = 'UAV flights and sensor readings are simulated. Every marker is a potential detection.'

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
  const supervisor = user?.role === 'supervisor'
  return (
    <div className="app app-top">
      <header className="topbar">
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
        {/* On a laptop the links sit in the bar; on a phone the same list is a tab bar at the bottom (redesign.css). */}
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>
            <Icon d={ICONS.missions} />
            <span className="nav-label">Missions</span>
          </NavLink>
          {supervisor && (
            <NavLink to="/missions/new" className="nav-new">
              <Icon d={ICONS.new} />
              <span className="nav-label">New mission</span>
            </NavLink>
          )}
          <NavLink to="/history">
            <Icon d={ICONS.history} />
            <span className="nav-label">History</span>
          </NavLink>
          <NavLink to="/evaluation">
            <Icon d={ICONS.evaluation} />
            <span className="nav-label">Evaluation</span>
          </NavLink>
          <NavLink to="/sensors">
            <Icon d={ICONS.sensors} />
            <span className="nav-label">Sensors</span>
          </NavLink>
          {supervisor &&
            (user.database_ui_url ? (
              <a href={user.database_ui_url} target="_blank" rel="noreferrer">
                <Icon d={ICONS.database} />
                <span className="nav-label">Database</span>
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : (
              <NavLink to="/database">
                <Icon d={ICONS.database} />
                <span className="nav-label">Database</span>
              </NavLink>
            ))}
        </nav>
        <div className="top-tools">
          <p className="sim-note" title={`Simulated data. ${SIM_NOTE}`}>
            <b>Simulated data.</b> <span className="sim-more">{SIM_NOTE}</span>
            <b className="sim-mini" aria-hidden="true">
              SIM
            </b>
          </p>
          {supervisor && <RosButton folded />}
          <DisplayMenu />
          <div className="who">
            <span className="avatar" aria-hidden="true">
              {initials(user?.full_name)}
            </span>
            <span className="who-name">
              {user?.full_name}
              <span className="role">{role}</span>
            </span>
            <button type="button" className="link-button sign-out" title="Sign out" onClick={logout}>
              <Icon d={ICONS.signOut} />
              <span className="sign-out-label">Sign out</span>
            </button>
          </div>
        </div>
      </header>
      <div className="app-main">
        <Outlet />
      </div>
    </div>
  )
}
