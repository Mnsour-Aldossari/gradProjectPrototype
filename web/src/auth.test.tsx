import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fakeBackend, renderApp, Reply, signedInAs } from './test/fakes'
import { FIELD_OPERATOR, SUPERVISOR } from './test/fixtures'

async function signIn(username: string) {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Username'), username)
  await user.type(screen.getByLabelText('Password'), 'test-password')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}

describe('signing in', () => {
  it('takes the supervisor to Missions', async () => {
    const calls = fakeBackend({
      'POST /api/auth/login': { token: 'token-supervisor', user: SUPERVISOR },
      'GET /api/missions': [],
    })
    renderApp('/login')
    await signIn('supervisor')

    expect(await screen.findByRole('heading', { name: 'Missions' })).toBeDefined()
    expect(window.location.pathname).toBe('/')
    expect(calls[0]).toEqual({
      method: 'POST',
      path: '/api/auth/login',
      body: { username: 'supervisor', password: 'test-password' },
    })
    expect(localStorage.getItem('uav.token')).toBe('token-supervisor')
  })

  it('takes the field operator to the field view', async () => {
    fakeBackend({
      'POST /api/auth/login': { token: 'token-field', user: FIELD_OPERATOR },
      'GET /api/missions': [],
    })
    renderApp('/login')
    await signIn('field')

    expect(await screen.findByRole('heading', { name: 'No missions yet' })).toBeDefined()
    expect(window.location.pathname).toBe('/field')
  })

  it('says so when the password is wrong, and stays on the sign-in page', async () => {
    fakeBackend({ 'POST /api/auth/login': new Reply(401, { detail: 'Invalid username or password' }) })
    renderApp('/login')
    await signIn('supervisor')

    expect((await screen.findByRole('alert')).textContent).toBe('Wrong username or password. Check them and try again.')
    expect(window.location.pathname).toBe('/login')
    expect(localStorage.getItem('uav.token')).toBeNull()
  })

  it('sends a field operator who opens a supervisor page to the field view', async () => {
    fakeBackend(signedInAs(FIELD_OPERATOR, { 'GET /api/missions': [] }))
    renderApp('/missions/new')

    expect(await screen.findByRole('heading', { name: 'No missions yet' })).toBeDefined()
    expect(window.location.pathname).toBe('/field')
  })
})
