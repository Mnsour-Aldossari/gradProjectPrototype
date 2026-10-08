import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { FakeWebSocket, fakeBackend, renderApp, signedInAs, type Call } from '../test/fakes'
import { mission, SUPERVISOR, TEST_FIELD, TEST_SHAPES } from '../test/fixtures'
import type { LatLon } from '../types'

const TOO_SMALL = 'The area is too small (1 m²); draw at least 100 m²'

/** The backend's check (POST /api/missions/check): the 1 m square is too small, anything else is fine. */
function check({ body }: Call) {
  const area = (body as { area: LatLon[] }).area
  if (JSON.stringify(area) === JSON.stringify(TEST_SHAPES['1 m square'])) {
    return { ok: false, problems: [TOO_SMALL], path: [], path_length_m: 0, width_m: 1, height_m: 1, area_m2: 1,
      estimated_duration_s: 0 }
  }
  return { ok: true, problems: [], path: [area[0], area[1]], path_length_m: 600, width_m: 30, height_m: 30,
    area_m2: 900, estimated_duration_s: 300 }
}

const checked = (calls: Call[]) =>
  calls.filter((c) => c.path === '/api/missions/check').map((c) => (c.body as { area: LatLon[] }).area)

describe('planning a mission', () => {
  it('checks each drawn outline with the backend and shows its problems', async () => {
    const calls = fakeBackend(signedInAs(SUPERVISOR, { 'POST /api/missions/check': check }))
    const user = userEvent.setup()
    renderApp('/missions/new')

    // The test field is checked as the page opens.
    expect(await screen.findByText(/Ready to survey/)).toBeDefined()
    expect(checked(calls)).toEqual([TEST_FIELD])

    await user.click(screen.getByRole('button', { name: 'Free shape' }))
    await user.click(screen.getByRole('button', { name: 'Finish drawing: 1 m square' }))
    expect(await screen.findByText(/Change the outline/)).toBeDefined()
    expect(screen.getByText(`${TOO_SMALL}.`)).toBeDefined()
    expect(checked(calls).at(-1)).toEqual(TEST_SHAPES['1 m square'])
    expect(screen.getByRole('button', { name: 'Create mission' }).hasAttribute('disabled')).toBe(true)

    await user.click(screen.getByRole('button', { name: 'Rectangle' }))
    await user.click(screen.getByRole('button', { name: 'Finish drawing: 30 m square' }))
    expect(await screen.findByText(/Ready to survey/)).toBeDefined()
    expect(checked(calls).at(-1)).toEqual(TEST_SHAPES['30 m square'])
    expect(screen.getByRole('button', { name: 'Create mission' }).hasAttribute('disabled')).toBe(false)
  })

  it('creates the mission with the drawn outline and opens it', async () => {
    FakeWebSocket.install()
    const calls = fakeBackend(
      signedInAs(SUPERVISOR, {
        'POST /api/missions/check': check,
        'POST /api/missions': ({ body }: Call) => mission({ id: 5, status: 'planned', ...(body as object) }),
        'GET /api/health': { status: 'ok' },
        'GET /api/missions/5/profile': { notes: [] },
      }),
    )
    const user = userEvent.setup()
    renderApp('/missions/new')
    await user.click(await screen.findByRole('button', { name: 'Rectangle' }))
    await user.click(screen.getByRole('button', { name: 'Finish drawing: 30 m square' }))
    const create = screen.getByRole('button', { name: 'Create mission' })
    await waitFor(() => expect(create.hasAttribute('disabled')).toBe(false))
    await user.click(create)

    await waitFor(() => expect(window.location.pathname).toBe('/missions/5'))
    const created = calls.find((c) => c.method === 'POST' && c.path === '/api/missions')
    expect(created?.body).toMatchObject({ name: 'Test field survey', area: TEST_SHAPES['30 m square'] })
  })
})
