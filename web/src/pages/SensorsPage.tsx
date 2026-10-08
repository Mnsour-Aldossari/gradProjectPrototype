import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { AccuracyMeter } from '../components/AccuracyMeter'
import type { AccuracyEstimate, EvaluationReport, SoilType } from '../types'

type Lang = 'en' | 'ar'
const LANG_KEY = 'uav.sensorsLang'
const SOILS: SoilType[] = ['dry_sand', 'wet_clay', 'mineralized_rocky']
const CHART_SPACINGS = [1, 2, 3] // lane spacings drawn as lines in the chart
const CHART_COLOURS = ['var(--series-adaptive)', 'var(--series-baseline)', 'var(--clutter)']
const TYPICAL_DEPTH_M = 0.1

const TEXT = {
  en: {
    title: 'Sensors: how they work and how accurate they are',
    switchTo: 'عربي',
    switchLabel: 'اعرض الصفحة بالعربي',
    simulated: 'Simulated data. The sensors and the buried objects are simulated; every marker is a potential detection for trained personnel to verify.',
    lede: 'The UAV carries two sensors and flies lanes over the area. A detector compares their readings with the ground around them and reports places worth checking.',
    sensorsHeading: 'The two sensors',
    md: {
      name: 'Metal detector (MD)',
      what: 'Senses metal under the UAV. The signal grows with the amount of metal.',
      strength: 'Weakens very fast with distance: about the cube of (height + depth). From 1.5 m down to 0.75 m it is about 6 times stronger.',
      good: 'Good at: mines with metal, at any soil moisture.',
      weak: 'Weak at: low-metal (mostly plastic) mines; it also rings on scrap metal, and mineralised soil adds noise.',
    },
    gpr: {
      name: 'Ground-penetrating radar (GPR)',
      what: 'Sends radio waves into the ground and listens for echoes from anything different from the soil around it.',
      strength: 'Sees plastic as well as metal, and the echo time gives the depth. Weakens slowly with height.',
      good: 'Good at: low-metal mines in dry soil.',
      weak: 'Weak at: wet clay, which absorbs the waves; rocks echo too, so they can look like mines.',
    },
    stepsHeading: 'From readings to a potential detection',
    steps: [
      ['Know the conditions', 'The soil, height and speed set how much each sensor is trusted.'],
      ['Compare with the surroundings', 'Each reading is compared with the ground around it (a local, adaptive threshold), not with one fixed number.'],
      ['Describe the object', 'How strong the metal and radar responses are, how they relate, and how deep the echo is.'],
      ['Group the hits', 'Readings from one buried object become one candidate.'],
      ['Decide', 'High priority, needs verification, or likely clutter, weighing each sensor by how reliable it is in this soil.'],
    ],
    officialHeading: 'How accurate it is: the official evaluation',
    officialLede: (n: number) =>
      `${n} simulated surveys at the standard settings (1.5 m, 2 m/s, 2 m lanes), on seeds kept apart from tuning. A mine counts as found when a high-priority or needs-verification marker lies within 1.5 m of it.`,
    loading: 'Running the evaluation (a few seconds the first time)…',
    soil: 'Soil',
    found: 'Mines found',
    reports: 'Reports that are mines',
    falseAlarms: 'False alarms',
    baseline: 'A fixed threshold finds',
    fullEvaluation: 'Full evaluation',
    tryHeading: 'Try the settings',
    tryLede: 'Change the height, speed and lane spacing to see what the detector is expected to find. Each setting was flown 30 times in the simulation.',
    height: 'Height',
    speed: 'Speed',
    spacing: 'Lane spacing',
    flightTime: (min: number) => `About ${min} minutes of flight per hectare (lanes only).`,
    signal: (md: string, gpr: string) => `Signal compared with 1.5 m: metal detector × ${md}, radar × ${gpr}.`,
    chartTitle: (h: number) => `Mines found by speed, at ${h} m`,
    chartLegend: (d: number) => `${d} m lanes`,
    chartX: 'Speed (m/s)',
    chartY: 'Mines found',
    limitsHeading: 'What it cannot do yet',
    limits: [
      'At the standard settings it misses about one mine in four, so it cannot declare an area clear. It points the team to where to look first.',
      'Low-metal mines are the hardest: about half are missed at the standard settings. Slower flight and closer lanes help most.',
      'In dry sand, rocks cause most false alarms: the radar sees them like mines.',
      'Flying lower makes both sensors stronger, but this detector was tuned at 1.5 m, so below that it loses some metal mines in wet clay and rocky soil.',
      'All of this is simulated. The real accuracy can only be known with real sensors over known test lanes.',
    ],
    soils: { dry_sand: 'Dry sand', wet_clay: 'Wet clay', mineralized_rocky: 'Mineralised rocky soil', all: 'All soils' },
  },
  ar: {
    title: 'الحساسات: كيف تعمل وما مدى دقتها',
    switchTo: 'English',
    switchLabel: 'Show this page in English',
    simulated: 'بيانات محاكاة. الحساسات والأجسام المدفونة محاكاة، وكل علامة هي كشف محتمل يتحقق منه فريق مدرَّب.',
    lede: 'تحمل الطائرة حساسين وتطير في خطوط فوق المنطقة. يقارن الكاشف قراءاتهما بالأرض المحيطة ويبلّغ عن الأماكن التي تستحق الفحص.',
    sensorsHeading: 'الحساسان',
    md: {
      name: 'كاشف المعادن (MD)',
      what: 'يستشعر المعدن تحت الطائرة، وتزيد الإشارة مع كمية المعدن.',
      strength: 'يضعف بسرعة كبيرة مع المسافة: تقريبًا مكعّب (الارتفاع + العمق). من 1.5 م إلى 0.75 م تصبح الإشارة أقوى بحوالي 6 مرات.',
      good: 'ممتاز في: الألغام التي فيها معدن، في أي رطوبة.',
      weak: 'ضعيف في: الألغام قليلة المعدن (أغلبها بلاستيك)، ويستجيب أيضًا للخردة المعدنية، والتربة المتمعدنة تضيف تشويشًا.',
    },
    gpr: {
      name: 'رادار اختراق الأرض (GPR)',
      what: 'يرسل موجات راديو داخل الأرض ويستقبل الصدى من أي جسم يختلف عن التربة حوله.',
      strength: 'يرى البلاستيك والمعدن، وزمن الصدى يعطي العمق. يضعف ببطء مع الارتفاع.',
      good: 'ممتاز في: الألغام قليلة المعدن في التربة الجافة.',
      weak: 'ضعيف في: الطين الرطب لأنه يمتص الموجات، والصخور تعطي صدى أيضًا فقد تشبه الألغام.',
    },
    stepsHeading: 'من القراءة إلى كشف محتمل',
    steps: [
      ['معرفة الظروف', 'نوع التربة والارتفاع والسرعة تحدد مدى الثقة في كل حساس.'],
      ['المقارنة بالمحيط', 'كل قراءة تُقارن بالأرض حولها (عتبة محلية متكيفة)، وليس برقم ثابت واحد.'],
      ['وصف الجسم', 'قوة استجابة المعدن والرادار، والعلاقة بينهما، وعمق الصدى.'],
      ['تجميع النقاط', 'القراءات القادمة من جسم واحد تصبح مرشحًا واحدًا.'],
      ['القرار', 'أولوية عالية، أو يحتاج تحقق، أو غالبًا خردة، مع وزن كل حساس حسب موثوقيته في هذه التربة.'],
    ],
    officialHeading: 'ما مدى دقته: التقييم الرسمي',
    officialLede: (n: number) =>
      `${n} مسحًا محاكى بالإعدادات القياسية (1.5 م، 2 م/ث، خطوط كل 2 م)، على بيانات منفصلة عن بيانات الضبط. يُحسب اللغم مكتشفًا إذا كانت علامة "أولوية عالية" أو "يحتاج تحقق" على بعد 1.5 م منه.`,
    loading: 'جارٍ تشغيل التقييم (ثوانٍ قليلة في المرة الأولى)…',
    soil: 'التربة',
    found: 'الألغام المكتشفة',
    reports: 'البلاغات الصحيحة',
    falseAlarms: 'إنذارات خاطئة',
    baseline: 'العتبة الثابتة تكتشف',
    fullEvaluation: 'التقييم الكامل',
    tryHeading: 'جرّب الإعدادات',
    tryLede: 'غيّر الارتفاع والسرعة والمسافة بين الخطوط لترى ما يُتوقع أن يكتشفه الكاشف. كل إعداد طُيّر 30 مرة في المحاكاة.',
    height: 'الارتفاع',
    speed: 'السرعة',
    spacing: 'المسافة بين الخطوط',
    flightTime: (min: number) => `حوالي ${min} دقيقة طيران لكل هكتار (الخطوط فقط).`,
    signal: (md: string, gpr: string) => `قوة الإشارة مقارنة بارتفاع 1.5 م: كاشف المعادن × ${md}، الرادار × ${gpr}.`,
    chartTitle: (h: number) => `الألغام المكتشفة حسب السرعة، على ارتفاع ${h} م`,
    chartLegend: (d: number) => `خطوط كل ${d} م`,
    chartX: 'السرعة (م/ث)',
    chartY: 'الألغام المكتشفة',
    limitsHeading: 'ما لا يستطيعه بعد',
    limits: [
      'بالإعدادات القياسية يفوته تقريبًا لغم من كل أربعة، فلا يمكنه إعلان أن المنطقة نظيفة. دوره أن يوجّه الفريق إلى أين يبدأ.',
      'الألغام قليلة المعدن هي الأصعب: يفوته نصفها تقريبًا بالإعدادات القياسية. الطيران الأبطأ والخطوط الأقرب يساعدان أكثر شيء.',
      'في الرمل الجاف، الصخور سبب أغلب الإنذارات الخاطئة لأن الرادار يراها مثل الألغام.',
      'الطيران الأوطى يقوّي الحساسين، لكن هذا الكاشف ضُبط على 1.5 م، فتحت ذلك يفوته بعض الألغام المعدنية في الطين الرطب والتربة الصخرية.',
      'كل هذا محاكاة. الدقة الحقيقية لا تُعرف إلا بحساسات حقيقية فوق مسارات اختبار معروفة.',
    ],
    soils: { dry_sand: 'رمل جاف', wet_clay: 'طين رطب', mineralized_rocky: 'تربة صخرية متمعدنة', all: 'كل أنواع التربة' },
  },
}

function savedLang(): Lang {
  try {
    return localStorage.getItem(LANG_KEY) === 'ar' ? 'ar' : 'en'
  } catch {
    return 'en'
  }
}

const pct = (v: number) => `${Math.round(v * 100)}%`
// The simulator's sensor models (backend/app/simulation/sensors.py): MD falls with (height + depth)^3, GPR with
// (1 + 0.4 height)^2.
const mdGain = (h: number) => ((1.5 + TYPICAL_DEPTH_M) / (h + TYPICAL_DEPTH_M)) ** 3
const gprGain = (h: number) => ((1 + 0.4 * 1.5) / (1 + 0.4 * h)) ** 2
const times = (v: number) => (v >= 10 ? v.toFixed(0) : v.toFixed(1))

export function SensorsPage() {
  const [lang, setLangState] = useState<Lang>(savedLang)
  const t = TEXT[lang]
  const [report, setReport] = useState<EvaluationReport | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)
  const [soil, setSoil] = useState<SoilType>('dry_sand')
  const [height, setHeight] = useState(1.5)
  const [speed, setSpeed] = useState(2)
  const [spacing, setSpacing] = useState(2)
  const [estimate, setEstimate] = useState<AccuracyEstimate | null>(null)
  const [grid, setGrid] = useState<AccuracyEstimate[] | null>(null)
  const [estimateError, setEstimateError] = useState<string | null>(null)

  function setLang(next: Lang) {
    setLangState(next)
    try {
      localStorage.setItem(LANG_KEY, next)
    } catch {
      // the choice then lasts until the page closes
    }
  }

  useEffect(() => {
    api<EvaluationReport>('/api/evaluation')
      .then(setReport)
      .catch((e) => setReportError(e instanceof Error ? e.message : String(e)))
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const q = new URLSearchParams({
        soil_type: soil,
        altitude_m: String(height),
        speed_mps: String(speed),
        line_spacing_m: String(spacing),
      })
      api<AccuracyEstimate>(`/api/accuracy?${q}`)
        .then((e) => {
          setEstimate(e)
          setEstimateError(null)
        })
        .catch((e) => setEstimateError(e instanceof Error ? e.message : String(e)))
    }, 150)
    return () => window.clearTimeout(timer)
  }, [soil, height, speed, spacing])

  useEffect(() => {
    api<AccuracyEstimate[]>(`/api/accuracy/grid?soil_type=${soil}`)
      .then(setGrid)
      .catch(() => setGrid(null))
  }, [soil])

  const minutesPerHa = Math.round(10_000 / spacing / speed / 60)

  return (
    <main className="page sensors-page" lang={lang} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      <div className="page-head">
        <h1>{t.title}</h1>
        <button
          type="button"
          className="button secondary"
          lang={lang === 'en' ? 'ar' : 'en'}
          aria-label={t.switchLabel}
          onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}
        >
          {t.switchTo}
        </button>
      </div>

      <div className="simulated-banner" role="note">
        <p>{t.simulated}</p>
      </div>
      <p className="lede">{t.lede}</p>

      <section className="sensors-section" aria-labelledby="sensors-two">
        <h2 id="sensors-two">{t.sensorsHeading}</h2>
        <div className="sensors-cards">
          {[t.md, t.gpr].map((s) => (
            <article key={s.name} className="card card-pad sensor-card">
              <h3>{s.name}</h3>
              <p>{s.what}</p>
              <p>{s.strength}</p>
              <p className="sensor-good">{s.good}</p>
              <p className="sensor-weak">{s.weak}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="sensors-section" aria-labelledby="sensors-steps">
        <h2 id="sensors-steps">{t.stepsHeading}</h2>
        <ol className="sensor-steps">
          {t.steps.map(([title, text]) => (
            <li key={title}>
              <b>{title}:</b> <span>{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="sensors-section" aria-labelledby="sensors-official">
        <div className="row spread">
          <h2 id="sensors-official">{t.officialHeading}</h2>
          <Link to="/evaluation">{t.fullEvaluation}</Link>
        </div>
        {reportError && <p className="error">{reportError}</p>}
        {!report && !reportError && <p className="small">{t.loading}</p>}
        {report && (
          <>
            <p className="lede">{t.officialLede(report.protocol.scenarios)}</p>
            <div className="table-scroll">
              <table className="table num-table">
                <thead>
                  <tr>
                    <th>{t.soil}</th>
                    <th>{t.found}</th>
                    <th>{t.reports}</th>
                    <th>{t.falseAlarms}</th>
                    <th>{t.baseline}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.soils.map((s) => {
                    const a = report.results.adaptive[s.key]
                    const b = report.results.baseline[s.key]
                    return (
                      <tr key={s.key} className={s.key === 'all' ? 'total' : ''}>
                        <th>{t.soils[s.key as keyof typeof t.soils] ?? s.label}</th>
                        <td className="num" dir="ltr">
                          {pct(a.recall)} <small>({a.tp}/{a.targets})</small>
                        </td>
                        <td className="num" dir="ltr">{pct(a.precision)}</td>
                        <td className="num" dir="ltr">{a.fp}</td>
                        <td className="num" dir="ltr">{pct(b.recall)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="sensors-section" aria-labelledby="sensors-try">
        <h2 id="sensors-try">{t.tryHeading}</h2>
        <p className="lede">{t.tryLede}</p>
        <div className="sensors-try card card-pad">
          <div className="sensors-controls">
            <div className="segmented compact" role="radiogroup" aria-label={t.soil}>
              {SOILS.map((s) => (
                <button key={s} type="button" role="radio" aria-checked={soil === s} className={soil === s ? 'is-on' : ''} onClick={() => setSoil(s)}>
                  {t.soils[s]}
                </button>
              ))}
            </div>
            <Slider label={t.height} unit="m" min={0.5} max={5} step={0.25} value={height} onChange={setHeight} />
            <Slider label={t.speed} unit="m/s" min={0.5} max={5} step={0.5} value={speed} onChange={setSpeed} />
            <Slider label={t.spacing} unit="m" min={0.5} max={5} step={0.5} value={spacing} onChange={setSpacing} />
            <p className="small">{t.flightTime(minutesPerHa)}</p>
            <p className="small">{t.signal(times(mdGain(height)), times(gprGain(height)))}</p>
          </div>
          <div className="sensors-result" aria-live="polite">
            {estimateError && <p className="error">{estimateError}</p>}
            {estimate && <AccuracyMeter estimate={estimate} lang={lang} />}
            {grid && <SpeedChart grid={grid} height={height} lang={lang} />}
          </div>
        </div>
      </section>

      <section className="sensors-section" aria-labelledby="sensors-limits">
        <h2 id="sensors-limits">{t.limitsHeading}</h2>
        <ul className="sensor-limits">
          {t.limits.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </section>
    </main>
  )
}

function Slider(props: {
  label: string
  unit: string
  min: number
  max: number
  step: number
  value: number
  onChange: (v: number) => void
}) {
  return (
    <label className="sensors-slider">
      <span>
        {props.label}{' '}
        <b className="num" dir="ltr">
          {props.value} {props.unit}
        </b>
      </span>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
      />
    </label>
  )
}

/** Mines found against speed at the grid height nearest the chosen one, one line per lane spacing. */
function SpeedChart({ grid, height, lang }: { grid: AccuracyEstimate[]; height: number; lang: Lang }) {
  const t = TEXT[lang]
  const heights = [...new Set(grid.map((g) => g.altitude_m))]
  const h = heights.reduce((best, x) => (Math.abs(x - height) < Math.abs(best - height) ? x : best), heights[0])
  const speeds = [...new Set(grid.map((g) => g.speed_mps))].sort((a, b) => a - b)
  const lines = CHART_SPACINGS.map((d) =>
    speeds.map((s) => grid.find((g) => g.altitude_m === h && g.speed_mps === s && g.line_spacing_m === d)!),
  )
  const W = 420
  const H = 200
  const pad = { l: 40, r: 12, t: 12, b: 34 }
  const x = (s: number) => pad.l + 14 + ((s - speeds[0]) / (speeds.at(-1)! - speeds[0])) * (W - pad.l - pad.r - 14)
  const y = (v: number) => pad.t + (1 - v) * (H - pad.t - pad.b)
  return (
    <figure className="speed-chart" dir="ltr">
      <figcaption dir={lang === 'ar' ? 'rtl' : 'ltr'}>{t.chartTitle(h)}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t.chartTitle(h)}>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} style={{ stroke: 'var(--chart-grid)' }} />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="chart-tick">
              {Math.round(v * 100)}%
            </text>
          </g>
        ))}
        {speeds.map((s) => (
          <text key={s} x={x(s)} y={H - pad.b + 16} textAnchor="middle" className="chart-tick">
            {s}
          </text>
        ))}
        <text x={(W + pad.l) / 2} y={H - 4} textAnchor="middle" className="chart-tick">
          {t.chartX}
        </text>
        {lines.map((pts, i) => (
          <g key={CHART_SPACINGS[i]} style={{ stroke: CHART_COLOURS[i], fill: CHART_COLOURS[i] }}>
            <polyline points={pts.map((p) => `${x(p.speed_mps)},${y(p.recall)}`).join(' ')} fill="none" strokeWidth={2.5} />
            {pts.map((p) => (
              <circle key={p.speed_mps} cx={x(p.speed_mps)} cy={y(p.recall)} r={3.5}>
                <title>{`${t.chartLegend(CHART_SPACINGS[i])}, ${p.speed_mps} m/s: ${pct(p.recall)}`}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>
      <ul className="chart-legend" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
        {CHART_SPACINGS.map((d, i) => (
          <li key={d}>
            <i style={{ background: CHART_COLOURS[i] }} aria-hidden="true" />
            {t.chartLegend(d)}
          </li>
        ))}
      </ul>
    </figure>
  )
}
