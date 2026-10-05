import { useEffect, useId, useRef, useState } from 'react'
import { usePrefs, type Prefs } from '../prefs'

// The menu's settings; the page layout and the field-map cards in Prefs are set on the pages themselves.
type ChoiceKey = 'theme' | 'fontSize' | 'density'

interface Group<K extends ChoiceKey> {
  key: K
  label: string
  choices: [Prefs[K], string][]
}

const THEME: Group<'theme'> = {
  key: 'theme',
  label: 'Theme',
  choices: [
    ['light', 'Light'],
    ['dark', 'Dark'],
    ['system', 'Device'],
  ],
}
const FONT_SIZE: Group<'fontSize'> = {
  key: 'fontSize',
  label: 'Text size',
  choices: [
    ['small', 'Small'],
    ['normal', 'Normal'],
    ['large', 'Large'],
  ],
}
const DENSITY: Group<'density'> = {
  key: 'density',
  label: 'Density',
  choices: [
    ['comfortable', 'Comfortable'],
    ['compact', 'Compact'],
  ],
}

function Choices<K extends ChoiceKey>({ group }: { group: Group<K> }) {
  const { prefs, setPrefs } = usePrefs()
  const labelId = useId()
  return (
    <div className="display-row">
      <span id={labelId} className="display-row-label">
        {group.label}
      </span>
      <div className={`segmented segmented-${group.choices.length}`} role="radiogroup" aria-labelledby={labelId}>
        {group.choices.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={prefs[group.key] === value}
            className={prefs[group.key] === value ? 'is-on' : ''}
            onClick={() => setPrefs({ [group.key]: value } as Partial<Prefs>)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * The "Display" button and its small menu: theme, text size and density for the signed-in user.
 * `inline` opens the menu in the page flow (field Status tab) instead of as a floating panel (sidebar).
 */
export function DisplayMenu({ inline = false }: { inline?: boolean }) {
  const { reset } = usePrefs()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return (
    <div className={`display${inline ? ' display-inline' : ''}`} ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className="display-button"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title="Display settings"
        onClick={() => setOpen((o) => !o)}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" />
        </svg>
        <span className="display-label">Display</span>
      </button>
      {open && (
        <div id={panelId} className="display-panel" role="group" aria-label="Display settings">
          <Choices group={THEME} />
          <Choices group={FONT_SIZE} />
          <Choices group={DENSITY} />
          <div className="display-foot">
            <span className="small">Saved on this device for your account.</span>
            <button type="button" className="link-button" onClick={reset}>
              Reset to default
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
