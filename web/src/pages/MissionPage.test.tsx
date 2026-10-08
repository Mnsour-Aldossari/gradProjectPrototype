import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { FakeWebSocket, fakeBackend, renderApp, Reply, signedInAs, type Call } from '../test/fakes'
import { detection, FIELD_OPERATOR, mission, SUPERVISOR, telemetry } from '../test/fixtures'
import type { Detection, Mission, User } from '../types'

/** Mission 1 opened by `user`; its live link sends a snapshot of `opened` with `detections`. */
async function openMission(user: User, opened: Mission = mission(), detections: Detection[] = []) {
  const sockets = FakeWebSocket.install()
  const calls = fakeBackend(
    signedInAs(user, {
      'GET /api/health': { status: 'ok', px4_available: false },
      'GET /api/missions/1/profile': new Reply(404, { detail: 'No profile in this test' }),
      'POST /api/missions/1/control': {},
      'PATCH /api/detections/7': ({ body }: Call) =>
        detection({ ...(body as Partial<Detection>), verified_by: user.id, verified_at: '2026-10-08T08:30:00Z' }),
    }),
  )
  renderApp('/missions/1')
  await waitFor(() => expect(sockets).toHaveLength(1))
  const socket = sockets[0]
  expect(socket.url).toMatch(/\/ws\/missions\/1\?token=token-/)
  socket.serverOpens({ type: 'snapshot', mission: opened, detections, track: [], last_telemetry: null })
  await screen.findByRole('heading', { name: new RegExp(opened.name) })
  return { calls, socket }
}

const commands = (calls: Call[]) => calls.filter((c) => c.path === '/api/missions/1/control').map((c) => c.body)

describe('flight controls', () => {
  it('pause and resume the survey', async () => {
    const { calls, socket } = await openMission(SUPERVISOR)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Pause' }))
    await waitFor(() => expect(commands(calls)).toEqual([{ action: 'pause' }]))
    // The page shows Resume once the backend says the UAV holds its position.
    socket.serverSends({ type: 'mission', status: 'running', phase: 'paused', progress: 0.2, battery_pct: 97, error: null })
    await user.click(await screen.findByRole('button', { name: 'Resume' }))
    await waitFor(() => expect(commands(calls)).toEqual([{ action: 'pause' }, { action: 'resume' }]))
  })

  it('ask before Return Home and Land, and send nothing when the supervisor keeps surveying', async () => {
    const { calls } = await openMission(SUPERVISOR)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Return Home' }))
    let dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Return home?' })).toBeDefined()
    await user.click(within(dialog).getByRole('button', { name: 'Keep Surveying' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(commands(calls)).toEqual([])

    await user.click(screen.getByRole('button', { name: 'Return Home' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Return Home' }))
    await waitFor(() => expect(commands(calls)).toEqual([{ action: 'return' }]))

    await user.click(screen.getByRole('button', { name: 'Land' }))
    dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Land now?' })).toBeDefined()
    await user.click(within(dialog).getByRole('button', { name: 'Land Now' }))
    await waitFor(() => expect(commands(calls)).toEqual([{ action: 'return' }, { action: 'land' }]))
  })

  it('are not shown to the field operator', async () => {
    await openMission(FIELD_OPERATOR)
    for (const name of ['Pause', 'Resume', 'Return Home', 'Land']) {
      expect(screen.queryByRole('button', { name })).toBeNull()
    }
  })
})

describe('live updates', () => {
  it('move the UAV on the map with each telemetry event', async () => {
    const { socket } = await openMission(SUPERVISOR)
    expect(screen.getByTestId('survey-map').dataset.uav).toBe('')

    socket.serverSends({ type: 'telemetry', ...telemetry({ lat: 24.13965, lon: 47.2618 }) })
    expect(screen.getByTestId('survey-map').dataset.uav).toBe('24.13965,47.2618')

    socket.serverSends({ type: 'telemetry', ...telemetry({ t_s: 13, lat: 24.13961, lon: 47.2619, ground_speed_mps: 2.4 }) })
    expect(screen.getByTestId('survey-map').dataset.uav).toBe('24.13961,47.2619')
    expect(screen.getByText('2.4 m/s')).toBeDefined()
  })

  it('add a new detection to the list and the map', async () => {
    const { socket } = await openMission(SUPERVISOR)
    expect(screen.getByText('Nothing reported yet.')).toBeDefined()

    socket.serverSends({ type: 'detection_created', detection: detection({ id: 7 }) })
    expect(screen.getByRole('button', { name: /#7 High priority/ })).toBeDefined()
    expect(screen.getByText('1 to verify')).toBeDefined()
    expect(screen.getByTestId('survey-map').dataset.detections).toBe('7')

    socket.serverSends({ type: 'alert', detection: detection({ id: 7 }) })
    expect(screen.getByText('New high-priority potential detection')).toBeDefined()
  })
})

describe('verifying a detection', () => {
  const completed = mission({ status: 'completed', phase: null, progress: 1 })

  async function verify(choice: 'Confirmed by team' | 'False alarm', notes: string) {
    const user = userEvent.setup()
    await user.click(screen.getByRole('radio', { name: choice }))
    await user.clear(screen.getByLabelText('Field notes'))
    await user.type(screen.getByLabelText('Field notes'), notes)
    await user.click(screen.getByRole('button', { name: 'Save verification' }))
    // The detection as the backend saved it, shown on the page.
    expect(await screen.findByText(new RegExp(`^${choice} on `))).toBeDefined()
  }

  it('sends confirmed_by_team, then false_alarm, with the notes', async () => {
    const { calls } = await openMission(SUPERVISOR, completed, [detection({ id: 7 })])
    await userEvent.setup().click(screen.getByRole('button', { name: /#7 High priority/ }))

    await verify('Confirmed by team', 'Marked with a flag')
    await verify('False alarm', 'A tin can')

    expect(calls.filter((c) => c.method === 'PATCH')).toEqual([
      { method: 'PATCH', path: '/api/detections/7', body: { status: 'confirmed_by_team', notes: 'Marked with a flag' } },
      { method: 'PATCH', path: '/api/detections/7', body: { status: 'false_alarm', notes: 'A tin can' } },
    ])
  })
})
