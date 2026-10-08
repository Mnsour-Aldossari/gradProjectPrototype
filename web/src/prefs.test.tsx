import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fakeBackend, renderApp, signedInAs } from './test/fakes'
import { FIELD_OPERATOR, SUPERVISOR } from './test/fixtures'

const root = document.documentElement

describe('display settings', () => {
  it('are saved for the user and come back when the app is opened again', async () => {
    fakeBackend(signedInAs(SUPERVISOR, { 'GET /api/missions': [] }))
    const user = userEvent.setup()
    const { unmount } = renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Display' }))
    await user.click(screen.getByRole('radio', { name: 'Dark' }))
    await user.click(screen.getByRole('radio', { name: 'Large' }))
    expect([root.dataset.theme, root.dataset.font]).toEqual(['dark', 'large'])
    expect(JSON.parse(localStorage.getItem('uav.prefs.v1.supervisor')!)).toMatchObject({ theme: 'dark', fontSize: 'large' })

    // Closed and opened again, as after a reload.
    unmount()
    delete root.dataset.theme
    delete root.dataset.font
    renderApp('/')
    await screen.findByRole('heading', { name: 'Missions' })
    expect([root.dataset.theme, root.dataset.font]).toEqual(['dark', 'large'])
    await user.click(screen.getByRole('button', { name: 'Display' }))
    expect(screen.getByRole('radio', { name: 'Dark' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('radio', { name: 'Large' }).getAttribute('aria-checked')).toBe('true')
  })

  it('belong to each user: another user on the same device starts from the defaults', async () => {
    localStorage.setItem('uav.prefs.v1.supervisor', JSON.stringify({ theme: 'dark', fontSize: 'large' }))
    fakeBackend(signedInAs(FIELD_OPERATOR, { 'GET /api/missions': [] }))
    renderApp('/field')

    await screen.findByRole('heading', { name: 'No missions yet' })
    expect([root.dataset.theme, root.dataset.font]).toEqual(['light', 'normal'])
  })

  it('go back to light and normal text with Reset to default', async () => {
    localStorage.setItem('uav.prefs.v1.supervisor', JSON.stringify({ theme: 'dark', fontSize: 'small' }))
    fakeBackend(signedInAs(SUPERVISOR, { 'GET /api/missions': [] }))
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Display' }))
    expect([root.dataset.theme, root.dataset.font]).toEqual(['dark', 'small'])
    await user.click(screen.getByRole('button', { name: 'Reset to default' }))
    expect([root.dataset.theme, root.dataset.font]).toEqual(['light', 'normal'])
    expect(localStorage.getItem('uav.prefs.v1.supervisor')).toBeNull()
  })
})
