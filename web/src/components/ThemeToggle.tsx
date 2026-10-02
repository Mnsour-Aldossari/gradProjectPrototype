import { useEffect, useState } from 'react'
import { currentTheme, followDeviceTheme, setTheme, type Theme } from '../themePref'

/** Switches between light and dark colours. The label names the theme it switches to. */
export function ThemeToggle({ className }: { className: string }) {
  const [theme, setState] = useState<Theme>(currentTheme)

  useEffect(() => followDeviceTheme(setState), [])

  const next: Theme = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`}
      onClick={() => {
        setTheme(next)
        setState(next)
      }}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {next === 'dark' ? (
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" fill="currentColor" />
        ) : (
          <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none" />
            <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
          </g>
        )}
      </svg>
      <span className="theme-toggle-label">{next === 'dark' ? 'Dark mode' : 'Light mode'}</span>
    </button>
  )
}
