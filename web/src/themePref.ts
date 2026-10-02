// Light or dark colours. index.html applies the stored choice (or the device setting) before the first paint;
// this module keeps it in sync afterwards. Keep the key and the colours in sync with index.html.
export type Theme = 'light' | 'dark'

const THEME_KEY = 'uav.theme'
const CHROME: Record<Theme, string> = { light: '#1d2a24', dark: '#0b100e' }

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_KEY)
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null
  }
}

function deviceTheme(): Theme {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', CHROME[theme])
}

/** Saves an explicit choice; from then on the device setting no longer applies. */
export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // Without storage the choice lasts until the page is reloaded.
  }
  applyTheme(theme)
}

/** Follows the device setting while the user has not chosen; returns a cleanup function. */
export function followDeviceTheme(onChange: (theme: Theme) => void): () => void {
  applyTheme(stored() ?? deviceTheme())
  let query: MediaQueryList
  try {
    query = window.matchMedia('(prefers-color-scheme: dark)')
  } catch {
    return () => {}
  }
  const listener = () => {
    if (stored() !== null) return
    applyTheme(deviceTheme())
    onChange(currentTheme())
  }
  query.addEventListener('change', listener)
  return () => query.removeEventListener('change', listener)
}
