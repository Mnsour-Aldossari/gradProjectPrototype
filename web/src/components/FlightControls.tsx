import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { FlightAction, Mission } from '../types'

const CONFIRM: Record<'return' | 'land', { title: string; text: string; button: string }> = {
  return: {
    title: 'Return home?',
    text: 'The UAV stops surveying, flies back to where the survey started and lands. The survey cannot be resumed; what was scanned so far is kept.',
    button: 'Return Home',
  },
  land: {
    title: 'Land now?',
    text: 'The UAV stops surveying and lands where it is. The survey cannot be resumed; what was scanned so far is kept.',
    button: 'Land Now',
  },
}

/** The supervisor's commands during a flight: pause or resume the survey, or end it with a return home or a landing. */
export function FlightControls({ mission }: { mission: Mission }) {
  const [sending, setSending] = useState<FlightAction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<'return' | 'land' | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const phase = mission.phase ?? 'surveying'

  useEffect(() => {
    if (confirm) dialog.current?.showModal()
    else dialog.current?.close()
  }, [confirm])

  async function send(action: FlightAction) {
    setConfirm(null)
    setSending(action)
    setError(null)
    try {
      await api(`/api/missions/${mission.id}/control`, { method: 'POST', body: { action } })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The command was not sent')
    } finally {
      setSending(null)
    }
  }

  if (phase === 'returning' || phase === 'landing') {
    return (
      <p className="small flight-ending" role="status">
        {phase === 'returning' ? 'Returning home.' : 'Landing.'} The survey ends once the UAV is on the ground.
      </p>
    )
  }

  const paused = phase === 'paused'
  return (
    <>
      <div className="flight-controls">
        <button
          type="button"
          className="button secondary"
          disabled={sending !== null}
          onClick={() => send(paused ? 'resume' : 'pause')}
        >
          {sending === 'pause' || sending === 'resume' ? 'Sending…' : paused ? 'Resume' : 'Pause'}
        </button>
        <button type="button" className="button secondary" disabled={sending !== null} onClick={() => setConfirm('return')}>
          {sending === 'return' ? 'Sending…' : 'Return Home'}
        </button>
        <button type="button" className="button danger" disabled={sending !== null} onClick={() => setConfirm('land')}>
          {sending === 'land' ? 'Sending…' : 'Land'}
        </button>
      </div>
      {paused && <p className="small flight-ending">Paused: the UAV holds its position and takes no readings.</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <dialog
        ref={dialog}
        className="confirm-dialog"
        aria-labelledby="confirm-title"
        onClose={() => setConfirm(null)}
      >
        {confirm && (
          <>
            <h2 id="confirm-title">{CONFIRM[confirm].title}</h2>
            <p>{CONFIRM[confirm].text}</p>
            <div className="confirm-actions">
              <button type="button" className="button secondary" onClick={() => setConfirm(null)}>
                Keep Surveying
              </button>
              <button
                type="button"
                className={`button${confirm === 'land' ? ' danger' : ''}`}
                onClick={() => send(confirm)}
              >
                {CONFIRM[confirm].button}
              </button>
            </div>
          </>
        )}
      </dialog>
    </>
  )
}
