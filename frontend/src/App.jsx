import { useEffect, useMemo, useState } from 'react'
import './App.css'

const MAX_DRIVERS = 5
const MAX_CONSTRUCTORS = 2
const fmtPrice = (v) => `$${v.toFixed(1)}M`
const fmtPts = (v) => `${v.toFixed(1)} pts`
const CHIP_LABELS = {
  wildcard: 'Wildcard', limitless: 'Limitless', extra_drs: 'Extra DRS', no_negative: 'No Negative',
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
      <h3>{label} <span className="count">{count}/{max}</span></h3>
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
    <div className="builder">
      {column(drivers, 'Drivers', nDrivers, MAX_DRIVERS)}
      {column(constructors, 'Constructors', nCons, MAX_CONSTRUCTORS)}
    </div>
  )
}

function PickRow({ pick, boosted, mult, badge }) {
  return (
    <div className="pick">
      <span className="pick-name">
        {pick.name}
        {boosted && <span className="boost-tag">DRS&nbsp;{mult}×</span>}
        {badge && <span className={`xfer-tag ${badge}`}>{badge === 'in' ? 'IN' : 'OUT'}</span>}
      </span>
      <span className="pick-price">{fmtPrice(pick.price)}</span>
      <span className="pick-pts">
        {fmtPts(pick.expected_points)}
        {pick.std > 0 && (
          <span className="pick-range" title="floor–ceiling (±1σ)">
            {pick.floor}–{pick.ceiling}
          </span>
        )}
      </span>
    </div>
  )
}

function Lineup({ data, teamActive }) {
  const pct = Math.min((data.total_price / data.budget) * 100, 100)
  const over = data.total_price > data.budget
  const inIds = new Set(data.transfers_in.map((p) => p.fantasy_id))
  return (
    <>
      <div className="summary">
        <div>
          <div className="summary-num">{data.net_points.toFixed(1)}</div>
          <div className="summary-label">
            {teamActive ? 'net points' : 'expected points'}
          </div>
        </div>
        <div>
          <div className="summary-num">{fmtPrice(data.total_price)}</div>
          <div className="summary-label">of {fmtPrice(data.budget)} spent</div>
        </div>
        {teamActive && (
          <div>
            <div className="summary-num">
              {data.num_transfers}
              {data.penalty > 0 && <span className="penalty"> −{data.penalty}</span>}
            </div>
            <div className="summary-label">transfers (penalty)</div>
          </div>
        )}
      </div>

      <div className="budget-bar">
        <div className={`budget-fill ${over ? 'over' : ''}`} style={{ width: `${pct}%` }} />
      </div>

      {teamActive && data.num_transfers > 0 && (
        <div className="transfers">
          <span className="t-out">OUT: {data.transfers_out.map((p) => p.name).join(', ') || '—'}</span>
          <span className="t-in">IN: {data.transfers_in.map((p) => p.name).join(', ') || '—'}</span>
        </div>
      )}

      <section>
        <h2>Drivers</h2>
        {data.drivers.slice().sort((a, b) => b.expected_points - a.expected_points).map((p) => (
          <PickRow key={p.fantasy_id} pick={p} boosted={p.fantasy_id === data.boosted_id}
            mult={data.drs_multiplier} badge={teamActive && inIds.has(p.fantasy_id) ? 'in' : null} />
        ))}
      </section>
      <section>
        <h2>Constructors</h2>
        {data.constructors.slice().sort((a, b) => b.expected_points - a.expected_points).map((p) => (
          <PickRow key={p.fantasy_id} pick={p} boosted={false}
            mult={data.drs_multiplier} badge={teamActive && inIds.has(p.fantasy_id) ? 'in' : null} />
        ))}
      </section>
    </>
  )
}

function Chips({ data }) {
  if (!data) return null
  return (
    <section className="chips">
      <h2>Chip value this race</h2>
      {data.valued.map((c, i) => (
        <div key={c.chip} className={`chip-row ${i === 0 && c.delta > 0 ? 'best' : ''}`}>
          <span>{CHIP_LABELS[c.chip] || c.chip}</span>
          <span className={c.delta > 0 ? 'gain' : 'flat'}>
            {c.delta > 0 ? `+${c.delta.toFixed(1)} pts` : 'no gain'}
          </span>
        </div>
      ))}
      <p className="info-chips">Not valued (in-race / variance): {data.info_only.join(', ')}</p>
    </section>
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
  const pool = poolData?.picks ?? []

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

  return (
    <div className="app">
      <header>
        <h1>🏎️ F1 Fantasy Optimal Lineup</h1>
        {gameday && (
          <p className="subtitle">
            Gameday {gameday.gameday} · {gameday.season}
            {gameday.deadline && <> · deadline {gameday.deadline.split(' ')[0]}</>}
            {gameday.is_sprint && <span className="sprint-badge">🏁 SPRINT</span>}
          </p>
        )}
      </header>

      <div className="controls">
        <label>Predictor&nbsp;
          <select value={predictor} onChange={(e) => setPredictor(e.target.value)}>
            <option value="naive">Naive</option>
            <option value="heuristic">Heuristic</option>
            <option value="ml">ML (pace-aware)</option>
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={drsBoost} onChange={(e) => setDrsBoost(e.target.checked)} />
          DRS Boost
        </label>
        <label>Free transfers&nbsp;
          <input className="num" type="number" min="0" value={freeTransfers}
            onChange={(e) => setFreeTransfers(Math.max(0, +e.target.value))} />
        </label>
        <label>Budget $M&nbsp;
          <input className="num" type="number" min="0" step="0.1" value={budget}
            placeholder={gameday ? gameday.budget : '100'}
            onChange={(e) => setBudget(e.target.value)} />
        </label>
        <button className="refresh" onClick={refresh} disabled={refreshing}>
          {refreshing ? 'Refreshing…' : '↻ Refresh data'}
        </button>
      </div>

      <details className="team-panel" open={!teamComplete}>
        <summary>
          My current team {teamComplete ? '✓ complete' : `(${team.size}/7 — leave empty for a fresh build)`}
        </summary>
        {pool.length > 0 && <TeamBuilder pool={pool} team={team} toggle={toggle} />}
        {team.size > 0 && <button className="clear" onClick={() => setTeam(new Set())}>Clear team</button>}
      </details>

      {rec && <Lineup data={rec} teamActive={teamComplete} />}
      {teamComplete && <Chips data={chips} />}
    </div>
  )
}
