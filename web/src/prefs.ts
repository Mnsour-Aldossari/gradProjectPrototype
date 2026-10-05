import { createContext, createElement, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import { useAuth } from './auth'

/**
 * Display preferences, kept per user on this device. They change how pages look, never what a user may see.
 * Storage can be unavailable (private mode); every read and write is guarded and falls back to the defaults.
 */
export type ThemePref = 'light' | 'dark' | 'system'
export type FontSizePref = 'small' | 'normal' | 'large'
export type DensityPref = 'comfortable' | 'compact'
/** Cards on the field map (the Map tab of /field) that the user can hide. */
export type FieldPanel = 'mission' | 'detections' | 'nearest' | 'key' | 'drone'
export interface FieldLayers {
  labels: boolean // detection numbers next to their markers
  guide: boolean // line from the user's position to the nearest detection
}

/** The cards in the right-hand column of the mission page, in their default order. */
export type MissionCard = 'flight' | 'sensors' | 'detections' | 'profile'
export const MISSION_CARDS: MissionCard[] = ['flight', 'sensors', 'detections', 'profile']
/** What the mission page can hide: the column cards except Flight (it holds Start survey), and the summary row. */
export type MissionHideable = Exclude<MissionCard, 'flight'> | 'summary'
const MISSION_HIDEABLE: MissionHideable[] = ['sensors', 'detections', 'profile', 'summary']

/** Limits for the sizes set with the splitter: column width in px (laptop), map height in % of the screen (phone). */
export const SIDE_WIDTH = { min: 300, max: 640, initial: 380 }
export const MAP_HEIGHT = { min: 40, max: 80, initial: 58 }

export interface MissionLayout {
  order: MissionCard[]
  hidden: MissionHideable[]
  collapsed: MissionCard[]
  /** null keeps the stylesheet's size. */
  sideWidth: number | null
  mapHeight: number | null
}

export interface PageLayout {
  sidebarCollapsed: boolean
  mission: MissionLayout
}

export interface Prefs {
  theme: ThemePref
  fontSize: FontSizePref
  density: DensityPref
  layout: PageLayout
  fieldHidden: FieldPanel[]
  fieldLayers: FieldLayers
}

export const DEFAULT_MISSION_LAYOUT: MissionLayout = {
  order: MISSION_CARDS,
  hidden: [],
  collapsed: [],
  sideWidth: null,
  mapHeight: null,
}

export const DEFAULT_PREFS: Prefs = {
  theme: 'light',
  fontSize: 'normal',
  density: 'comfortable',
  layout: { sidebarCollapsed: false, mission: DEFAULT_MISSION_LAYOUT },
  fieldHidden: [],
  fieldLayers: { labels: true, guide: true },
}

const THEMES: ThemePref[] = ['light', 'dark', 'system']
const FONT_SIZES: FontSizePref[] = ['small', 'normal', 'large']
const DENSITIES: DensityPref[] = ['comfortable', 'compact']
export const FIELD_PANELS: FieldPanel[] = ['mission', 'detections', 'nearest', 'key', 'drone']

function pick<T extends string>(value: unknown, allowed: T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}

/** Known names only, each once. */
function pickList<T extends string>(value: unknown, allowed: T[]): T[] {
  return Array.isArray(value) ? allowed.filter((a) => value.includes(a)) : []
}

function pickSize(value: unknown, limits: { min: number; max: number }): number | null {
  return typeof value === 'number' && value >= limits.min && value <= limits.max ? Math.round(value) : null
}

function parseMissionLayout(value: unknown): MissionLayout {
  const stored = (value && typeof value === 'object' ? value : {}) as Partial<Record<keyof MissionLayout, unknown>>
  // The stored order first, then any card it does not name (an older entry), in the default order.
  const order = Array.isArray(stored.order)
    ? [...new Set(stored.order.filter((c): c is MissionCard => MISSION_CARDS.includes(c as MissionCard)))]
    : []
  return {
    order: [...order, ...MISSION_CARDS.filter((c) => !order.includes(c))],
    hidden: pickList(stored.hidden, MISSION_HIDEABLE),
    collapsed: pickList(stored.collapsed, MISSION_CARDS),
    sideWidth: pickSize(stored.sideWidth, SIDE_WIDTH),
    mapHeight: pickSize(stored.mapHeight, MAP_HEIGHT),
  }
}

function parseLayout(value: unknown): PageLayout {
  const stored = (value && typeof value === 'object' ? value : {}) as Partial<Record<keyof PageLayout, unknown>>
  return { sidebarCollapsed: stored.sidebarCollapsed === true, mission: parseMissionLayout(stored.mission) }
}

const userKey = (username: string) => `uav.prefs.v1.${username}`
// The preferences last applied on this device, read by the script in index.html before the first paint.
const LAST_KEY = 'uav.prefs.last'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // Without storage the preferences last until the page is reloaded.
  }
}

/** Stored values are checked one by one, so an old or edited entry cannot break the page. */
function parse(raw: string | null): Prefs {
  let stored: Partial<Record<keyof Prefs, unknown>> = {}
  try {
    const value: unknown = raw ? JSON.parse(raw) : null
    if (value && typeof value === 'object') stored = value
  } catch {
    // unreadable entry: defaults
  }
  const hidden = Array.isArray(stored.fieldHidden) ? (stored.fieldHidden as unknown[]) : []
  const layers =
    stored.fieldLayers && typeof stored.fieldLayers === 'object' ? (stored.fieldLayers as Record<string, unknown>) : {}
  return {
    theme: pick(stored.theme, THEMES, DEFAULT_PREFS.theme),
    fontSize: pick(stored.fontSize, FONT_SIZES, DEFAULT_PREFS.fontSize),
    density: pick(stored.density, DENSITIES, DEFAULT_PREFS.density),
    layout: parseLayout(stored.layout),
    fieldHidden: FIELD_PANELS.filter((p) => hidden.includes(p)),
    fieldLayers: {
      labels: typeof layers.labels === 'boolean' ? layers.labels : DEFAULT_PREFS.fieldLayers.labels,
      guide: typeof layers.guide === 'boolean' ? layers.guide : DEFAULT_PREFS.fieldLayers.guide,
    },
  }
}

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

function apply(prefs: Prefs): void {
  const root = document.documentElement
  root.dataset.theme = prefs.theme === 'system' ? (darkQuery().matches ? 'dark' : 'light') : prefs.theme
  // The browser bar matches the page header (--surface in styles.css, and the script in index.html).
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', root.dataset.theme === 'dark' ? '#111a2b' : '#ffffff')
  // styles.css scales text with --text-scale and spacing with --density for these values.
  root.dataset.font = prefs.fontSize
  root.dataset.density = prefs.density
  write(LAST_KEY, JSON.stringify(prefs))
}

interface PrefsState {
  prefs: Prefs
  setPrefs: (change: Partial<Prefs>) => void
  /** Changes part of the mission page layout; the rest of the preferences stay. */
  setMissionLayout: (change: Partial<MissionLayout>) => void
  /** Resets everything: display and page layouts ("Reset to default"). */
  reset: () => void
}

const PrefsContext = createContext<PrefsState | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const username = user?.username ?? null
  // Before sign-in (login page) the page keeps what this device showed last.
  const [prefs, setPrefsState] = useState<Prefs>(() => parse(read(LAST_KEY)))

  useEffect(() => {
    if (username) setPrefsState(parse(read(userKey(username))))
  }, [username])

  useLayoutEffect(() => {
    apply(prefs)
    if (prefs.theme !== 'system') return
    const query = darkQuery()
    const follow = () => apply(prefs)
    query.addEventListener('change', follow)
    return () => query.removeEventListener('change', follow)
  }, [prefs])

  const setPrefs = useCallback(
    (change: Partial<Prefs>) => {
      const next = { ...prefs, ...change }
      if (username) write(userKey(username), JSON.stringify(next))
      setPrefsState(next)
    },
    [prefs, username],
  )

  const setMissionLayout = useCallback(
    (change: Partial<MissionLayout>) =>
      setPrefs({ layout: { ...prefs.layout, mission: { ...prefs.layout.mission, ...change } } }),
    [prefs.layout, setPrefs],
  )

  const reset = useCallback(() => {
    if (username) write(userKey(username), null)
    setPrefsState(DEFAULT_PREFS)
  }, [username])

  const value = useMemo(() => ({ prefs, setPrefs, setMissionLayout, reset }), [prefs, setPrefs, setMissionLayout, reset])
  return createElement(PrefsContext.Provider, { value }, children)
}

export function usePrefs(): PrefsState {
  const ctx = useContext(PrefsContext)
  if (!ctx) throw new Error('usePrefs must be used inside PrefsProvider')
  return ctx
}
