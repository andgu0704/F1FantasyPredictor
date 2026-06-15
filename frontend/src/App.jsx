import { useEffect, useMemo, useState } from 'react'
import './App.css'

const MAX_DRIVERS = 5
const MAX_CONSTRUCTORS = 2
const fmtPrice = (v) => `$${v.toFixed(1)}M`
const fmtPts = (v) => `${v.toFixed(1)} pts`

const PREDICTORS = [
  { id: 'naive', label: 'Simple (season average)',
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

function Info({ text }) {
  return <span className="info" title={text} aria-label={text}>ⓘ</span>
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
      <h3>{label} <span className="count">{count}/{max} chosen</span></h3>
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
        Tap the drivers and constructors that are <strong>currently in your team</strong>.
        Pick all {MAX_DRIVERS} drivers and {MAX_CONSTRUCTORS} constructors and the tool
        will suggest the best transfers; leave it empty to just see the ideal team from scratch.
      </p>
      <div className="builder">
        {column(drivers, 'Drivers', nDrivers, MAX_DRIVERS)}
        {column(constructors, 'Constructors', nCons, MAX_CONSTRUCTORS)}
      </div>
    </>
  )
}

function Trend({ move }) {
  if (move === undefined || Math.abs(move) < 0.03)
    return <span className="trend flat" title="Price expected to stay roughly the same">→</span>
  const up = move > 0
  return (
    <span className={`trend ${up ? 'up' : 'down'}`}
      title={`Price projected to ${up ? 'rise' : 'fall'} about ${Math.abs(move)}M before the next race`}>
      {up ? '↑' : '↓'}
    </span>
  )
}

function PickRow({ pick, boosted, mult, badge, move }) {
  return (
    <div className="pick">
      <span className="pick-name">
        {pick.name}
        {boosted && <span className="boost-tag" title={`This driver's points are multiplied by ${mult}`}>DRS&nbsp;{mult}×</span>}
        {badge && <span className={`xfer-tag ${badge}`}>{badge === 'in' ? 'BUY' : 'SELL'}</span>}
      </span>
      <span className="pick-price">{fmtPrice(pick.price)}<Trend move={move} /></span>
      <span className="pick-pts">
        {fmtPts(pick.expected_points)}
        {pick.std > 0 && (
          <span className="pick-range" title="Likely range — worst case to best case">
            {pick.floor}–{pick.ceiling}
          </span>
        )}
      </span>
    </div>
  )
}

function Lineup({ data, teamActive, projections }) {
  const pct = Math.min((data.total_price / data.budget) * 100, 100)
  const over = data.total_price > data.budget
  const inIds = new Set(data.transfers_in.map((p) => p.fantasy_id))
  return (
    <>
      <h2 className="section-title">
        {teamActive ? 'Suggested changes for the next race' : 'Best team for the next race'}
      </h2>

      <div className="summary">
        <div>
          <div className="summary-num">{data.net_points.toFixed(1)}</div>
          <div className="summary-label">
            projected points <Info text="Total fantasy points we expect this team to score next race (after any transfer penalty)." />
          </div>
        </div>
        <div>
          <div className="summary-num">{fmtPrice(data.total_price)}</div>
          <div className="summary-label">spent of {fmtPrice(data.budget)}</div>
        </div>
        {teamActive && (
          <div>
            <div className="summary-num">
              {data.num_transfers}
              {data.penalty > 0 && <span className="penalty"> −{data.penalty} pts</span>}
            </div>
            <div className="summary-label">
              transfers <Info text="Each change beyond your free transfers costs 10 points. This is the best trade-off." />
            </div>
          </div>
        )}
      </div>

      <div className="budget-bar" title="How much of your budget this team uses">
        <div className={`budget-fill ${over ? 'over' : ''}`} style={{ width: `${pct}%` }} />
      </div>

      {teamActive && data.num_transfers > 0 && (
        <div className="transfers">
          <span className="t-out">SELL: {data.transfers_out.map((p) => p.name).join(', ') || '—'}</span>
          <span className="t-in">BUY: {data.transfers_in.map((p) => p.name).join(', ') || '—'}</span>
        </div>
      )}
      {teamActive && data.num_transfers === 0 && (
        <p className="hint">No changes recommended — your current team is already optimal. 👍</p>
      )}

      <div className="pick-head">
        <span>Driver</span><span>Price</span><span>Proj. points</span>
      </div>
      <section>
        <h3 className="group">Drivers (pick {MAX_DRIVERS})</h3>
        {data.drivers.slice().sort((a, b) => b.expected_points - a.expected_points).map((p) => (
          <PickRow key={p.fantasy_id} pick={p} boosted={p.fantasy_id === data.boosted_id}
            mult={data.drs_multiplier} badge={teamActive && inIds.has(p.fantasy_id) ? 'in' : null}
            move={projections?.[p.fantasy_id]} />
        ))}
      </section>
      <section>
        <h3 className="group">Constructors (pick {MAX_CONSTRUCTORS})</h3>
        {data.constructors.slice().sort((a, b) => b.expected_points - a.expected_points).map((p) => (
          <PickRow key={p.fantasy_id} pick={p} boosted={false}
            mult={data.drs_multiplier} badge={teamActive && inIds.has(p.fantasy_id) ? 'in' : null}
            move={projections?.[p.fantasy_id]} />
        ))}
      </section>

      <p className="legend">
        <strong>DRS&nbsp;{data.drs_multiplier}×</strong> = the driver whose points are boosted ·
        Price <Trend move={0.1} /> rise <Trend move={-0.1} /> fall <Trend move={0} /> steady
        (buy risers early to grow your team value) ·
        the small <em>x–y</em> under points is the likely worst→best range.
      </p>
    </>
  )
}

function Chips({ data }) {
  if (!data) return null
  return (
    <section className="chips">
      <h2 className="section-title">Is it worth playing a chip this race?</h2>
      <p className="hint">
        Chips are one-time power-ups. The number is how many <strong>extra points</strong> the chip
        would add this race — only worth using when that number is clearly high.
      </p>
      {data.valued.map((c, i) => {
        const info = CHIP_INFO[c.chip] || { label: c.chip, desc: '' }
        return (
          <div key={c.chip} className={`chip-row ${i === 0 && c.delta > 0 ? 'best' : ''}`}>
            <span className="chip-name">
              {info.label}
              {i === 0 && c.delta > 0 && <span className="best-tag">best value</span>}
              <span className="chip-desc">{info.desc}</span>
            </span>
            <span className={c.delta > 0 ? 'gain' : 'flat'}>
              {c.delta > 0 ? `+${c.delta.toFixed(1)} pts` : 'no gain now'}
            </span>
          </div>
        )
      })}
      {data.info_only.map((id) => {
        const info = CHIP_INFO[id] || { label: id, desc: '' }
        return (
          <div key={id} className="chip-row muted">
            <span className="chip-name">{info.label}<span className="chip-desc">{info.desc}</span></span>
            <span className="flat">can’t be valued ahead of time</span>
          </div>
        )
      })}
    </section>
  )
}

function HowItWorks() {
  return (
    <details className="how">
      <summary>How this works &amp; what the terms mean</summary>
      <div className="how-body">
        <p>
          This tool predicts how many fantasy points each driver and constructor will score in
          the next Grand Prix, then solves for the highest-scoring team you can afford within the
          budget cap (5 drivers + 2 constructors). Live prices and points come from the
          official F1 Fantasy game; past results and pace come from F1 timing data.
        </p>
        <dl>
          <dt>Projected points</dt>
          <dd>Our estimate of a pick’s fantasy score next race. Three methods are available
            (the “Prediction method” dropdown) — from a simple season average to a pace-aware
            trained model.</dd>
          <dt>DRS Boost</dt>
          <dd>A free power-up that doubles one driver’s points each race. The tool automatically
            boosts the driver where it’s worth the most.</dd>
          <dt>Transfers &amp; the −10 penalty</dt>
          <dd>You get a set number of free transfers each race; every extra change costs 10 points.
            Enter your current team and the tool only suggests changes that gain more than they cost.</dd>
          <dt>Likely range (x–y)</dt>
          <dd>F1 results are unpredictable. This is the rough worst-case to best-case points for a
            driver, based on how consistent they’ve been.</dd>
          <dt>Price trend (↑ ↓ →)</dt>
          <dd>A heuristic guess at whether a price will rise or fall before the next race. Buying a
            riser early grows your team’s value over the season.</dd>
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
      <header>
        <h1>🏎️ F1 Fantasy Team Optimizer</h1>
        {gameday && (
          <p className="subtitle">
            Next race: {gameday.upcoming_race || `Gameday ${gameday.gameday}`}
            {gameday.upcoming_round && <> · Round {gameday.upcoming_round}, {gameday.season}</>}
            {gameday.upcoming_date && <> · {gameday.upcoming_date}</>}
            {gameday.is_sprint && <span className="sprint-badge" title="Sprint weekend — extra points on offer">🏁 SPRINT</span>}
          </p>
        )}
        <p className="intro">
          Builds the highest-scoring F1 Fantasy team for the upcoming Grand Prix within your budget.
          Leave your team empty to see the ideal squad, or enter your current team below for
          transfer advice.
        </p>
      </header>

      <div className="controls">
        <label>Prediction method <Info text="How we estimate each pick's points. Simpler is often just as accurate." />
          <select value={predictor} onChange={(e) => setPredictor(e.target.value)}>
            {PREDICTORS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
        <label className="checkbox" title="A free power-up that doubles one driver's points each race">
          <input type="checkbox" checked={drsBoost} onChange={(e) => setDrsBoost(e.target.checked)} />
          Use DRS Boost
        </label>
        <label>Free transfers <Info text="How many changes you can make for free this race. Extra ones cost 10 points each." />
          <input className="num" type="number" min="0" value={freeTransfers}
            onChange={(e) => setFreeTransfers(Math.max(0, +e.target.value))} />
        </label>
        <label>Budget $M <Info text="Money available (team value + bank). Defaults to the 100M cap." />
          <input className="num" type="number" min="0" step="0.1" value={budget}
            placeholder={gameday ? gameday.budget : '100'}
            onChange={(e) => setBudget(e.target.value)} />
        </label>
        <button className="refresh" onClick={refresh} disabled={refreshing}
          title="Pull the latest prices and results for the upcoming race">
          {refreshing ? 'Refreshing…' : '↻ Refresh data'}
        </button>
      </div>
      {predictorDesc && <p className="method-desc">{predictorDesc}</p>}

      <details className="team-panel" open={!teamComplete}>
        <summary>
          {teamComplete
            ? '✓ Your current team is set — change picks below'
            : `Enter your current team for transfer advice (${team.size}/7 selected) — optional`}
        </summary>
        {pool.length > 0 && <TeamBuilder pool={pool} team={team} toggle={toggle} />}
        {team.size > 0 && <button className="clear" onClick={() => setTeam(new Set())}>Start over</button>}
      </details>

      {rec && <Lineup data={rec} teamActive={teamComplete} projections={projections} />}
      {teamComplete && <Chips data={chips} />}
      <HowItWorks />
    </div>
  )
}
