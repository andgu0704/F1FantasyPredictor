import { useEffect, useMemo, useState } from 'react'
import './App.css'

const MAX_DRIVERS = 5
const MAX_CONSTRUCTORS = 2
const fmtPrice = (v) => `$${v.toFixed(1)}M`

const PREDICTORS = [
  { id: 'naive', label: 'Simple — season average',
    desc: 'Expects each driver to score their season average. Simplest, and the hardest to beat.' },
  { id: 'heuristic', label: 'Form & track',
    desc: 'Adjusts the average for recent form, history at this circuit, and reliability.' },
  { id: 'ml', label: 'Pace-aware (ML)',
    desc: 'A trained model that adds qualifying & race-pace — the most accurate at overall ranking.' },
]

const CHIP_INFO = {
  wildcard: { label: 'Wildcard', desc: 'Unlimited free transfers for one race (no point penalties).' },
  limitless: { label: 'Limitless', desc: 'No budget cap for one race — field any drivers you like.' },
  extra_drs: { label: 'Extra DRS', desc: 'Triples one driver’s points (3×) instead of the usual 2×.' },
  no_negative: { label: 'No Negative', desc: 'Any driver who scores below zero counts as zero instead.' },
  final_fix: { label: 'Final Fix', desc: 'Swap one pick after qualifying.' },
  auto_pilot: { label: 'Auto Pilot', desc: 'App auto-picks your boost (mobile).' },
}

const fmtDate = (iso) => {
  if (!iso) return null
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
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
      title={`Price projected to ${up ? 'rise' : 'fall'} about $${Math.abs(move)}M before the next race`}>
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

function TeamBuilder({ pool, team, toggle }) {
  const drivers = pool.filter((p) => p.entity_type === 'driver')
  const constructors = pool.filter((p) => p.entity_type === 'constructor')
  const nDrivers = [...team].filter((id) => drivers.some((d) => d.fantasy_id === id)).length
  const nCons = [...team].filter((id) => constructors.some((c) => c.fantasy_id === id)).length

  const column = (items, label, count, max) => (
    <div className="builder-col">
      <div className="col-head">
        <span>{label}</span>
        <span className={`col-count ${count === max ? 'done' : ''}`}>{count}/{max}</span>
      </div>
      <div className="chip-pool">
        {items.map((p) => {
          const on = team.has(p.fantasy_id)
          const full = (label === 'Drivers' ? nDrivers : nCons) >= max
          return (
            <button
              key={p.fantasy_id}
              className={`pill ${on ? 'on' : ''}`}
              disabled={!on && full}
              onClick={() => toggle(p.fantasy_id)}
            >
              {p.name} <span className="pill-price">{fmtPrice(p.price)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )

  return (
    <>
      <p className="hint">
        Tap the drivers and constructors <strong>currently in your team</strong>. Pick all
        {' '}{MAX_DRIVERS} drivers and {MAX_CONSTRUCTORS} constructors to get transfer advice —
        or leave it empty to see the ideal team from scratch.
      </p>
      <div className="builder">
        {column(drivers, 'Drivers', nDrivers, MAX_DRIVERS)}
        {column(constructors, 'Constructors', nCons, MAX_CONSTRUCTORS)}
      </div>
    </>
  )
}

function PickRow({ pick, rank, boosted, mult, badge, move }) {
  return (
    <div className={`pick ${boosted ? 'boosted' : ''}`}>
      <div className="pick-rank">{rank}</div>
      <div className="pick-main">
        <div className="pick-name">
          {pick.name}
          {boosted && <span className="tag tag-drs" title={`Points multiplied by ${mult}`}>DRS {mult}×</span>}
          {badge && <span className={`tag tag-${badge}`}>{badge === 'in' ? 'BUY' : 'SELL'}</span>}
        </div>
        <div className="pick-sub">
          <span className="pick-price">{fmtPrice(pick.price)}<Trend move={move} /></span>
          {pick.std > 0 && (
            <span className="pick-range" title="Likely range — worst case to best case">
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
      <h2 className="section-title">
        {teamActive ? 'Suggested changes' : 'Your optimal team'}
      </h2>

      <div className="stats">
        <Stat value={data.net_points.toFixed(0)} accent label="projected pts"
          tip="Total fantasy points expected next race (after any transfer penalty)." />
        <Stat value={fmtPrice(data.total_price)} label={`of ${fmtPrice(data.budget)}`} />
        {teamActive && (
          <Stat value={data.num_transfers}
            sub={data.penalty > 0 ? ` −${data.penalty}` : null}
            label="transfers"
            tip="Each change beyond your free transfers costs 10 points. This is the best trade-off." />
        )}
      </div>

      <div className="budget">
        <div className="budget-track" title="How much of your budget this team uses">
          <div className={`budget-fill ${over ? 'over' : ''}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="budget-text">{Math.round(pct)}% of budget</span>
      </div>

      {teamActive && data.num_transfers > 0 && (
        <div className="transfers">
          <span className="transfer t-out">SELL&nbsp; {data.transfers_out.map((p) => p.name).join(', ') || '—'}</span>
          <span className="transfer t-in">BUY&nbsp; {data.transfers_in.map((p) => p.name).join(', ') || '—'}</span>
        </div>
      )}
      {teamActive && data.num_transfers === 0 && (
        <div className="callout good">✓ Your current team is already optimal — no changes needed.</div>
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

      <p className="legend">
        <span className="tag tag-drs">DRS {data.drs_multiplier}×</span> boosted driver ·
        Price <Trend move={0.1} /> rising <Trend move={-0.1} /> falling — buy risers early to build value ·
        the small <em>x–y pts</em> is the likely worst→best range.
      </p>
    </section>
  )
}

function Chips({ data }) {
  if (!data) return null
  return (
    <section className="chips fade-up">
      <h2 className="section-title">Worth playing a chip?</h2>
      <p className="hint">
        Chips are one-time power-ups. The number is the <strong>extra points</strong> it would add
        this race — only worth using when it's clearly high.
      </p>
      <div className="chip-grid">
        {data.valued.map((c, i) => {
          const info = CHIP_INFO[c.chip] || { label: c.chip, desc: '' }
          const best = i === 0 && c.delta > 0
          return (
            <div key={c.chip} className={`chip-card ${best ? 'best' : ''}`}>
              <div className="chip-head">
                <span className="chip-name">{info.label}</span>
                {best && <span className="best-tag">Best value</span>}
              </div>
              <p className="chip-desc">{info.desc}</p>
              <div className={`chip-delta ${c.delta > 0 ? 'gain' : 'flat'}`}>
                {c.delta > 0 ? `+${c.delta.toFixed(1)} pts` : 'No gain now'}
              </div>
            </div>
          )
        })}
        {data.info_only.map((id) => {
          const info = CHIP_INFO[id] || { label: id, desc: '' }
          return (
            <div key={id} className="chip-card muted">
              <div className="chip-head"><span className="chip-name">{info.label}</span></div>
              <p className="chip-desc">{info.desc}</p>
              <div className="chip-delta flat">In-race only</div>
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
          This tool predicts how many fantasy points each driver and constructor will score in the
          next Grand Prix, then builds the highest-scoring team you can afford within the budget cap
          (5 drivers + 2 constructors). Live prices come from the official F1 Fantasy game; past
          results and pace come from F1 timing data.
        </p>
        <dl>
          <dt>Projected points</dt>
          <dd>Our estimate of a pick’s fantasy score next race. Pick a method above — from a simple
            season average to a pace-aware trained model.</dd>
          <dt>DRS Boost</dt>
          <dd>A free power-up that doubles one driver’s points each race. The tool boosts whoever
            gains the most.</dd>
          <dt>Transfers &amp; the −10 penalty</dt>
          <dd>You get free transfers each race; extras cost 10 points. Enter your team and the tool
            only suggests changes that gain more than they cost.</dd>
          <dt>Likely range (x–y)</dt>
          <dd>F1 is unpredictable. This is the rough worst→best points for a driver based on how
            consistent they’ve been.</dd>
          <dt>Price trend (↑ ↓ →)</dt>
          <dd>A heuristic guess at whether a price will rise or fall. Buying a riser early grows your
            team value over the season.</dd>
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
  const [team, setTeam] = useState(() => new Set())
  const [refreshing, setRefreshing] = useState(false)
  const [tick, setTick] = useState(0)

  const [gameday] = useApi(`/api/gameday?_=${tick}`)
  const [poolData] = useApi(`/api/picks?predictor=${predictor}&_=${tick}`)
  const [projData] = useApi(`/api/projections?_=${tick}`)
  const pool = poolData?.picks ?? []
  const projections = projData?.projections

  const teamComplete = useMemo(() => {
    const d = [...team].filter((id) => pool.find((p) => p.fantasy_id === id && p.entity_type === 'driver')).length
    const c = [...team].filter((id) => pool.find((p) => p.fantasy_id === id && p.entity_type === 'constructor')).length
    return d === MAX_DRIVERS && c === MAX_CONSTRUCTORS
  }, [team, pool])

  const budgetParam = budget !== '' && +budget > 0 ? `&budget=${+budget}` : ''
  const teamParam = teamComplete ? `&current_team=${[...team].join(',')}&free_transfers=${freeTransfers}` : ''
  const [rec] = useApi(`/api/recommend?predictor=${predictor}&drs_boost=${drsBoost}${teamParam}${budgetParam}&_=${tick}`)
  const [chips] = useApi(teamComplete
    ? `/api/chips?predictor=${predictor}&current_team=${[...team].join(',')}&free_transfers=${freeTransfers}${budgetParam}&_=${tick}`
    : null)

  const toggle = (id) => setTeam((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const refresh = async () => {
    setRefreshing(true)
    try {
      await fetch('/api/refresh', { method: 'POST' })
      setTick((t) => t + 1)
    } finally {
      setRefreshing(false)
    }
  }

  const predictorDesc = PREDICTORS.find((p) => p.id === predictor)?.desc

  return (
    <div className="app">
      <header className="hero fade-up">
        <div className="brand">
          <span className="logo" aria-hidden="true">🏎️</span>
          <span className="brand-name">F1 Fantasy <b>Optimizer</b></span>
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
        <p className="hero-intro">
          The highest-scoring F1 Fantasy team for the next Grand Prix, within your budget.
          Leave your team empty for the ideal squad, or enter it for transfer advice.
        </p>
      </header>

      <section className="card settings fade-up">
        <div className="field">
          <label htmlFor="pred">Prediction method <Info text="How we estimate each pick's points. Simpler is often just as accurate." /></label>
          <div className="select-wrap">
            <select id="pred" value={predictor} onChange={(e) => setPredictor(e.target.value)}>
              {PREDICTORS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
          {predictorDesc && <p className="field-hint">{predictorDesc}</p>}
        </div>

        <div className="field-row">
          <div className="field">
            <label htmlFor="ft">Free transfers <Info text="Changes you can make for free this race. Extra ones cost 10 points each." /></label>
            <input id="ft" className="num" type="number" min="0" value={freeTransfers}
              onChange={(e) => setFreeTransfers(Math.max(0, +e.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="bud">Budget ($M) <Info text="Money available (team value + bank). Defaults to the 100M cap." /></label>
            <input id="bud" className="num" type="number" min="0" step="0.1" value={budget}
              placeholder={gameday ? String(gameday.budget) : '100'}
              onChange={(e) => setBudget(e.target.value)} />
          </div>
        </div>

        <Toggle checked={drsBoost} onChange={setDrsBoost} label="Use DRS Boost"
          tip="A free power-up that doubles one driver's points each race." />

        {!gameday?.read_only && (
          <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
            {refreshing ? 'Refreshing…' : '↻ Refresh data'}
          </button>
        )}
      </section>

      <details className="card team-panel fade-up" open={!teamComplete}>
        <summary>
          <span className="panel-title">My current team</span>
          <span className={`panel-status ${teamComplete ? 'done' : ''}`}>
            {teamComplete ? '✓ complete' : `${team.size}/7 · optional`}
          </span>
        </summary>
        <div className="panel-body">
          {pool.length > 0 && <TeamBuilder pool={pool} team={team} toggle={toggle} />}
          {team.size > 0 && <button className="btn-text" onClick={() => setTeam(new Set())}>Clear &amp; start over</button>}
        </div>
      </details>

      {rec ? (
        <Lineup data={rec} teamActive={teamComplete} projections={projections} />
      ) : (
        <div className="loading"><span className="spinner" />Building your optimal team…</div>
      )}
      {teamComplete && <Chips data={chips} />}
      <HowItWorks />

      <footer className="foot">
        Predictions are estimates, not guarantees. Data from F1 Fantasy &amp; F1 timing.
      </footer>
    </div>
  )
}
