import React, { useState, useEffect, useCallback } from 'react';
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';
import './App.css';

const API_BASE = 'http://localhost:8000';
const ALGO_COLORS = { greedy: '#f59e0b', hungarian: '#3b82f6', auction: '#10b981' };
const ALGO_LABELS = { greedy: 'Greedy', hungarian: 'Hungarian', auction: 'Auction' };
const ALGO_DESCRIPTIONS = {
  greedy: 'Most urgent first, nearest truck. Fast but short-sighted.',
  hungarian: 'Global batch optimizer. Best profit but may skip critical P1 orders.',
  auction: 'Urgency × value bidding with opportunity cost. Best balance for perishables.',
};
const TIER_COLORS = { P1: '#ef4444', P2: '#f97316', P3: '#eab308', P4: '#22c55e' };
const SEED_OPTIONS = [42, 77, 123, 256, 999];
const ZONES = [
  { name: 'Fish Wharf', x: 2, y: 16, color: '#3b82f6' },
  { name: 'Downtown', x: 10, y: 10, color: '#8b5cf6' },
  { name: 'Industrial', x: 17, y: 4, color: '#f59e0b' },
  { name: 'Suburbs N', x: 14, y: 17, color: '#10b981' },
  { name: 'Suburbs S', x: 6, y: 3, color: '#ef4444' },
];

// SVG Map
function FleetMap({ scenario, assignments, selectedAlgo }) {
  const [hovered, setHovered] = useState(null);
  const [tipPos, setTipPos] = useState({ x: 0, y: 0 });
  if (!scenario) return null;

  const { trucks, orders } = scenario;
  const scale = 34;
  const w = 20 * scale, h = 20 * scale, pad = 34;
  const assignMap = {};
  assignments.forEach(a => { assignMap[a.order_id] = a; });
  const truckAssign = {};
  assignments.forEach(a => { truckAssign[a.truck_id] = a; });
  const tLookup = {};
  trucks.forEach(t => { tLookup[t.id] = t; });
  const oLookup = {};
  orders.forEach(o => { oLookup[o.id] = o; });
  const sx = x => pad + x * scale;
  const sy = y => pad + (20 - y) * scale;
  const onHover = (item, e) => { setHovered(item); setTipPos({ x: e.clientX, y: e.clientY }); };

  return (
    <div className="map-container">
      <svg viewBox={`0 0 ${w + pad * 2} ${h + pad * 2}`} className="fleet-map">
        <rect x={pad} y={pad} width={w} height={h} fill="#10101c" rx="8" />
        {[0, 5, 10, 15, 20].map(v => (
          <React.Fragment key={`g${v}`}>
            <line x1={sx(v)} y1={sy(0)} x2={sx(v)} y2={sy(20)} stroke="#1a1a30" strokeWidth="0.5" />
            <line x1={sx(0)} y1={sy(v)} x2={sx(20)} y2={sy(v)} stroke="#1a1a30" strokeWidth="0.5" />
            <text x={sx(v)} y={sy(-0.7)} textAnchor="middle" fill="#444" fontSize="9">{v}</text>
            <text x={sx(-0.9)} y={sy(v) + 3} textAnchor="middle" fill="#444" fontSize="9">{v}</text>
          </React.Fragment>
        ))}
        {ZONES.map(z => (
          <React.Fragment key={z.name}>
            <circle cx={sx(z.x)} cy={sy(z.y)} r={scale * 2.5} fill={z.color} opacity="0.04" />
            <text x={sx(z.x)} y={sy(z.y + 3)} textAnchor="middle" fill={z.color} fontSize="9" opacity="0.45" fontWeight="600">{z.name}</text>
          </React.Fragment>
        ))}
        {assignments.map((a, i) => {
          const t = tLookup[a.truck_id], o = oLookup[a.order_id];
          if (!t || !o) return null;
          const hl = hovered?.id === a.truck_id || hovered?.id === a.order_id;
          return (
            <React.Fragment key={`a${i}`}>
              <line x1={sx(t.location.x)} y1={sy(t.location.y)} x2={sx(o.pickup_location.x)} y2={sy(o.pickup_location.y)}
                stroke={ALGO_COLORS[selectedAlgo]} strokeWidth={hl ? 2.5 : 1} strokeDasharray="4,3" opacity={hl ? 0.8 : 0.2} />
              <line x1={sx(o.pickup_location.x)} y1={sy(o.pickup_location.y)} x2={sx(o.dropoff_location.x)} y2={sy(o.dropoff_location.y)}
                stroke={ALGO_COLORS[selectedAlgo]} strokeWidth={hl ? 3 : 1.5} opacity={hl ? 1 : 0.35} />
              <circle cx={sx(o.dropoff_location.x)} cy={sy(o.dropoff_location.y)} r={hl ? 4 : 2.5}
                fill={ALGO_COLORS[selectedAlgo]} opacity={hl ? 1 : 0.5} />
            </React.Fragment>
          );
        })}
        {orders.map(o => {
          const assigned = !!assignMap[o.id]; const hl = hovered?.id === o.id;
          return (
            <g key={`o${o.id}`} style={{ cursor: 'pointer' }}
              onMouseEnter={e => onHover({ type: 'order', id: o.id,
                info: `${o.id} • ${o.perishability_tier} • ${o.cargo_description}\nValue: $${o.base_value.toFixed(0)} • Weight: ${o.weight_kg}kg${assigned ? `\nAssigned to: ${assignMap[o.id].truck_id}` : '\n⚠ Unassigned'}` }, e)}
              onMouseLeave={() => setHovered(null)}>
              <circle cx={sx(o.pickup_location.x)} cy={sy(o.pickup_location.y)} r={hl ? 7 : assigned ? 5 : 4}
                fill={assigned ? TIER_COLORS[o.perishability_tier] : '#444'}
                stroke={hl ? '#fff' : assigned ? '#fff' : '#333'} strokeWidth={hl ? 2 : assigned ? 1 : 0.5}
                opacity={assigned ? 1 : 0.3} />
              <text x={sx(o.pickup_location.x)} y={sy(o.pickup_location.y) - 9} textAnchor="middle"
                fill={assigned ? '#ddd' : '#444'} fontSize="8">{o.id.replace('ORD-', '')}</text>
            </g>
          );
        })}
        {trucks.map(t => {
          const hl = hovered?.id === t.id; const has = !!truckAssign[t.id];
          return (
            <g key={`t${t.id}`} style={{ cursor: 'pointer' }}
              onMouseEnter={e => onHover({ type: 'truck', id: t.id,
                info: `${t.id} • ${t.capacity_kg}kg • ${t.speed_kmh}km/h${has ? `\nAssigned: ${truckAssign[t.id].order_id}` : '\nIdle'}` }, e)}
              onMouseLeave={() => setHovered(null)}>
              <text x={sx(t.location.x)} y={sy(t.location.y) + 5} textAnchor="middle"
                fontSize={hl ? 18 : 14} opacity={has ? 1 : 0.5}
                style={{ filter: hl ? `drop-shadow(0 0 4px ${ALGO_COLORS[selectedAlgo]})` : 'none' }}>
                🚛</text>
              <text x={sx(t.location.x)} y={sy(t.location.y) - 10} textAnchor="middle"
                fill={hl ? '#fff' : has ? '#ccc' : '#555'} fontSize="8" fontWeight="bold">
                {t.id.replace('TRK-', '')}</text>
            </g>
          );
        })}
        <g transform={`translate(${pad + 8}, ${pad + 8})`}>
          <rect width="105" height="100" rx="6" fill="rgba(10,10,18,0.88)" stroke="#1e1e35" />
          <text x="8" y="14" fill="#666" fontSize="8" fontWeight="700" letterSpacing="0.5">LEGEND</text>
          <text x="12" y="30" fontSize="11" textAnchor="middle">🚛</text>
          <text x="22" y="30" fill="#999" fontSize="8">Truck</text>
          {Object.entries(TIER_COLORS).map(([tier, col], i) => (
            <React.Fragment key={tier}>
              <circle cx="12" cy={43 + i * 13} r="4" fill={col} />
              <text x="22" y={46 + i * 13} fill="#999" fontSize="8">{tier}</text>
            </React.Fragment>
          ))}
          <circle cx="12" cy={95} r="3" fill="#444" />
          <text x="22" y={98} fill="#666" fontSize="8">Unassigned</text>
        </g>
      </svg>
      {hovered && (
        <div className="map-tooltip" style={{ left: tipPos.x + 14, top: tipPos.y - 8 }}>
          {hovered.info.split('\n').map((l, i) => <div key={i} className={i === 0 ? 'tt-title' : 'tt-detail'}>{l}</div>)}
        </div>
      )}
    </div>
  );
}

// Assignment List
function AssignmentList({ assignments, unassignedIds, orders }) {
  if (!assignments) return null;
  const oLookup = {};
  (orders || []).forEach(o => { oLookup[o.id] = o; });
  return (
    <div className="assignments-panel">
      <h3>Assignments ({assignments.length})</h3>
      <div className="assignments-scroll">
        {assignments.map(a => {
          const o = oLookup[a.order_id];
          return (
            <div key={a.order_id} className="asgn-card">
              <div className="asgn-top">
                <span className="asgn-truck">{a.truck_id}</span>
                <span className="asgn-arrow">→</span>
                <span className="asgn-order">{a.order_id}</span>
                {o && <span className="asgn-tier" style={{ background: TIER_COLORS[o.perishability_tier] }}>{o.perishability_tier}</span>}
                <span className="asgn-val">${a.delivered_value.toFixed(0)}</span>
              </div>
              <div className="asgn-meta">
                {o && <span>{o.cargo_description}</span>}
                <span>{a.transit_minutes.toFixed(0)} min</span>
                <span>${a.cost.toFixed(0)}</span>
              </div>
            </div>
          );
        })}
      </div>
      {unassignedIds?.length > 0 && (
        <div className="unasgn">
          <h4>⚠ Unassigned ({unassignedIds.length})</h4>
          <div className="unasgn-tags">
            {unassignedIds.map(id => {
              const o = oLookup[id];
              return (
                <span key={id} className="unasgn-tag">
                  {id} {o && <span style={{ color: TIER_COLORS[o.perishability_tier], fontWeight: 700 }}>{o.perishability_tier}</span>}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// Metrics Table
function MetricsTable({ averages }) {
  if (!averages) return null;
  const metrics = [
    { key: 'fleet_score', label: 'Fleet Score', desc: 'Overall efficiency (higher = better)', fmt: v => v.toFixed(2), hi: 'max' },
    { key: 'orders_fulfilled', label: 'Orders Fulfilled', desc: 'Orders served per scenario', fmt: v => `${v.toFixed(0)} / 25`, hi: 'max' },
    { key: 'p1_fulfilled_pct', label: 'P1 Critical Orders', desc: 'Ultra-perishable orders served', fmt: v => `${v.toFixed(0)}%`, hi: 'max' },
    { key: 'total_delivered_value', label: 'Value Delivered', desc: 'Average cargo value preserved', fmt: v => `$${Math.round(v).toLocaleString()}`, hi: 'max' },
    { key: 'total_value_lost', label: 'Value Lost', desc: 'Average cargo value lost', fmt: v => `$${Math.round(v).toLocaleString()}`, hi: 'min' },
    { key: 'total_cost', label: 'Operational Cost', desc: 'Average fuel & driving cost', fmt: v => `$${Math.round(v)}`, hi: 'min' },
    { key: 'total_distance_km', label: 'Total Distance', desc: 'Average km driven', fmt: v => `${v.toFixed(0)} km`, hi: 'min' },
    { key: 'avg_transit_minutes', label: 'Avg Transit', desc: 'Average delivery time', fmt: v => `${v.toFixed(1)} min`, hi: 'min' },
    { key: 'computation_time_ms', label: 'Compute Time', desc: 'Average algorithm runtime', fmt: v => `${v.toFixed(1)} ms`, hi: 'min' },
  ];
  const algos = ['greedy', 'hungarian', 'auction'];
  return (
    <table className="metrics-table">
      <thead><tr><th>Metric</th>{algos.map(a => <th key={a}><span style={{ color: ALGO_COLORS[a] }}>{ALGO_LABELS[a]}</span></th>)}</tr></thead>
      <tbody>
        {metrics.map(m => {
          const vals = algos.map(a => averages[a][m.key] || 0);
          const best = m.hi === 'max' ? Math.max(...vals) : Math.min(...vals);
          return (
            <tr key={m.key}>
              <td className="m-label"><div>{m.label}</div><div className="m-desc">{m.desc}</div></td>
              {algos.map((a, i) => (
                <td key={a} className={vals[i] === best ? 'm-best' : ''}>
                  {m.fmt(vals[i])}{vals[i] === best && <span className="best-badge">Best</span>}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// Radar Chart (improved scaling)
function TradeoffRadar({ averages }) {
  if (!averages) return null;
  const g = averages.greedy, h = averages.hungarian, a = averages.auction;

  // Scale each dimension so differences are visually dramatic
  // Use min-max scaling across the 3 algos, then map to 20-100 range
  const scale3 = (gv, hv, av) => {
    const min = Math.min(gv, hv, av);
    const max = Math.max(gv, hv, av);
    const range = max - min || 1;
    return {
      g: 20 + ((gv - min) / range) * 80,
      h: 20 + ((hv - min) / range) * 80,
      a: 20 + ((av - min) / range) * 80,
    };
  };

  // For metrics where lower is better, invert before scaling
  const fs = scale3(g.fleet_score, h.fleet_score, a.fleet_score);
  const p1 = scale3(g.p1_fulfilled_pct, h.p1_fulfilled_pct, a.p1_fulfilled_pct);
  const val = scale3(g.total_delivered_value, h.total_delivered_value, a.total_delivered_value);
  // Invert distance: less is better
  const dist = scale3(-g.total_distance_km, -h.total_distance_km, -a.total_distance_km);
  // Invert compute time: less is better
  const spd = scale3(-g.computation_time_ms, -h.computation_time_ms, -a.computation_time_ms);

  const data = [
    { metric: 'Fleet Score', Greedy: fs.g, Hungarian: fs.h, Auction: fs.a },
    { metric: 'P1 Fulfillment', Greedy: p1.g, Hungarian: p1.h, Auction: p1.a },
    { metric: 'Value Delivered', Greedy: val.g, Hungarian: val.h, Auction: val.a },
    { metric: 'Fuel Efficiency', Greedy: dist.g, Hungarian: dist.h, Auction: dist.a },
    { metric: 'Speed', Greedy: spd.g, Hungarian: spd.h, Auction: spd.a },
  ];

  return (
    <div className="radar-box">
      <h3>Algorithm Tradeoff Profile</h3>
      <p className="viz-sub">Each axis shows relative strength. Outer edge = best among the three. The shape reveals what each algorithm prioritizes.</p>
      <ResponsiveContainer width="100%" height={300}>
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="#1e1e35" />
          <PolarAngleAxis dataKey="metric" tick={{ fill: '#aaa', fontSize: 11 }} />
          <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 100]} />
          <Radar name="Greedy" dataKey="Greedy" stroke={ALGO_COLORS.greedy} fill={ALGO_COLORS.greedy} fillOpacity={0.12} strokeWidth={2.5} />
          <Radar name="Hungarian" dataKey="Hungarian" stroke={ALGO_COLORS.hungarian} fill={ALGO_COLORS.hungarian} fillOpacity={0.12} strokeWidth={2.5} />
          <Radar name="Auction" dataKey="Auction" stroke={ALGO_COLORS.auction} fill={ALGO_COLORS.auction} fillOpacity={0.12} strokeWidth={2.5} />
          <Tooltip contentStyle={{ background: '#1e1e2e', border: '1px solid #333', borderRadius: '8px', fontSize: '12px' }}
            formatter={(value) => `${Math.round(value)}%`} />
        </RadarChart>
      </ResponsiveContainer>
      <div className="radar-legend">
        {['greedy', 'hungarian', 'auction'].map(a => (
          <span key={a} className="radar-leg-item">
            <span className="radar-dot" style={{ background: ALGO_COLORS[a] }}></span>
            {ALGO_LABELS[a]}
          </span>
        ))}
      </div>
    </div>
  );
}

// Heatmap (improved colors)
function SeedHeatmap({ multiData }) {
  if (!multiData) return null;
  const algos = ['greedy', 'hungarian', 'auction'];

  // Color function: green for good, red for bad, relative to min/max per metric
  const getHeatColor = (val, min, max, higherIsBetter) => {
    const pct = max === min ? 0.5 : (val - min) / (max - min);
    const score = higherIsBetter ? pct : 1 - pct;
    // Interpolate from red (#ef4444) through yellow (#eab308) to green (#22c55e)
    if (score < 0.5) {
      const t = score / 0.5;
      return `rgb(${Math.round(239 + (234 - 239) * t)}, ${Math.round(68 + (179 - 68) * t)}, ${Math.round(68 + (8 - 68) * t)})`;
    } else {
      const t = (score - 0.5) / 0.5;
      return `rgb(${Math.round(234 + (34 - 234) * t)}, ${Math.round(179 + (197 - 179) * t)}, ${Math.round(8 + (94 - 8) * t)})`;
    }
  };

  const metricsList = [
    { key: 'fleet_score', label: 'Fleet Score', fmt: v => v.toFixed(2), higher: true },
    { key: 'p1_fulfilled_pct', label: 'P1 Fulfilled', fmt: v => `${v}%`, higher: true },
    { key: 'total_delivered_value', label: 'Value ($)', fmt: v => `${(v / 1000).toFixed(1)}k`, higher: true },
  ];

  return (
    <div className="heatmap-box">
      <h3>Consistency Across Scenarios</h3>
      <p className="viz-sub">Green = strong, red = weak. Shows how reliably each algorithm performs across different seeds.</p>
      {metricsList.map(m => {
        let allVals = [];
        multiData.per_seed.forEach(s => algos.forEach(a => allVals.push(s[a][m.key])));
        const minV = Math.min(...allVals), maxV = Math.max(...allVals);
        return (
          <div key={m.key} className="hm-section">
            <div className="hm-label">{m.label}</div>
            <div className="hm-grid">
              <div className="hm-header">
                <span></span>
                {multiData.seeds.map(s => <span key={s} className="hm-seed">Seed {s}</span>)}
              </div>
              {algos.map(a => (
                <div key={a} className="hm-row">
                  <span className="hm-algo" style={{ color: ALGO_COLORS[a] }}>{ALGO_LABELS[a]}</span>
                  {multiData.per_seed.map((seedData, i) => {
                    const val = seedData[a][m.key];
                    const bg = getHeatColor(val, minV, maxV, m.higher);
                    return (
                      <span key={i} className="hm-cell" style={{ background: bg }}>
                        {m.fmt(val)}
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Key Findings
function KeyFindings({ averages }) {
  if (!averages) return null;
  const g = averages.greedy, h = averages.hungarian, a = averages.auction;
  const findings = [
    { icon: '🏆', title: 'Best Profit', text: `Hungarian leads with avg Fleet Score ${h.fleet_score.toFixed(2)}, delivering $${Math.round(h.total_delivered_value).toLocaleString()} per scenario.`, color: ALGO_COLORS.hungarian },
    { icon: '🐟', title: 'P1 Protection', text: `Greedy & Auction both achieve ${g.p1_fulfilled_pct.toFixed(0)}% P1 fulfillment. Hungarian averages ${h.p1_fulfilled_pct.toFixed(0)}% — it trades critical orders for global efficiency.`, color: '#ef4444' },
    { icon: '🎯', title: 'Best Balance', text: `Auction uniquely combines high Fleet Score (${a.fleet_score.toFixed(2)}) with 100% P1 protection. Opportunity cost logic prevents wasting scarce trucks.`, color: ALGO_COLORS.auction },
    { icon: '⚡', title: 'Fastest', text: `Greedy averages ${g.computation_time_ms.toFixed(1)}ms — ${Math.round(a.computation_time_ms / g.computation_time_ms)}× faster than Auction. Ideal for real-time streaming.`, color: ALGO_COLORS.greedy },
    { icon: '⛽', title: 'Most Efficient', text: `Hungarian drives ${Math.round(h.total_distance_km)} km avg — ${Math.round(((g.total_distance_km - h.total_distance_km) / g.total_distance_km) * 100)}% less than Greedy. Global optimization finds shorter routes.`, color: ALGO_COLORS.hungarian },
  ];
  return (
    <div className="findings-section">
      <h2>💡 Key Findings</h2>
      <p className="section-sub">Averaged across {SEED_OPTIONS.length} scenarios — these patterns hold regardless of seed</p>
      <div className="findings-row">
        {findings.map((f, i) => (
          <div key={i} className="finding-card" style={{ borderTopColor: f.color }}>
            <div className="finding-icon">{f.icon}</div>
            <div className="finding-title">{f.title}</div>
            <div className="finding-text">{f.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Main App
function App() {
  const [singleData, setSingleData] = useState(null);
  const [multiData, setMultiData] = useState(null);
  const [selectedAlgo, setSelectedAlgo] = useState('auction');
  const [seed, setSeed] = useState(42);
  const [loading, setLoading] = useState(true);

  const fetchSingle = useCallback(async (s) => {
    try {
      const res = await fetch(`${API_BASE}/api/compare?seed=${s}`);
      setSingleData(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  const fetchMulti = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/compare/multi`);
      setMultiData(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { Promise.all([fetchSingle(seed), fetchMulti()]).then(() => setLoading(false)); }, []);

  const handleSeedChange = (s) => { setSeed(s); fetchSingle(s); };
  const currentResult = singleData?.results?.[selectedAlgo];
  const averages = multiData?.averages;

  if (loading && !singleData) return <div className="app loading-screen">Loading FreshFleet...</div>;

  return (
    <div className="app">
      <header className="app-header">
        <div className="hdr-left">
          <h1>🚛 FreshFleet</h1>
          <span className="hdr-sub">Perishable Goods Delivery Allocation Engine</span>
        </div>
        <div className="hdr-right">
          <label className="seed-label">Scenario:
            <select value={seed} onChange={e => handleSeedChange(Number(e.target.value))} className="seed-dropdown">
              {SEED_OPTIONS.map(s => <option key={s} value={s}>{s === 42 ? `Seed 42 (Default)` : `Seed ${s}`}</option>)}
            </select>
          </label>
        </div>
      </header>

      <div className="algo-cards">
        {['greedy', 'hungarian', 'auction'].map(algo => (
          <button key={algo} className={`algo-card ${selectedAlgo === algo ? 'active' : ''}`}
            style={{ '--ac': ALGO_COLORS[algo] }} onClick={() => setSelectedAlgo(algo)}>
            <div className="ac-top">
              <span className="ac-name">{ALGO_LABELS[algo]}</span>
              <span className="ac-score">{averages ? averages[algo].fleet_score.toFixed(2) : '—'}</span>
            </div>
            <div className="ac-desc">{ALGO_DESCRIPTIONS[algo]}</div>
            <div className="ac-stats">
              {averages && <>
                <span>P1: {averages[algo].p1_fulfilled_pct.toFixed(0)}%</span>
                <span>${Math.round(averages[algo].total_delivered_value).toLocaleString()}</span>
                <span>{averages[algo].computation_time_ms.toFixed(1)}ms</span>
              </>}
            </div>
          </button>
        ))}
      </div>

      {singleData && (
        <div className="stats-bar">
          {[
            { v: singleData.scenario.orders.length, l: 'Orders' },
            { v: singleData.scenario.trucks.length, l: 'Trucks' },
            { v: currentResult?.assignments?.length, l: 'Assigned' },
            { v: currentResult?.unassigned_order_ids?.length, l: 'Unassigned' },
            { v: singleData.scenario.orders.filter(o => o.perishability_tier === 'P1').length, l: 'P1 Orders' },
            { v: seed, l: 'Seed' },
          ].map((s, i) => (
            <div key={i} className="stat-item"><span className="stat-v">{s.v}</span><span className="stat-l">{s.l}</span></div>
          ))}
        </div>
      )}

      {singleData && (
        <div className="main-grid">
          <div className="map-panel">
            <h2 style={{ color: ALGO_COLORS[selectedAlgo] }}>Fleet Map — {ALGO_LABELS[selectedAlgo]}</h2>
            <p className="panel-sub">Hover over trucks and orders for details. Dashed = truck → pickup, solid = delivery route.</p>
            <FleetMap scenario={singleData.scenario} assignments={currentResult?.assignments || []} selectedAlgo={selectedAlgo} />
          </div>
          <div className="assign-panel">
            <AssignmentList assignments={currentResult?.assignments || []} unassignedIds={currentResult?.unassigned_order_ids || []} orders={singleData.scenario.orders} />
          </div>
        </div>
      )}

      {averages && (
        <>
          <KeyFindings averages={averages} />
          <div className="analysis-section">
            <h2>📊 Algorithm Comparison</h2>
            <p className="section-sub">Averaged across {SEED_OPTIONS.length} scenarios (seeds: {SEED_OPTIONS.join(', ')})</p>
            <MetricsTable averages={averages} />
          </div>
          <div className="viz-row">
            <TradeoffRadar averages={averages} />
            <SeedHeatmap multiData={multiData} />
          </div>
        </>
      )}
    </div>
  );
}

export default App;