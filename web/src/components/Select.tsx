import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

export interface SelectOption<T extends string | number> {
  value: T
  label: string
  disabled?: boolean
}

/**
 * A dropdown in the app's own style (light and dark), in place of the browser's native list, which ignores the
 * theme. Select-only combobox: a button showing the choice and a listbox under it (or above it when there is no
 * room below). Keyboard: arrows, Home / End, Enter or Space to choose, Escape to close, first letter to jump.
 * Put it inside a <label> with the field's name, like a native select.
 */
export function Select<T extends string | number>({
  value,
  options,
  onChange,
  className,
  disabled = false,
}: {
  value: T
  options: SelectOption<T>[]
  onChange: (value: T) => void
  className?: string
  disabled?: boolean
}) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [above, setAbove] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const selected = Math.max(0, options.findIndex((o) => o.value === value))

  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [open, active])

  function show() {
    // Open upwards when the list would not fit below (e.g. the replay bar at the bottom of the 3D view).
    const r = button.current?.getBoundingClientRect()
    const needed = Math.min(options.length * 40 + 12, 280)
    setAbove(r ? window.innerHeight - r.bottom < needed && r.top > window.innerHeight - r.bottom : false)
    setActive(selected)
    setOpen(true)
  }

  function choose(i: number) {
    const o = options[i]
    if (!o || o.disabled) return
    if (o.value !== value) onChange(o.value)
    setOpen(false)
    button.current?.focus()
  }

  function step(from: number, dir: 1 | -1): number {
    for (let i = from + dir; i >= 0 && i < options.length; i += dir) if (!options[i].disabled) return i
    return from
  }

  function key(e: KeyboardEvent<HTMLButtonElement>) {
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        show()
      }
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => step(a, e.key === 'ArrowDown' ? 1 : -1))
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault()
      setActive(e.key === 'Home' ? step(-1, 1) : step(options.length, -1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      choose(active)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
    } else if (e.key === 'Tab') {
      setOpen(false)
    } else if (e.key.length === 1) {
      const k = e.key.toLowerCase()
      const n = options.length
      for (let j = 1; j <= n; j++) {
        const i = (active + j) % n
        if (!options[i].disabled && options[i].label.toLowerCase().startsWith(k)) {
          setActive(i)
          break
        }
      }
    }
  }

  return (
    <div className={`select${open ? ' open' : ''}${className ? ` ${className}` : ''}`} ref={root}>
      <button
        ref={button}
        type="button"
        role="combobox"
        className="select-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={key}
      >
        <span className="select-value">{options[selected]?.label}</span>
        <svg className="select-chevron" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>
      {open && (
        <ul ref={list} id={`${id}-list`} role="listbox" className={`select-list${above ? ' above' : ''}`} tabIndex={-1}>
          {options.map((o, i) => (
            <li
              key={String(o.value)}
              id={`${id}-${i}`}
              data-index={i}
              role="option"
              aria-selected={i === selected}
              aria-disabled={o.disabled || undefined}
              className={`select-option${i === active ? ' active' : ''}`}
              onPointerEnter={() => !o.disabled && setActive(i)}
              onClick={(e) => {
                e.preventDefault() // inside a <label>: do not also click the button
                choose(i)
              }}
            >
              <span>{o.label}</span>
              {i === selected && (
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M3 8.5l3.2 3L13 5" />
                </svg>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
