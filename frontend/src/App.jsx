import { useEffect, useMemo, useState } from 'react'
import './App.css'

const N_DRIVERS = 5
const N_CONS = 2
const fmtPrice = (v) => `$${v.toFixed(1)}M`

const PREDICTORS = [
  { id: 'naive', label: 'Simple — season average',
    desc: 'Expects each driver to score their season average. Simplest, and hardest to beat.' },
  { id: 'heuristic', label: 'Form & track',
    desc: 'Adjusts the average for recent form, circuit history, and reliability.' },
  { id: 'ml', label: 'Pace-aware (ML)',
    desc: 'Trained model using qualifying & race-pace — best at overall ranking.' },
]
const PRED_SHORT = { naive: 'Simple', heuristic: 'Form & track', ml: 'Pace-aware' }

const CHIP_INFO = {
  wildcard: { label: 'Wildcard', desc: 'Unlimited free transfers for one race.' },
  limitless: { label: 'Limitless', desc: 'No budget cap for one race.' },
  extra_drs: { label: 'Extra DRS', desc: 'Triples one driver’s points (3×).' },
  no_negative: { label: 'No Negative', desc: 'Negative driver scores count as zero.' },
  final_fix: { label: 'Final Fix', desc: 'Swap one pick after qualifying.' },
  auto_pilot: { label: 'Auto Pilot', desc: 'Auto-picks your boost (mobile).' },
}

const fmtDate = (iso) => {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined,
    { month: 'short', day: 'numeric', year: 'numeric' })
}

function Info({ text }) {
  return <span className="info" tabIndex={0} title={text} aria-label={text}>i</span>
}

function Trend({ move }) {
  if (move === undefined || Math.abs(move) < 0.03)
    return <span className="trend flat" title="Price expected to stay about the same">→</span>
  const up = move > 0
  return (
    <span className={`trend ${up ? 'up' : 'down'}`}
      title={`Price projected to ${up ? 'rise' : 'fall'} ~$${Math.abs(move)}M before the next race`}>
      {up ? '↑' : '↓'}
    </span>
  )
}

function Toggle({ checked, onChange, label, tip }) {
  return (
    <label className="toggle">
      <span className="toggle-text">{label}{tip && <Info text={tip} />}</span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch" aria-hidden="true"><span className="knob" /></span>
    </label>
  )
}

function ModeBanner({ teamComplete, onOpenTeam }) {
  if (teamComplete) {
    return (
      <div className="mode-banner transfer">
        <span><b>Transfer mode.</b> Advice is tailored to your team — the
          {' '}<span className="tag tag-in">BUY</span> / <span className="tag tag-out">SELL</span>
          {' '}tags show exactly what to change this race.</span>
        <button className="link" onClick={onOpenTeam}>Edit team</button>
      </div>
    )
  }
  return (
    <div className="mode-banner build">
      <span><b>Showing the ideal team to build from scratch.</b> Already playing?
        Add your current team to get personalised <b>buy / sell</b> transfer advice instead.</span>
      <button className="link" onClick={onOpenTeam}>＋ Add my team</button>
    </div>
  )
}

function useApi(url) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!url) return
    let live = true
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [url])
  return [data, error]
}

/* ----- Inputs (progressive disclosure) --------------------------------- */
function OptionsPanel({ predictor, setPredictor, drsBoost, setDrsBoost,
  freeTransfers, setFreeTransfers, budget, setBudget, gameday, refresh, refreshing }) {
  const desc = PREDICTORS.find((p) => p.id === predictor)?.desc
  return (
    <div className="panel fade-up">
      <div className="field">
        <label htmlFor="pred">Prediction method <Info text="How each pick's points are estimated." /></label>
        <div className="select-wrap">
          <select id="pred" value={predictor} onChange={(e) => setPredictor(e.target.value)}>
            {PREDICTORS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </div>
        {desc && <p className="field-hint">{desc}</p>}
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor="ft">Free transfers <Info text="Free changes this race; extras cost 10 pts each." /></label>
          <input id="ft" className="num" type="number" min="0" value={freeTransfers}
            onChange={(e) => setFreeTransfers(Math.max(0, +e.target.value))} />
        </div>
        <div className="field">
          <label htmlFor="bud">Budget ($M) <Info text="Team value + bank. Defaults to the 100M cap." /></label>
          <input id="bud" className="num" type="number" min="0" step="0.1" value={budget}
            placeholder={gameday ? String(gameday.budget) : '100'}
            onChange={(e) => setBudget(e.target.value)} />
        </div>
      </div>
      <Toggle checked={drsBoost} onChange={setDrsBoost} label="Use DRS Boost"
        tip="Free power-up that doubles one driver's points each race." />
      {!gameday?.read_only && (
        <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
          {refreshing ? 'Refreshing…' : '↻ Refresh data'}
        </button>
      )}
    </div>
  )
}

function TeamSlots({ pool, driverSlots, consSlots, setDriver, setCons, clear }) {
  const drivers = pool.filter((p) => p.entity_type === 'driver')
  const cons = pool.filter((p) => p.entity_type === 'constructor')
  const used = new Set([...driverSlots, ...consSlots].filter(Boolean))

  const renderSlot = (items, value, onChange, placeholder, key) => {
    const opts = items.filter((p) => p.fantasy_id === value || !used.has(p.fantasy_id))
    return (
      <div className="select-wrap slot" key={key}>
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">{placeholder}</option>
          {opts.map((p) => (
            <option key={p.fantasy_id} value={p.fantasy_id}>{p.name} · {fmtPrice(p.price)}</option>
          ))}
        </select>
      </div>
    )
  }

  return (
    <div className="panel fade-up">
      <p className="panel-lead">Pick the team you have now — we’ll suggest the best transfers.</p>
      <div className="slots-group">
        <div className="slots-head">Drivers <span>{driverSlots.filter(Boolean).length}/{N_DRIVERS}</span></div>
        {driverSlots.map((v, i) => renderSlot(drivers, v, (val) => setDriver(i, val), `Driver ${i + 1}`, 'd' + i))}
      </div>
      <div className="slots-group">
        <div className="slots-head">Constructors <span>{consSlots.filter(Boolean).length}/{N_CONS}</span></div>
        {consSlots.map((v, i) => renderSlot(cons, v, (val) => setCons(i, val), `Constructor ${i + 1}`, 'c' + i))}
      </div>
      {used.size > 0 && <button className="btn-text" onClick={clear}>Clear all</button>}
    </div>
  )
}

/* ----- Result ---------------------------------------------------------- */
function PickRow({ pick, rank, boosted, mult, badge, move }) {
  return (
    <div className={`pick ${boosted ? 'boosted' : ''}`}>
      <div className="pick-rank">{rank}</div>
      <div className="pick-main">
        <div className="pick-name">
          {pick.name}
          {boosted && <span className="tag tag-drs" title={`Points ×${mult}`}>DRS {mult}×</span>}
          {badge && <span className={`tag tag-${badge}`}>{badge === 'in' ? 'BUY' : 'SELL'}</span>}
        </div>
        <div className="pick-sub">
          <span className="pick-price">{fmtPrice(pick.price)}<Trend move={move} /></span>
          {pick.std > 0 && (
            <span className="pick-range" title="Likely range — worst to best case">
              {pick.floor}–{pick.ceiling} pts
            </span>
          )}
        </div>
      </div>
      <div className="pick-pts">
        <span className="pts-num">{pick.expected_points.toFixed(1)}</span>
        <span className="pts-unit">pts</span>
      </div>
    </div>
  )
}

function Stat({ value, sub, label, tip, accent }) {
  return (
    <div className={`stat ${accent ? 'accent' : ''}`}>
      <div className="stat-value">{value}{sub && <span className="stat-sub">{sub}</span>}</div>
      <div className="stat-label">{label}{tip && <Info text={tip} />}</div>
    </div>
  )
}

function Lineup({ data, teamActive, projections }) {
  const pct = Math.min((data.total_price / data.budget) * 100, 100)
  const over = data.total_price > data.budget
  const inIds = new Set(data.transfers_in.map((p) => p.fantasy_id))
  const drivers = data.drivers.slice().sort((a, b) => b.expected_points - a.expected_points)
  const cons = data.constructors.slice().sort((a, b) => b.expected_points - a.expected_points)

  return (
    <section className="results fade-up">
      <div className="results-head">
        <h2 className="section-title">{teamActive ? 'Suggested changes' : 'Your optimal team'}</h2>
      </div>

      <div className="stats">
        <Stat value={data.net_points.toFixed(0)} accent label="projected pts"
          tip="Points expected next race, after any transfer penalty." />
        <Stat value={fmtPrice(data.total_price)} label={`of ${fmtPrice(data.budget)}`} />
        {teamActive && (
          <Stat value={data.num_transfers} sub={data.penalty > 0 ? ` −${data.penalty}` : null}
            label="transfers" tip="Changes beyond your free ones cost 10 pts each." />
        )}
      </div>

      <div className="budget">
        <div className="budget-track"><div className={`budget-fill ${over ? 'over' : ''}`} style={{ width: `${pct}%` }} /></div>
        <span className="budget-text">{Math.round(pct)}% of budget used</span>
      </div>

      {teamActive && data.num_transfers > 0 && (
        <div className="transfers">
          <span className="transfer t-out">SELL&nbsp; {data.transfers_out.map((p) => p.name).join(', ') || '—'}</span>
          <span className="transfer t-in">BUY&nbsp; {data.transfers_in.map((p) => p.name).join(', ') || '—'}</span>
        </div>
      )}
      {teamActive && data.num_transfers === 0 && (
        <div className="callout good">✓ Your team is already optimal — no changes needed.</div>
      )}

      <div className="group-label">Drivers</div>
      <div className="picklist">
        {drivers.map((p, i) => (
          <PickRow key={p.fantasy_id} pick={p} rank={i + 1} boosted={p.fantasy_id === data.boosted_id}
            mult={data.drs_multiplier} badge={teamActive && inIds.has(p.fantasy_id) ? 'in' : null}
            move={projections?.[p.fantasy_id]} />
        ))}
      </div>

      <div className="group-label">Constructors</div>
      <div className="picklist">
        {cons.map((p, i) => (
          <PickRow key={p.fantasy_id} pick={p} rank={i + 1} boosted={false}
            mult={data.drs_multiplier} badge={teamActive && inIds.has(p.fantasy_id) ? 'in' : null}
            move={projections?.[p.fantasy_id]} />
        ))}
      </div>
    </section>
  )
}

function Chips({ data }) {
  if (!data) return null
  const best = data.valued[0]?.delta > 0 ? data.valued[0] : null
  return (
    <section className="chips fade-up">
      <h2 className="section-title">Worth playing a chip?</h2>
      {best
        ? <p className="chips-verdict good">Yes — <strong>{CHIP_INFO[best.chip]?.label}</strong> adds about +{best.delta.toFixed(1)} pts this race.</p>
        : <p className="chips-verdict">Not this race — save your chips for a bigger swing.</p>}
      <div className="chip-grid">
        {data.valued.map((c, i) => {
          const info = CHIP_INFO[c.chip] || { label: c.chip, desc: '' }
          const isBest = i === 0 && c.delta > 0
          return (
            <div key={c.chip} className={`chip-card ${isBest ? 'best' : ''}`}>
              <div className="chip-head">
                <span className="chip-name">{info.label}</span>
                {isBest && <span className="best-tag">Best</span>}
              </div>
              <p className="chip-desc">{info.desc}</p>
              <div className={`chip-delta ${c.delta > 0 ? 'gain' : 'flat'}`}>
                {c.delta > 0 ? `+${c.delta.toFixed(1)} pts` : 'No gain'}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function HowItWorks() {
  return (
    <details className="how">
      <summary>How it works &amp; what the terms mean</summary>
      <div className="how-body">
        <p>
          We predict each driver and constructor’s fantasy points for the next Grand Prix, then build
          the highest-scoring team you can afford (5 drivers + 2 constructors). Prices come from the
          official F1 Fantasy game; results and pace from F1 timing data.
        </p>
        <dl>
          <dt>Projected points</dt>
          <dd>Estimated fantasy score next race. Choose a method in Options.</dd>
          <dt>DRS Boost</dt>
          <dd>Free power-up doubling one driver’s points; we boost whoever gains the most.</dd>
          <dt>Transfers &amp; the −10 penalty</dt>
          <dd>Free transfers each race; extras cost 10 pts. We only suggest changes that gain more than they cost.</dd>
          <dt>Likely range (x–y)</dt>
          <dd>Rough worst→best points for a driver, based on how consistent they’ve been.</dd>
          <dt>Price trend (↑ ↓ →)</dt>
          <dd>A guess at whether a price will rise or fall. Buy risers early to grow your team value.</dd>
        </dl>
      </div>
    </details>
  )
}

export default function App() {
  const [predictor, setPredictor] = useState('naive')
  const [drsBoost, setDrsBoost] = useState(true)
  const [freeTransfers, setFreeTransfers] = useState(2)
  const [budget, setBudget] = useState('')
  const [driverSlots, setDriverSlots] = useState(() => Array(N_DRIVERS).fill(''))
  const [consSlots, setConsSlots] = useState(() => Array(N_CONS).fill(''))
  const [panel, setPanel] = useState(null) // 'options' | 'team' | null
  const [refreshing, setRefreshing] = useState(false)
  const [tick, setTick] = useState(0)
  const [theme, setTheme] = useState(() => {
    const saved = typeof localStorage !== 'undefined' && localStorage.getItem('theme')
    if (saved) return saved
    return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('theme', theme) } catch { /* ignore */ }
  }, [theme])

  const [gameday] = useApi(`/api/gameday?_=${tick}`)
  const [poolData] = useApi(`/api/picks?predictor=${predictor}&_=${tick}`)
  const [projData] = useApi(`/api/projections?_=${tick}`)
  const pool = poolData?.picks ?? []
  const projections = projData?.projections

  const teamArr = useMemo(
    () => [...driverSlots, ...consSlots].filter(Boolean),
    [driverSlots, consSlots])
  const teamComplete = driverSlots.every(Boolean) && consSlots.every(Boolean)

  const budgetParam = budget !== '' && +budget > 0 ? `&budget=${+budget}` : ''
  const teamParam = teamComplete ? `&current_team=${teamArr.join(',')}&free_transfers=${freeTransfers}` : ''
  const [rec] = useApi(`/api/recommend?predictor=${predictor}&drs_boost=${drsBoost}${teamParam}${budgetParam}&_=${tick}`)
  const [chips] = useApi(teamComplete
    ? `/api/chips?predictor=${predictor}&current_team=${teamArr.join(',')}&free_transfers=${freeTransfers}${budgetParam}&_=${tick}`
    : null)

  const setDriver = (i, val) => setDriverSlots((s) => s.map((x, j) => (j === i ? val : x)))
  const setCons = (i, val) => setConsSlots((s) => s.map((x, j) => (j === i ? val : x)))
  const clearTeam = () => { setDriverSlots(Array(N_DRIVERS).fill('')); setConsSlots(Array(N_CONS).fill('')) }

  const refresh = async () => {
    setRefreshing(true)
    try {
      await fetch('/api/refresh', { method: 'POST' })
      setTick((t) => t + 1)
    } finally { setRefreshing(false) }
  }

  const togglePanel = (p) => setPanel((cur) => (cur === p ? null : p))

  return (
    <div className="app">
      <header className="hero fade-up">
        <div className="brand-row">
          <div className="brand">
            <span className="logo" aria-hidden="true">🏎️</span>
            <span className="brand-name">F1 Fantasy <b>Optimizer</b></span>
          </div>
          <button className="theme-toggle" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </div>
        {gameday && (
          <div className="hero-race">
            <h1 className="race-name">{gameday.upcoming_race || `Gameday ${gameday.gameday}`}</h1>
            <div className="race-meta">
              {gameday.upcoming_round && <span className="meta-chip">Round {gameday.upcoming_round} · {gameday.season}</span>}
              {gameday.upcoming_date && <span className="meta-chip">{fmtDate(gameday.upcoming_date)}</span>}
              {gameday.is_sprint && <span className="meta-chip sprint">🏁 Sprint</span>}
            </div>
          </div>
        )}
      </header>

      <div className="toolbar fade-up">
        <button className={`tool ${panel === 'options' ? 'active' : ''}`} onClick={() => togglePanel('options')}>
          <span className="tool-ico">⚙</span> Options
          <span className="tool-meta">{PRED_SHORT[predictor]}{drsBoost ? ' · DRS' : ''}</span>
        </button>
        <button className={`tool ${panel === 'team' ? 'active' : ''}`} onClick={() => togglePanel('team')}>
          <span className="tool-ico">＋</span> My team
          <span className={`tool-meta ${teamComplete ? 'ok' : ''}`}>
            {teamComplete ? '✓ set' : `${teamArr.length}/7`}
          </span>
        </button>
      </div>

      {panel === 'options' && (
        <OptionsPanel {...{ predictor, setPredictor, drsBoost, setDrsBoost,
          freeTransfers, setFreeTransfers, budget, setBudget, gameday, refresh, refreshing }} />
      )}
      {panel === 'team' && pool.length > 0 && (
        <TeamSlots {...{ pool, driverSlots, consSlots, setDriver, setCons, clear: clearTeam }} />
      )}

      {rec && <ModeBanner teamComplete={teamComplete} onOpenTeam={() => setPanel('team')} />}

      {rec ? (
        <Lineup data={rec} teamActive={teamComplete} projections={projections} />
      ) : (
        <div className="loading"><span className="spinner" />Building your optimal team…</div>
      )}
      {teamComplete && <Chips data={chips} />}
      <HowItWorks />

      <footer className="foot">Predictions are estimates, not guarantees. Data from F1 Fantasy &amp; F1 timing.</footer>
    </div>
  )
}
