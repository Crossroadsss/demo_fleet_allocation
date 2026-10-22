// Plotly charts of backend results only. Degrades to a note if Plotly is unavailable.

export const SERVICE_COLORS = ["#2b59c3", "#8e44ad", "#d6337e", "#3d7d3d", "#6d4c41", "#546e7a"];
export const SCENARIO_COLORS = { a: "#0f8b8d", b_fixed: "#8a96a3", b: "#e07a1f" };
export const SCENARIO_ORDER = ["a", "b_fixed", "b"];

const FONT = { family: "Segoe UI, system-ui, sans-serif", size: 12, color: "#142235" };
const CONFIG = { displayModeBar: false, responsive: true };
const plotly = () => window.Plotly;

export function clearChart(el) {
  if (plotly()) plotly().purge(el);
  el.innerHTML = "";
}

function unavailable(el) {
  el.innerHTML = '<p class="muted small">Chart unavailable (Plotly could not be loaded — offline?). The tables have all values.</p>';
}

// states: [{key, short, services:[...], metrics}] — only plans with a feasible result.
// The two dashboard bar charts share one layout; their legends are identical HTML lines above the charts
// (not Plotly legends, which can wrap onto the plot or hide a series when clicked).
const LABEL_FONT = { size: 11, color: "#142235" };

function barLayout(xTitle, yTitle, yRange, dtick) {
  return {
    font: FONT, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", showlegend: false,
    height: 260, margin: { l: 58, r: 10, t: 22, b: 52 },
    xaxis: { title: { text: xTitle, font: { size: 11 }, standoff: 6 }, tickfont: { size: 12 }, linecolor: "#9fb0c4", ticks: "" },
    yaxis: { title: { text: yTitle, font: { size: 11 } }, tickfont: { size: 11 }, range: yRange, dtick,
             gridcolor: "#e6ebf1", zeroline: false, linecolor: "#9fb0c4", showline: true, ticks: "outside", ticklen: 3 },
  };
}

// Grouped vertical bars: one group per service, one bar per plan, each value labeled on its own bar,
// so identical Unchanged/Optimized speeds appear as two equal bars with their own labels.
export function renderSpeed(el, states, serviceIds) {
  if (!plotly()) return unavailable(el);
  const speedOf = (st, id) => { const s = st.services.find(x => x.service_id === id); return s ? s.speed_knots : null; };
  const traces = states.map(st => {
    const ys = serviceIds.map(id => speedOf(st, id));
    return {
      type: "bar", name: st.short, x: serviceIds, y: ys, marker: { color: SCENARIO_COLORS[st.key] },
      text: ys.map(v => (v == null ? "" : v.toFixed(1))), textposition: "outside", textfont: LABEL_FONT, cliponaxis: false,
      hovertemplate: `${st.short}<br>%{x}: %{y:.2f} kn<extra></extra>`,
    };
  });
  const all = traces.flatMap(t => t.y).filter(v => v != null);
  const lo = Math.max(0, Math.floor(Math.min(...all)) - 1);  // non-zero start, stated in the axis title
  const layout = barLayout("Service", `Sailing speed (kn) · axis starts at ${lo} kn`, [lo, Math.ceil(Math.max(...all)) + 1], 1);
  plotly().react(el, traces, { ...layout, barmode: "group", bargap: 0.3, bargroupgap: 0.08 }, CONFIG);
}

// Vertical bars of total weekly cost, one bar (trace) per operating plan; axis starts at zero.
export function renderCost(el, states) {
  if (!plotly()) return unavailable(el);
  const tick = { a: "Baseline", b_fixed: "Unchanged", b: "Optimized" };
  const totals = states.map(s => s.metrics.total_cost_usd_week / 1e6);
  const traces = states.map((st, i) => ({
    type: "bar", name: st.short, x: [tick[st.key]], y: [totals[i]], marker: { color: SCENARIO_COLORS[st.key] },
    text: [totals[i].toFixed(2)], textposition: "outside", textfont: LABEL_FONT, cliponaxis: false, width: 0.55,
    hovertemplate: `${st.short}: %{y:.3f} USD million / week<extra></extra>`,
  }));
  const top = Math.max(...totals);
  const step = top > 12 ? 4 : top > 6 ? 2 : 1;
  const layout = barLayout("Operating plan", "Weekly operating cost (USD million/week)", [0, Math.ceil((top * 1.15) / step) * step], step);
  plotly().react(el, traces, { ...layout, barmode: "overlay" }, CONFIG);
}

// Detailed analysis: fuel vs incremental vessel operating cost per plan.
export function renderCostBreakdown(el, states) {
  if (!plotly()) return unavailable(el);
  const labels = states.map(s => s.short);
  const colors = states.map(s => SCENARIO_COLORS[s.key]);
  const fuel = states.map(s => s.metrics.fuel_cost_usd_week);
  const ops = states.map(s => s.metrics.deployment_cost_usd_week);
  plotly().react(el, [
    { type: "bar", orientation: "h", name: "Fuel (solid)", y: labels, x: fuel, marker: { color: colors },
      hovertemplate: "%{y} fuel: $%{x:,.0f}/week<extra></extra>" },
    { type: "bar", orientation: "h", name: "Incremental vessel operating (light)", y: labels, x: ops,
      marker: { color: colors, opacity: 0.4, line: { color: colors, width: 1.5 } },
      hovertemplate: "%{y} vessel operating: $%{x:,.0f}/week<extra></extra>" },
  ], {
    font: FONT, height: 230, margin: { l: 120, r: 90, t: 36, b: 36 }, barmode: "stack",
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", legend: { orientation: "h", x: 0, y: 1.2 },
    xaxis: { gridcolor: "#e6ebf1", tickprefix: "$", tickformat: "~s" }, yaxis: { autorange: "reversed" },
    annotations: states.map((s, i) => ({ y: labels[i], x: fuel[i] + ops[i], xanchor: "left", xshift: 6, showarrow: false,
      text: `<b>$${(s.metrics.total_cost_usd_week / 1e6).toFixed(2)}M</b>` })),
  }, CONFIG);
}
