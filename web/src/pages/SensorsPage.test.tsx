import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fakeBackend, renderApp, signedInAs, type Call } from '../test/fakes'
import { FIELD_OPERATOR } from '../test/fixtures'

const counts = (tp: number, targets: number, fp: number) => ({
  targets, tp, fn: targets - tp, fp, recall: tp / targets, precision: tp / (tp + fp), f1: 0, fp_by_cause: {}, outcomes: {},
})

const REPORT = {
  simulated: true,
  notice: 'Results on simulated data.',
  protocol: { evaluation_seeds: [2000, 2029], tuning_seeds: [1000, 1019], scenarios: 90,
    survey: { altitude_m: 1.5, speed_mps: 2, line_spacing_m: 2 }, match_radius_m: 1.5, reported_categories: 'high + suspect' },
  frozen_parameters: { baseline: { md_threshold: 0.46 }, adaptive: { k_md: 4, k_gpr: 5, body_ratio: 0.1, reliability: {} } },
  soils: [{ key: 'all', label: 'All soils' }],
  results: { baseline: { all: counts(112, 257, 150) }, adaptive: { all: counts(187, 257, 82) } },
  mandatory_tests: [],
  borderline_case: { description: '', seeds: [] },
  limitations: [],
}

function estimate({ query }: Call) {
  const q = query ?? new URLSearchParams()
  const speed = Number(q.get('speed_mps') ?? 2)
  return {
    soil_type: q.get('soil_type'), altitude_m: Number(q.get('altitude_m')), speed_mps: speed,
    line_spacing_m: Number(q.get('line_spacing_m')), recall: speed < 2 ? 0.93 : 0.77, recall_margin: 0.08,
    precision: 0.6, false_alarms_per_ha: 6.4, low_metal_recall: 0.5, surveys: 30, seeds: [3000, 3029], method: 'adaptive',
  }
}

describe('the Sensors page', () => {
  it('explains the sensors, shows the official accuracy and the estimate, in English or Arabic', async () => {
    const calls = fakeBackend(
      signedInAs(FIELD_OPERATOR, {
        'GET /api/evaluation': REPORT,
        'GET /api/accuracy': estimate,
        'GET /api/accuracy/grid': [],
      }),
    )
    const user = userEvent.setup()
    renderApp('/sensors')
    expect(await screen.findByRole('heading', { name: 'Metal detector (MD)' })).toBeDefined()
    expect(await screen.findByText('73%')).toBeDefined() // 187 of 257 mines in the official evaluation
    expect(await screen.findByText('77%')).toBeDefined() // the estimate at the standard settings
    expect(calls.some((c) => c.path === '/api/accuracy' && c.query?.get('soil_type') === 'dry_sand')).toBe(true)

    await user.click(screen.getByRole('radio', { name: 'Wet clay' }))
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/api/accuracy' && c.query?.get('soil_type') === 'wet_clay')).toBe(true),
    )
    expect(calls.some((c) => c.path === '/api/accuracy/grid' && c.query?.get('soil_type') === 'wet_clay')).toBe(true)

    await user.click(screen.getByRole('button', { name: 'اعرض الصفحة بالعربي' }))
    expect(screen.getByRole('heading', { name: 'كاشف المعادن (MD)' })).toBeDefined()
    expect(screen.getByRole('main').getAttribute('dir')).toBe('rtl')
    expect(screen.getByText('الألغام المكتشفة', { selector: 'dt' })).toBeDefined()
  })
})
