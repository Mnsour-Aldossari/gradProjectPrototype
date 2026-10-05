import { useRef, type KeyboardEvent, type PointerEvent } from 'react'

export interface SplitterProps {
  /** 'columns': a vertical bar that sets the width of the column on its right. 'rows': a bar that sets the height above it. */
  axis: 'columns' | 'rows'
  label: string
  value: number
  min: number
  max: number
  /** Arrow-key step. */
  step: number
  /** Screen pixels per unit of value: 1 for px, innerHeight / 100 for vh. */
  pxPerUnit: () => number
  /** Called while dragging; `done` is true once, when the drag or key press ends. */
  onChange: (value: number, done: boolean) => void
  /** Double click: back to the default size. */
  onReset: () => void
}

/** A bar to drag (mouse or finger) or move with the arrow keys, between the map and the cards. */
export function Splitter({ axis, label, value, min, max, step, pxPerUnit, onChange, onReset }: SplitterProps) {
  const start = useRef<{ pos: number; value: number } | null>(null)
  const clamp = (v: number) => Math.round(Math.min(max, Math.max(min, v)))
  const pos = (e: PointerEvent) => (axis === 'columns' ? e.clientX : e.clientY)
  // Dragging the column bar to the left makes the right-hand column wider; dragging the row bar down makes the map taller.
  const sign = axis === 'columns' ? -1 : 1

  const down = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    start.current = { pos: pos(e), value }
  }
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return
    onChange(clamp(start.current.value + (sign * (pos(e) - start.current.pos)) / pxPerUnit()), false)
  }
  const up = (e: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return
    start.current = null
    onChange(clamp(value), true)
    e.currentTarget.releasePointerCapture(e.pointerId)
  }
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> =
      axis === 'columns' ? { ArrowLeft: step, ArrowRight: -step } : { ArrowUp: -step, ArrowDown: step }
    if (e.key in keys) onChange(clamp(value + keys[e.key]), true)
    else if (e.key === 'Home') onChange(min, true)
    else if (e.key === 'End') onChange(max, true)
    else return
    e.preventDefault()
  }

  return (
    <div
      className={`splitter splitter-${axis}`}
      role="separator"
      aria-orientation={axis === 'columns' ? 'vertical' : 'horizontal'}
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title={`${label}: drag, or use the arrow keys. Double-click for the default size.`}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onKeyDown={key}
      onDoubleClick={onReset}
    >
      <span className="splitter-grip" aria-hidden="true" />
    </div>
  )
}
