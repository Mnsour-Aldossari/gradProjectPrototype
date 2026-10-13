import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fakeBackend, renderApp, signedInAs } from '../test/fakes'
import { mission, SUPERVISOR } from '../test/fixtures'

// 14 missions, newest first as the server sends them; every third one on wet clay.
const MISSIONS = Array.from({ length: 14 }, (_, i) => {
  const n = 14 - i
  return mission({
    id: n,
    name: `Survey block ${n}`,
    soil_type: n % 3 === 0 ? 'wet_clay' : 'dry_sand',
    status: n % 2 === 0 ? 'completed' : 'planned',
  })
})

const cards = () =>
  within(screen.getByRole('region', { name: 'All missions' }))
    .getAllByRole('link')
    .map((a) => a.textContent)
    .filter((t) => t?.startsWith('Survey block'))

describe('the Missions page', () => {
  it('pages the mission cards and filters them by name, status and soil', async () => {
    fakeBackend(signedInAs(SUPERVISOR, { 'GET /api/missions': MISSIONS }))
    const user = userEvent.setup()
    renderApp('/')

    expect(await screen.findByText('1–12 of 14')).toBeDefined()
    expect(cards()).toHaveLength(12)
    expect(screen.queryByText('Plan another survey')).toBeNull() // only after the last card
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('13–14 of 14')).toBeDefined()
    expect(cards()).toEqual(['Survey block 2', 'Survey block 1'])
    expect(window.location.search).toBe('?page=2')

    await user.type(screen.getByRole('searchbox', { name: 'Search' }), 'BLOCK 1')
    expect(cards()).toEqual(['Survey block 14', 'Survey block 13', 'Survey block 12', 'Survey block 11', 'Survey block 10', 'Survey block 1'])
    expect(screen.getByText('6 of 14')).toBeDefined()
    expect(screen.queryByRole('navigation', { name: 'Pages of missions' })).toBeNull() // back on one page

    await user.click(screen.getByRole('combobox', { name: 'Soil' }))
    await user.click(screen.getByRole('option', { name: 'Wet clay' }))
    expect(cards()).toEqual(['Survey block 12'])
    await user.click(screen.getByRole('combobox', { name: 'Status' }))
    await user.click(screen.getByRole('option', { name: 'Planned' }))
    expect(screen.getByText('No missions match these filters.')).toBeDefined()

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(cards()).toHaveLength(12)
    expect(window.location.search).toBe('')
  })
})
