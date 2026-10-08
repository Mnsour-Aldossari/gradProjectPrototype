import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { fakeBackend, renderApp, signedInAs, type Call } from '../test/fakes'
import { SUPERVISOR, TEST_FIELD } from '../test/fixtures'

const estimate = (altitude_m: number) => ({
  soil_type: 'dry_sand', altitude_m, speed_mps: 2, line_spacing_m: 2, recall: altitude_m === 1.5 ? 0.767 : 0.5,
  recall_margin: 0.087, precision: 0.595, false_alarms_per_ha: 6.43, low_metal_recall: 0.533, surveys: 30,
  seeds: [3000, 3029], method: 'adaptive',
})

describe('the expected accuracy while planning', () => {
  it('shows what the backend expects with the chosen settings', async () => {
    const calls = fakeBackend(
      signedInAs(SUPERVISOR, {
        'POST /api/missions/check': ({ body }: Call) => ({
          ok: true, problems: [], path: [TEST_FIELD[0], TEST_FIELD[1]], path_length_m: 600, width_m: 60, height_m: 40,
          area_m2: 2400, estimated_duration_s: 300, accuracy: estimate((body as { altitude_m: number }).altitude_m),
        }),
      }),
    )
    renderApp('/missions/new')
    expect(await screen.findByText('Expected detection with these settings')).toBeDefined()
    expect(screen.getByText('77%')).toBeDefined()
    expect(screen.getByText(/About 6.4 false alarms per hectare/)).toBeDefined()
    expect((calls.find((c) => c.path === '/api/missions/check')!.body as { altitude_m: number }).altitude_m).toBe(1.5)
  })
})
