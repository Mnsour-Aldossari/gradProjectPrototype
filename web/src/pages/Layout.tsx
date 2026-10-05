import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { DisplayMenu } from '../components/DisplayMenu'
import { usePrefs } from '../prefs'

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
  fold: 'M4 4v16 M20 12H9 M13 8l-4 4 4 4',
  unfold: 'M4 4v16 M9 12h11 M16 8l4 4-4 4',
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
  // The seed names already say the role ("Mission Supervisor"), so the role line only shows when it adds something.
  const showRole = !(user?.full_name ?? '').toLowerCase().includes(role.toLowerCase())
  const { prefs, setPrefs } = usePrefs()
  // Folded to icons on a laptop; the phone header (styles.css, max-width 860px) ignores it.
  const folded = prefs.layout.sidebarCollapsed
  const setFolded = (sidebarCollapsed: boolean) => setPrefs({ layout: { ...prefs.layout, sidebarCollapsed } })
  // The link names stay for screen readers when folded; the tooltip shows them to everyone else.
  const tip = (label: string) => (folded ? label : undefined)
  return (
    <div className={`app${folded ? ' is-folded' : ''}`}>
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
          <NavLink to="/" end title={tip('Missions')}>
            <Icon d={ICONS.missions} />
            <span className="nav-label">Missions</span>
          </NavLink>
          {user?.role === 'supervisor' && (
            <NavLink to="/missions/new" title={tip('New mission')}>
              <Icon d={ICONS.new} />
              <span className="nav-label">New mission</span>
            </NavLink>
          )}
          <NavLink to="/history" title={tip('History')}>
            <Icon d={ICONS.history} />
            <span className="nav-label">History</span>
          </NavLink>
          <NavLink to="/evaluation" title={tip('Evaluation')}>
            <Icon d={ICONS.evaluation} />
            <span className="nav-label">Evaluation</span>
          </NavLink>
        </nav>
        <div className="side-grow" />
        <p className="sim-note" title={tip(`Simulated data. ${SIM_NOTE}`)}>
          <b>Simulated data.</b> <span className="sim-more">{SIM_NOTE}</span>
          <b className="sim-mini" aria-hidden="true">
            SIM
          </b>
        </p>
        <button
          type="button"
          className="side-fold"
          title={tip('Expand menu')}
          onClick={() => setFolded(!folded)}
        >
          <Icon d={folded ? ICONS.unfold : ICONS.fold} />
          <span className="side-fold-label">{folded ? 'Expand menu' : 'Collapse menu'}</span>
        </button>
        <DisplayMenu />
        <div className="who">
          <span className="avatar" aria-hidden="true">
            {initials(user?.full_name)}
          </span>
          <span className="who-name">
            {user?.full_name}
            {showRole && <span className="role">{role}</span>}
          </span>
          <button type="button" className="link-button sign-out" title={tip('Sign out')} onClick={logout}>
            <Icon d={ICONS.signOut} />
            <span className="sign-out-label">Sign out</span>
          </button>
        </div>
      </aside>
      <div className="app-main">
        <Outlet />
      </div>
    </div>
  )
}
