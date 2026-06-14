import { useEffect, useState } from 'react'
import './App.css'

const fmtPrice = (v) => `$${v.toFixed(1)}M`
const fmtPts = (v) => `${v.toFixed(1)} pts`

function PickRow({ pick, boosted }) {
  return (
    <div className="pick">
      <span className="pick-name">
        {pick.name}
        {boosted && <span className="boost-tag">DRS&nbsp;2×</span>}
      </span>
      <span className="pick-price">{fmtPrice(pick.price)}</span>
      <span className="pick-pts">{fmtPts(pick.expected_points)}</span>
    </div>
  )
}

function Lineup({ data }) {
  const pct = Math.min((data.total_price / data.budget) * 100, 100)
  const over = data.total_price > data.budget
  return (
    <>
      <div className="summary">
        <div>
          <div className="summary-num">{data.expected_points.toFixed(1)}</div>
          <div className="summary-label">expected points</div>
        </div>
        <div>
          <div className="summary-num">{fmtPrice(data.total_price)}</div>
          <div className="summary-label">of {fmtPrice(data.budget)} spent</div>
        </div>
      </div>

      <div className="budget-bar">
        <div className={`budget-fill ${over ? 'over' : ''}`} style={{ width: `${pct}%` }} />
      </div>

      <section>
        <h2>Drivers</h2>
        {data.drivers
          .slice()
          .sort((a, b) => b.expected_points - a.expected_points)
          .map((p) => (
            <PickRow key={p.fantasy_id} pick={p} boosted={p.fantasy_id === data.boosted_id} />
          ))}
      </section>

      <section>
        <h2>Constructors</h2>
        {data.constructors
          .slice()
          .sort((a, b) => b.expected_points - a.expected_points)
          .map((p) => (
            <PickRow key={p.fantasy_id} pick={p} boosted={false} />
          ))}
      </section>
    </>
  )
}

export default function App() {
  const [predictor, setPredictor] = useState('heuristic')
  const [drsBoost, setDrsBoost] = useState(true)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ predictor, drs_boost: drsBoost })
    fetch(`/api/recommend?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [predictor, drsBoost])

  return (
    <div className="app">
      <header>
        <h1>🏎️ F1 Fantasy Optimal Lineup</h1>
        {data && (
          <p className="subtitle">
            Gameday {data.gameday} · {data.season} · {data.predictor}
          </p>
        )}
      </header>

      <div className="controls">
        <label>
          Predictor&nbsp;
          <select value={predictor} onChange={(e) => setPredictor(e.target.value)}>
            <option value="heuristic">Heuristic (form + track)</option>
            <option value="naive">Naive (season avg)</option>
            <option value="ml">ML (ridge)</option>
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={drsBoost} onChange={(e) => setDrsBoost(e.target.checked)} />
          DRS Boost (2× one driver)
        </label>
      </div>

      {loading && <p className="status">Optimizing…</p>}
      {error && <p className="status error">Failed to load: {error}</p>}
      {data && !loading && <Lineup data={data} />}
    </div>
  )
}
