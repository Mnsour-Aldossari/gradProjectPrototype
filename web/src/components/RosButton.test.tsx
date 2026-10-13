import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fakeBackend, renderApp, Reply, signedInAs } from '../test/fakes'
import { FIELD_OPERATOR, SUPERVISOR } from '../test/fixtures'

const OFF = { available: true, running: false, distro: 'Ubuntu-24.04', message: '' }
const ON = { ...OFF, running: true, message: 'ROS 2 started' }

describe("the menu's ROS 2 switch", () => {
  it('starts and stops ROS 2 for the supervisor', async () => {
    const calls = fakeBackend(
      signedInAs(SUPERVISOR, {
        'GET /api/missions': [],
        'GET /api/ros': OFF,
        'POST /api/ros/start': ON,
        'POST /api/ros/stop': { ...OFF, message: 'ROS 2 stopped' },
      }),
    )
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'ROS 2 Off' }))
    expect((await screen.findByRole('button', { name: 'ROS 2 On' })).getAttribute('aria-pressed')).toBe('true')
    await user.click(screen.getByRole('button', { name: 'ROS 2 On' }))
    expect(await screen.findByRole('button', { name: 'ROS 2 Off' })).toBeDefined()
    expect(calls.filter((c) => c.path.startsWith('/api/ros/')).map((c) => c.path)).toEqual([
      '/api/ros/start',
      '/api/ros/stop',
    ])
  })

  it("says why ROS 2 did not start", async () => {
    fakeBackend(
      signedInAs(SUPERVISOR, {
        'GET /api/missions': [],
        'GET /api/ros': OFF,
        'POST /api/ros/start': new Reply(502, { detail: 'ROS 2 is not built in WSL: run bash ros2_ws/build.sh once' }),
      }),
    )
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'ROS 2 Off' }))
    expect(await screen.findByText(/ROS 2 is not built in WSL/)).toBeDefined()
  })

  it('is not there without WSL', async () => {
    fakeBackend(signedInAs(SUPERVISOR, { 'GET /api/missions': [], 'GET /api/ros': { ...OFF, available: false } }))
    renderApp('/')
    expect(await screen.findByRole('link', { name: 'History' })).toBeDefined()
    expect(screen.queryByRole('button', { name: /ROS 2/ })).toBeNull()
  })

  it('is not shown to the field operator', async () => {
    const calls = fakeBackend(signedInAs(FIELD_OPERATOR, { 'GET /api/missions': [] }))
    renderApp('/history')
    expect(await screen.findByRole('link', { name: 'History' })).toBeDefined()
    expect(screen.queryByRole('button', { name: /ROS 2/ })).toBeNull()
    expect(calls.some((c) => c.path === '/api/ros')).toBe(false)
  })
})
