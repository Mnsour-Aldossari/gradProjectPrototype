import type { ReactNode } from 'react'

export const CARD_ICONS = {
  fold: 'M6 9l6 6 6-6',
  up: 'M12 19V5 M6 11l6-6 6 6',
  down: 'M12 5v14 M6 13l6 6 6-6',
  customize: 'M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6',
  hide: 'M3 3l18 18 M10.6 5.1A10 10 0 0 1 12 5c5 0 9 4.5 10 7a13 13 0 0 1-3 4.2 M6.6 6.6A13 13 0 0 0 2 12c1 2.5 5 7 10 7a10 10 0 0 0 5.4-1.6 M9.9 9.9a3 3 0 0 0 4.2 4.2',
}

export function Glyph({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

export interface CardFrameProps {
  /** Which card, for the page to find it again (focus after a move). */
  cardId: string
  /** Card name in the heading and in the buttons' names ("Fold Flight", "Move Flight up"). */
  title: string
  headingId: string
  /** Small text at the right of the heading, such as "3 to verify". */
  aside?: ReactNode
  folded: boolean
  onFold: () => void
  /** Customize mode: move and hide buttons in the heading. */
  editing: boolean
  first: boolean
  last: boolean
  onMove: (step: -1 | 1) => void
  /** Missing for a card that cannot be hidden. */
  onHide?: () => void
  /** Content that stays when the card is folded (Flight keeps its status and Start survey). */
  keep?: ReactNode
  children: ReactNode
}

/** A card in the mission page's column that can be folded, and moved or hidden in Customize mode. */
export function CardFrame({ cardId, title, headingId, aside, folded, onFold, editing, first, last, onMove, onHide, keep, children }: CardFrameProps) {
  return (
    <section className={`card card-pad block cfg-card${folded ? ' is-folded' : ''}${editing ? ' is-editing' : ''}`} aria-labelledby={headingId} data-card={cardId}>
      <div className="card-head">
        <h2 id={headingId}>{title}</h2>
        <div className="cfg-right">
          {aside}
          {editing && (
            <>
              <button type="button" className="cfg-tool cfg-up" aria-label={`Move ${title} up`} title="Move up" disabled={first} onClick={() => onMove(-1)}>
                <Glyph d={CARD_ICONS.up} />
              </button>
              <button type="button" className="cfg-tool cfg-down" aria-label={`Move ${title} down`} title="Move down" disabled={last} onClick={() => onMove(1)}>
                <Glyph d={CARD_ICONS.down} />
              </button>
              {onHide && (
                <button type="button" className="cfg-tool" aria-label={`Hide ${title}`} title="Hide" onClick={onHide}>
                  <Glyph d={CARD_ICONS.hide} />
                </button>
              )}
            </>
          )}
          <button
            type="button"
            className="cfg-tool cfg-fold"
            aria-expanded={!folded}
            aria-label={`${folded ? 'Unfold' : 'Fold'} ${title}`}
            title={folded ? 'Unfold' : 'Fold'}
            onClick={onFold}
          >
            <Glyph d={CARD_ICONS.fold} />
          </button>
        </div>
      </div>
      {keep}
      {!folded && children}
    </section>
  )
}
