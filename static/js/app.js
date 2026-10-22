// Pages, shared state, inputs, API calls and dashboard rendering.
// Defaults come only from GET /api/config; every result shown comes from the last /api/compare response.
import { renderSpeed, renderCost, renderCostBreakdown, clearChart, SERVICE_COLORS, SCENARIO_COLORS, SCENARIO_ORDER } from "./charts.js";
import { MapSync } from "./map.js";

const $ = sel => document.querySelector(sel);
const $$ = sel => [...document.querySelectorAll(sel)];
const TIMEOUT_MS = 30000;

const state = {
  config: null,
  input: null,          // editable request body
  runInput: null,       // snapshot of the inputs used for the displayed comparison
  comparison: null,     // last /api/compare response
  stale: false,
  busy: false,
  page: "results",
  visibleServices: new Set(),  // services shown on the maps (all after each run)
};
let maps = null;

// Operator-facing plan names over the API keys a (A), b_fixed (B1), b (B2)
const SCEN = {
  a: { scenario: "mixed_routing", short: "Baseline" },
  b_fixed: { scenario: "full_cape", short: "Unchanged Fleet" },
  b: { scenario: "full_cape", short: "Optimized Fleet" },
};
const CLS = { a: "a", b_fixed: "b1", b: "b2" };

const RULES = [
  { key: "max_fleet_per_service", field: "limits", label: "Maximum Vessels per Service", short: "Max vessels per service", unit: "vessels", step: 1, int: true,
    desc: "Set a maximum number of vessels that can be assigned to each shipping service." },
  { key: "minimum_schedule_buffer", field: "days_by_service", label: "Minimum Schedule Buffer", short: "Schedule buffer", unit: "days per round trip", step: 0.5,
    desc: "Spare days built into every round trip to absorb delays (port congestion, weather) while keeping weekly departures. More buffer → faster sailing or more vessels." },
  { key: "maximum_round_trip_time", field: "days_by_service", label: "Maximum Round-Trip Duration", short: "Max round-trip duration", unit: "days per round trip", step: 1,
    desc: "Limit the active time of one round trip — sailing plus time in port, not counting spare buffer days. A tighter limit forces faster sailing." },
];

// ---------- formatting ----------
const usd = v => v == null || Number.isNaN(v) ? "—" : (Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${Math.round(v).toLocaleString("en-US")}`);
const usdFull = v => v == null || Number.isNaN(v) ? "—" : `$${Math.round(v).toLocaleString("en-US")}`;
const num = (v, d = 1) => v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d);
const int = v => v == null || Number.isNaN(v) ? "—" : Math.round(v).toLocaleString("en-US");
const signed = (v, f) => (v == null || Number.isNaN(v) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "±") + f(Math.abs(v)));
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const BINDING = { frequency: "weekly frequency", min_speed: "min speed", max_cycle: "max round trip", max_speed_cap: "max speed" };
const viaName = v => (v === "cape" ? "Cape of Good Hope" : "Suez / Red Sea");

// ---------- state paths ----------
const getPath = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => o[k], obj)[last] = value;
}

function syncInputs() {
  $$("[data-path]").forEach(el => {
    const v = getPath(state.input, el.dataset.path);
    if (el.type === "checkbox") el.checked = !!v;
    else if (document.activeElement !== el) el.value = v ?? "";
  });
  const f = state.input.fleet;
  const c = f.reference_fuel_tonnes_per_day / (24 * f.reference_speed_knots ** 3);
  $("#fuel-coeff").textContent = Number.isFinite(c) ? c.toExponential(4) : "—";
  state.input.services.forEach((s, i) => {
    for (const sc of Object.keys(state.config.scenarios)) {
      const el = document.getElementById(`rt-${sc}-${i}`);
      if (el) el.textContent = int(roundTrip(s, sc));
    }
  });
  renderConfigSummary();
  renderRouteDiagram();
}

function roundTrip(svc, sc) {
  const r = state.config.scenarios[sc].routing;
  return Object.entries(r).reduce((a, [dir, variant]) => a + Number(svc.legs[dir][variant]), 0);
}

function onInput(e) {
  const el = e.target;
  if (!el.dataset || !el.dataset.path) return;
  let value;
  if (el.type === "checkbox") value = el.checked;
  else if (el.type === "number") {
    value = el.value === "" ? null : (el.dataset.type === "int" ? Number.parseInt(el.value, 10) : Number(el.value));
    el.classList.toggle("invalid", value == null || Number.isNaN(value));
  } else value = el.value;
  setPath(state.input, el.dataset.path, value);
  if (el.dataset.rerender === "rules") renderRules();
  syncInputs();
  markStale();
}

function markStale() {
  if (!state.comparison) return;
  state.stale = true;
  $("#nav-stale").classList.remove("hidden");
  $("#results-body").classList.add("is-stale");
  setResultsStatus("stale", "<b>Out of date</b> — scenario inputs changed after this run. The figures below belong to the previous inputs; " +
    'click <b>Rerun optimization</b> or review the <a href="#" data-goto="inputs">scenario configuration</a>.');
}

function clearStale() {
  state.stale = false;
  $("#nav-stale").classList.add("hidden");
  $("#results-body").classList.remove("is-stale");
}

// ---------- navigation ----------
function goto(page) {
  state.page = page;
  $$(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.page === page));
  ["model", "inputs", "results"].forEach(p => $(`#page-${p}`).classList.toggle("hidden", p !== page));
  if (page === "results" && maps) setTimeout(() => maps.resize(), 60);
  if (page !== "results" && maps) maps.pause();
  window.scrollTo({ top: 0 });
}

// ---------- model & methodology ----------
function renderModelPage() {
  const cfg = state.config;
  $("#scenario-explainer").innerHTML = Object.entries(cfg.scenarios).map(([, s]) => `
    <div class="scen-explain">
      <h4>${esc(s.label)}</h4>
      <div class="dir"><b>Westbound (Asia → Europe)</b><span>via ${viaName(s.routing.westbound)}</span></div>
      <div class="dir"><b>Eastbound (Europe → Asia)</b><span>via ${viaName(s.routing.eastbound)}</span></div>
    </div>`).join("");
  $("#sources-list").innerHTML = Object.values(cfg.sources).map(s => `<li>${esc(s)}</li>`).join("") +
    Object.entries(cfg.routes).map(([id, r]) => `<li><b>${esc(id)} rotation:</b> ${esc(r.ports_note)}</li>`).join("");
  renderMath();
}

function renderMath() {
  if (!window.katex) return;  // plain-text fallbacks stay visible
  $$(".tex, .tex-block").forEach(el => {
    try { window.katex.render(el.dataset.tex, el, { displayMode: el.classList.contains("tex-block"), throwOnError: false }); }
    catch { /* keep fallback text */ }
  });
}

// ---------- scenario configuration ----------
function renderConfigSummary() {
  const f = state.input.fleet, e = state.input.economics, r = state.input.rules;
  const chips = [
    `<span class="chip"><b>${esc(f.available_vessels ?? "—")}</b> vessels available</span>`,
    `<span class="chip"><b>${esc(f.min_speed_knots ?? "—")}–${esc(f.max_speed_knots ?? "—")}</b> kn</span>`,
    `<span class="chip">bunker <b>$${int(e.fuel_price_usd_per_tonne)}</b>/t</span>`,
    `<span class="chip">vessel operating <b>$${int(e.deployment_cost_usd_per_vessel_week)}</b>/vessel/week</span>`,
    `<span class="chip"><b>${state.input.services.length}</b> services</span>`,
    ...RULES.map(rule => {
      const on = r[rule.key].enabled;
      const vals = on ? Object.values(r[rule.key][rule.field]) : [];
      const uniq = [...new Set(vals)];
      const detail = on ? ` (${uniq.length === 1 ? `${uniq[0]} ${rule.unit}` : "per service"})` : "";
      return `<span class="chip ${on ? "on" : "off"}">${rule.short}: <b>${on ? "on" : "off"}</b>${esc(detail)}</span>`;
    }),
  ];
  $("#config-summary").innerHTML = chips.join("");
}

function renderRouteDiagram() {
  const scen = Object.entries(state.config.scenarios);
  const all = state.input.services.flatMap(s => scen.map(([sc]) => roundTrip(s, sc))).filter(Number.isFinite);
  const max = Math.max(1, ...all);
  const segCls = (dir, v) => `${dir === "westbound" ? "wb" : "eb"}-${v}`;
  const rows = state.input.services.map(s => scen.map(([sc, meta], k) => {
    const segs = Object.entries(meta.routing).map(([dir, v]) => {
      const nm = Number(s.legs[dir][v]);
      const label = `${dir === "westbound" ? "WB" : "EB"} ${v === "cape" ? "Cape" : "Suez"} ${int(nm)}`;
      return `<div class="seg ${segCls(dir, v)}" style="width:${(100 * nm / max).toFixed(1)}%" title="${label} nm">${label}</div>`;
    }).join("");
    return `<div class="rd-svc">${k === 0 ? esc(s.service_id) : ""}</div>
      <div class="rd-label">${esc(meta.short)}</div>
      <div class="rd-bar">${segs}</div>
      <div class="rd-total">${int(roundTrip(s, sc))} nm</div>`;
  }).join("")).join('<div class="rd-sep"></div>');
  $("#route-diagram").innerHTML = `
    <div class="rd-head">Service</div><div class="rd-head rd-label">Scenario</div>
    <div class="rd-head">Round trip = westbound leg + eastbound leg</div><div class="rd-head" style="text-align:right">Total</div>
    ${rows}`;
}

function renderServiceEditor() {
  const scen = Object.keys(state.config.scenarios);
  const rows = state.input.services.map((s, i) => `
    <tr>
      <td class="l"><span class="swatch" style="background:${SERVICE_COLORS[i % SERVICE_COLORS.length]}"></span><b>${esc(s.service_id)}</b></td>
      <td class="l"><input type="text" data-path="services.${i}.name" title="${esc(state.config.routes[s.service_id]?.ports_note || "")}"></td>
      <td><input type="number" step="0.5" data-path="services.${i}.port_days"></td>
      <td class="g-wb"><input type="number" step="10" data-path="services.${i}.legs.westbound.cape"></td>
      <td class="g-eb"><input type="number" step="10" data-path="services.${i}.legs.eastbound.suez"></td>
      <td class="g-eb"><input type="number" step="10" data-path="services.${i}.legs.eastbound.cape"></td>
      ${scen.map(sc => `<td class="g-rt" id="rt-${sc}-${i}"></td>`).join("")}
    </tr>`).join("");
  $("#services-edit").innerHTML = `
    <thead>
      <tr class="group"><th colspan="3"></th><th class="g-wb">Westbound · Asia → Europe</th>
        <th class="g-eb" colspan="2">Eastbound · Europe → Asia</th><th class="g-rt" colspan="${scen.length}">Calculated round trip</th></tr>
      <tr><th class="l">ID</th><th class="l">Service name</th><th>Port days per round trip</th>
        <th class="g-wb">via Cape (nm)</th><th class="g-eb">via Suez (nm)</th><th class="g-eb">via Cape (nm)</th>
        ${scen.map(sc => `<th class="g-rt">${esc(state.config.scenarios[sc].short)} (nm)</th>`).join("")}</tr>
    </thead>
    <tbody>${rows}</tbody>`;
  syncInputs();
}

function renderRules() {
  const ids = state.input.services.map(s => s.service_id);
  $("#rules").innerHTML = RULES.map(rule => {
    const r = state.input.rules[rule.key];
    const values = ids.map(id => `
      <label>${esc(id)} (${rule.unit})
        <input type="number" step="${rule.step}" ${rule.int ? 'data-type="int"' : ""} data-path="rules.${rule.key}.${rule.field}.${id}"></label>`).join("");
    return `<div class="rule">
      <label><input type="checkbox" data-path="rules.${rule.key}.enabled" data-rerender="rules"> ${rule.label}</label>
      <p class="rule-desc">${rule.desc}</p>
      ${r.enabled ? `<div class="rule-values">${values}</div>` : ""}
    </div>`;
  }).join("");
  syncInputs();
}

function setInputMessage(kind, html) {
  $("#input-message").innerHTML = html ? `<div class="status ${kind}">${html}</div>` : "";
}

// ---------- decision dashboard ----------
function setResultsStatus(kind, html) {
  const el = $("#results-status");
  el.className = `status ${kind}`;
  el.innerHTML = html;
  el.classList.toggle("hidden", kind === "ok");  // the dashboard itself states a successful result
}

function scenarioStates(c) {
  return SCENARIO_ORDER.map(key => {
    const r = c[key];
    const feasible = key === "b_fixed" ? !!(r && r.feasible) : !!(r && r.services);
    return { key, ...SCEN[key], r, feasible, services: feasible ? r.services : null, metrics: feasible ? r.metrics : null };
  });
}

function infeasibleReasons(st) {
  if (st.key === "b_fixed") return st.r ? st.r.reasons : ["The Baseline has no feasible plan, so the Unchanged Fleet plan is undefined."];
  return (st.r && st.r.diagnostics && st.r.diagnostics.reasons) || [st.r ? st.r.reason || st.r.status : "No result"];
}

const SAVINGS_EPS = 0.5;  // USD/week; below this the solver result is reported as $0
const allOptimal = c => c.a.status === "OPTIMAL" && c.b.status === "OPTIMAL";
const serviceColor = id => SERVICE_COLORS[Math.max(0, state.runInput.services.findIndex(s => s.service_id === id)) % SERVICE_COLORS.length];

// 1 · Operating plan comparison: three plan cards, cost changes on the connecting arrows
function renderPlanFlow(c) {
  const [A, B1, B2] = scenarioStates(c);
  const routeLabel = { a: "Mixed routing · WB Cape, EB Suez", b_fixed: "Full Cape routing · Baseline fleet kept", b: "Full Cape routing · fleet re-optimized" };
  const card = st => {
    if (!st.feasible) {
      return `<div class="op-card ${CLS[st.key]}"><div class="op-name">${esc(st.short)}</div><div class="op-route">${routeLabel[st.key]}</div>
        <div class="op-infeasible">${st.key === "b_fixed" ? "Infeasible" : esc(st.r ? st.r.status : "No result")}</div>
        <div class="op-reason">${infeasibleReasons(st).map(esc).join("<br>")}</div></div>`;
    }
    const proof = st.key === "b_fixed" ? "evaluated" : (st.r.status === "OPTIMAL" ? "proven optimal" : "feasible · optimality not proven");
    return `<div class="op-card ${CLS[st.key]}"><div class="op-name">${esc(st.short)}</div><div class="op-route">${routeLabel[st.key]}</div>
      <div class="op-cost">${usd(st.metrics.total_cost_usd_week)} <small>/ week</small></div>
      <div class="op-meta"><span>Weekly operating cost · ${proof}</span><span>${st.metrics.allocated_vessels} vessels deployed</span></div></div>`;
  };
  // Routing disruption arrow: Cost(Unchanged) − Cost(Baseline)
  const disrupt = A.feasible && B1.feasible
    ? { cls: "disrupt", value: `${signed(c.fixed_fleet_impact_usd_week, usd)} / week`, note: "Longer routes via Cape, original fleet retained" }
    : { cls: "na", value: "N/A", note: A.feasible ? "Original fleet cannot keep weekly departures" : "Baseline infeasible" };
  // Fleet reoptimization arrow: Cost(Unchanged) − Cost(Optimized)
  let reopt;
  if (!A.feasible || !B2.feasible) reopt = { cls: "na", value: "N/A", note: "No feasible full-Cape plan" };
  else if (!B1.feasible) reopt = { cls: "na", value: "N/A", note: "Reallocation required — no savings figure applies" };
  else {
    const s = c.reoptimization_savings_usd_week;
    const zero = Math.abs(s) < SAVINGS_EPS;
    reopt = { cls: "reopt", value: `${zero ? "$0" : usd(s)} / week saved`,
              note: (zero ? "No further reduction from reallocating vessels" : "Optimized allocation and sailing speeds") +
                    (c.b.status === "OPTIMAL" ? "" : " · optimality not proven") };
  }
  const arrow = (label, v) => `<div class="connector ${v.cls}"><div class="c-pill"><div class="c-label">${label}</div>
    <div class="c-value">${v.value}</div></div><div class="c-arrow"></div><div class="c-note">${esc(v.note)}</div></div>`;
  $("#plan-flow").innerHTML = card(A) + arrow("Routing disruption", disrupt) + card(B1) + arrow("Fleet reoptimization", reopt) + card(B2);
}

function renderRecBanner(c) {
  const [A, B1, B2] = scenarioStates(c);
  const moves = Object.entries(c.fleet_moves || {}).filter(([, d]) => d !== 0);
  const movesTxt = moves.map(([s, d]) => `${s} ${d > 0 ? "+" : "−"}${Math.abs(d)} vessel${Math.abs(d) > 1 ? "s" : ""}`).join(", ");
  let text, warn = false;
  if (!A.feasible || !B2.feasible) {
    text = `No feasible plan for ${!A.feasible ? "the Baseline" : "full Cape routing"} under the current inputs — review the scenario configuration.`;
    warn = true;
  } else if (!B1.feasible) {
    text = `Reallocate vessels (${movesTxt}): the existing allocation cannot maintain weekly departures on full Cape routing.`;
    warn = true;
  } else if (!moves.length) {
    text = "Maintain the existing fleet allocation and increase sailing speeds to accommodate longer routes.";
  } else {
    text = `Reallocate vessels (${movesTxt}) and adjust sailing speeds to the longer full-Cape routes.`;
  }
  const net = A.feasible && B2.feasible ? signed(c.disruption_impact_usd_week, usd) : "N/A";
  const qual = allOptimal(c) ? "" : '<span class="qual">At least one plan is feasible but not proven optimal; figures may not be minimal.</span>';
  const banner = $("#rec-banner");
  banner.className = `rec-banner ${warn ? "warn" : ""}`;
  banner.innerHTML = `<span class="rec-icon">${warn ? "!" : "✓"}</span>
    <div class="rec-text"><b>Recommended action</b> &nbsp;${esc(text)}${qual}</div>
    <div class="rec-net">Net impact vs Baseline (optimized)<b>${net} / week</b></div>`;
}

// 3 · Allocation table, speed chart, cost chart
function renderFleetTable(c) {
  const [A, B1, B2] = scenarioStates(c);
  const ids = state.runInput.services.map(s => s.service_id);
  const n = (st, id) => {
    if (st.key === "b_fixed" && st.r) return st.r.allocation[id];  // Baseline counts, even if infeasible
    return st.feasible ? st.services.find(s => s.service_id === id).selected_vessels : null;
  };
  const rows = ids.map(id => {
    const a = n(A, id), u = n(B1, id), o = n(B2, id);
    const d = u != null && o != null ? o - u : null;
    return `<tr class="${d ? "changed" : ""}"><td><span class="swatch" style="background:${serviceColor(id)}"></span>${esc(id)}</td>
      <td>${a ?? "—"}</td><td>${u ?? "—"}${B1.feasible || u == null ? "" : "*"}</td><td>${o ?? "—"}</td>
      <td class="${d > 0 ? "chg-up" : d < 0 ? "chg-down" : ""}">${d == null ? "—" : signed(d, x => x)}</td></tr>`;
  }).join("");
  const sum = st => ids.reduce((acc, id) => acc + (n(st, id) ?? 0), 0);
  const tu = sum(B1), to = sum(B2);
  $("#fleet-table").innerHTML = `
    <thead><tr><th>Service</th><th>Baseline</th><th>Unchanged<br>Fleet</th><th>Optimized<br>Fleet</th><th title="Optimized Fleet − Unchanged Fleet">Change</th></tr></thead>
    <tbody>${rows}</tbody>
    <tfoot><tr><td>Total</td><td>${A.feasible ? sum(A) : "—"}</td><td>${B1.r ? tu : "—"}</td><td>${B2.feasible ? to : "—"}</td>
      <td>${B1.r && B2.feasible ? signed(to - tu, x => x) : "—"}</td></tr></tfoot>` +
    (B1.r && !B1.feasible ? '<caption class="note" style="caption-side:bottom;text-align:left">* Baseline counts cannot keep weekly departures on full Cape routing.</caption>' : "");
}

function renderCharts(c) {
  const feasible = scenarioStates(c).filter(st => st.feasible);
  const els = [$("#chart-speed"), $("#chart-cost")];
  if (!feasible.length) { els.forEach(clearChart); clearChart($("#chart-breakdown")); return; }
  const legend = feasible.map(st => `<span><i style="background:${SCENARIO_COLORS[st.key]}"></i>${esc(st.short)}</span>`).join("");
  $$(".scen-legend").forEach(el => (el.innerHTML = legend));
  renderSpeed(els[0], feasible, state.runInput.services.map(s => s.service_id));
  renderCost(els[1], feasible);
  if ($("#fold-breakdown").open && $("#detailed").open) renderCostBreakdown($("#chart-breakdown"), feasible);
}

// 4 · Detailed analysis
function renderWhatChanged(c) {
  const input = state.runInput;
  const [A, B1] = scenarioStates(c);
  const rows = input.services.map(s => {
    const a = roundTrip(s, "mixed_routing"), b = roundTrip(s, "full_cape");
    const aS = A.feasible ? A.services.find(x => x.service_id === s.service_id) : null;
    const b1S = B1.feasible ? B1.services.find(x => x.service_id === s.service_id) : null;
    const b1Req = !B1.feasible && B1.r && B1.r.speeds_required_knots ? B1.r.speeds_required_knots[s.service_id] : null;
    const speed = aS ? `${num(aS.speed_knots)} → ${b1S ? num(b1S.speed_knots) : (b1Req != null ? `needs ${num(b1Req)}` : "—")}` : "—";
    return `<tr><td><span class="swatch" style="background:${serviceColor(s.service_id)}"></span><b>${esc(s.service_id)}</b></td>
      <td>${int(a)}</td><td>${int(b)}</td><td class="up">${signed(b - a, int)} (${signed(100 * (b - a) / a, v => v.toFixed(1) + "%")})</td>
      <td>${speed}</td></tr>`;
  }).join("");
  $("#what-changed").innerHTML = `<div class="table-wrap"><table class="data whatchanged">
    <thead><tr><th class="l">Service</th><th>Round trip, mixed (nm)</th><th>Round trip, full Cape (nm)</th><th>Extra distance</th>
      <th>Speed Baseline → Unchanged Fleet (kn)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderDetail(c) {
  const sts = scenarioStates(c);
  const ids = state.runInput.services.map(s => s.service_id);
  const rowsDef = [
    ["Vessels", s => s.selected_vessels],
    ["Speed (kn)", s => num(s.speed_knots, 2)],
    ["Speed set by", s => BINDING[s.speed_binding] || s.speed_binding],
    ["Active cycle (days)", s => num(s.active_cycle_days)],
    ["Scheduled rotation (days)", s => num(s.scheduled_rotation_days, 0)],
    ["Schedule slack (days)", s => num(s.slack_days)],
    ["Fuel (t/week)", s => int(s.fuel_tonnes_week)],
    ["Fuel cost ($/week)", s => usdFull(s.fuel_cost_usd_week)],
    ["Vessel operating cost ($/week)", s => usdFull(s.deployment_cost_usd_week)],
    ["Total ($/week)", s => usdFull(s.total_cost_usd_week)],
  ];
  const cell = (st, id, row) => {
    if (!st.feasible) {
      if (st.key === "b_fixed" && st.r && row === 0) return `${st.r.allocation[id]} (infeasible)`;
      if (st.key === "b_fixed" && st.r && row === 1 && st.r.speeds_required_knots) {
        const v = st.r.speeds_required_knots[id];
        return v == null ? "no speed works" : `needs ${num(v)}`;
      }
      return "—";
    }
    return rowsDef[row][1](st.services.find(s => s.service_id === id));
  };
  const body = ids.map((id, i) => `
    <tr class="svc"><td colspan="4"><span class="swatch" style="background:${serviceColor(id)}"></span>${esc(id)} <span class="muted">${esc(state.runInput.services[i].name)}</span></td></tr>
    ${rowsDef.map(([label], row) => `<tr><td>${label}</td>${sts.map(st => `<td>${cell(st, id, row)}</td>`).join("")}</tr>`).join("")}`).join("");
  $("#detail-table").innerHTML = `
    <thead><tr><th class="l">Metric</th>${sts.map(st => `<th class="${CLS[st.key]}">${esc(st.short)}</th>`).join("")}</tr></thead>
    <tbody>${body}</tbody>`;
}

function renderCostDetails(c) {
  const [A, B1, B2] = scenarioStates(c);
  const cost = st => (st.feasible ? usdFull(st.metrics.total_cost_usd_week) : "N/A");
  const all3 = A.feasible && B1.feasible && B2.feasible;
  const rows = [
    ["Routing disruption (fleet unchanged)", "Cost(Unchanged Fleet) − Cost(Baseline)", A.feasible && B1.feasible ? usdFull(c.fixed_fleet_impact_usd_week) : "N/A"],
    ["Fleet reoptimization savings", "Cost(Unchanged Fleet) − Cost(Optimized Fleet)", all3 ? usdFull(c.reoptimization_savings_usd_week) : "N/A"],
    ["Net impact vs Baseline (optimized)", "Cost(Optimized Fleet) − Cost(Baseline)", A.feasible && B2.feasible ? usdFull(c.disruption_impact_usd_week) : "N/A"],
  ];
  const recon = all3
    ? `Reconciliation: routing disruption − reoptimization savings = ${usdFull(c.fixed_fleet_impact_usd_week - c.reoptimization_savings_usd_week)} = net impact ${usdFull(c.disruption_impact_usd_week)}.`
    : "Reconciliation not applicable: at least one plan is infeasible.";
  $("#cost-details").innerHTML = `
    <table class="data recon"><thead><tr><th class="l">Item</th><th class="l">Formula</th><th>USD / week</th></tr></thead><tbody>
      <tr><td>Baseline total</td><td>Σ services (fuel + vessel operating)</td><td class="num">${cost(A)}</td></tr>
      <tr><td>Unchanged Fleet total</td><td>Baseline vessel counts, speeds recomputed for full Cape</td><td class="num">${cost(B1)}</td></tr>
      <tr><td>Optimized Fleet total</td><td>SCIP optimum for full Cape</td><td class="num">${cost(B2)}</td></tr>
      ${rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td class="num">${r[2]}</td></tr>`).join("")}
    </tbody></table>
    <p class="small muted">${recon} Weekly fuel per service = p · c · D · v²; incremental vessel operating cost = h · vessels.
      All values from the current API response.</p>`;
}

function renderSolverDetails(c) {
  const t = (c.a.solve_time_ms || 0) + (c.b.solve_time_ms || 0);
  $("#solver-details").innerHTML = `Baseline: <b>${esc(c.a.status)}</b> · Optimized Fleet: <b>${esc(c.b.status)}</b> (OR-Tools SCIP,
    ${t.toFixed(0)} ms in total) · ${c.a.model_size.binary_variables} binary variables and ${c.a.model_size.constraints} constraints per
    scenario · Unchanged Fleet evaluated directly with the Baseline vessel counts · every plan passed independent verification of all
    constraints and costs.`;
}

// 2 · Fleet movement comparison
function renderServiceFilter() {
  const checks = state.runInput.services.map(s => `
    <label class="svc-check ${maps && maps.highlight === s.service_id ? "hl" : ""}" style="color:${serviceColor(s.service_id)}">
      <input type="checkbox" data-svc-check="${esc(s.service_id)}" ${state.visibleServices.has(s.service_id) ? "checked" : ""}>
      <span class="bar" style="background:${serviceColor(s.service_id)}"></span><span style="color:var(--ink)">${esc(s.service_id)}</span></label>`).join("");
  $("#svc-filter").innerHTML = `<span class="lbl">Show services:</span>${checks}
    <button class="btn" data-svc-all>All</button><button class="btn" data-svc-clear>Clear</button>`;
}

function renderMapInfo() {
  for (const st of scenarioStates(state.comparison)) {
    const el = $(`[data-info="${st.key}"]`);
    if (!st.feasible) { el.classList.add("hidden"); continue; }
    el.classList.remove("hidden");
    const shown = st.services.filter(s => state.visibleServices.has(s.service_id));
    if (!shown.length) { el.innerHTML = '<div class="empty">No services selected</div>'; continue; }
    const rows = shown.map(s => `<tr><td><span class="swatch" style="background:${serviceColor(s.service_id)}"></span>${esc(s.service_id)}</td>
      <td>${s.selected_vessels}</td><td>${num(s.speed_knots)}</td></tr>`).join("");
    const foot = shown.length === st.services.length
      ? `<tfoot><tr><td>Fleet</td><td>${st.metrics.allocated_vessels}</td><td>${st.metrics.idle_vessels} idle</td></tr></tfoot>` : "";
    el.innerHTML = `<table><thead><tr><th>Service</th><th>Vessels</th><th>Speed (kn)</th></tr></thead><tbody>${rows}</tbody>${foot}</table>`;
  }
}

function renderMaps() {
  if (!maps) return;
  renderServiceFilter();
  const plans = {};
  for (const st of scenarioStates(state.comparison)) {
    plans[st.key] = { routing: state.config.scenarios[st.scenario].routing, plan: st.feasible ? st.services : null };
    const overlay = $(`[data-overlay="${st.key}"]`);
    if (st.feasible) overlay.classList.add("hidden");
    else {
      overlay.innerHTML = `<div><b>${esc(st.short)} is infeasible — no fleet animation.</b>
        <p>${st.key === "b_fixed" ? "With the Baseline vessel counts, full Cape routing cannot keep weekly departures." : "No feasible allocation exists for this plan."}</p>
        <ul>${infeasibleReasons(st).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
      overlay.classList.remove("hidden");
    }
  }
  maps.setFilter(state.visibleServices);
  maps.load(plans, state.runInput.services);
  renderMapInfo();
}

// Display only — never reruns the optimization or resets the clock.
function setVisibleServices(ids) {
  state.visibleServices = new Set(ids);
  if (maps) maps.setFilter(state.visibleServices);
  renderServiceFilter();
  renderMapInfo();
}

function renderResults() {
  const c = state.comparison;
  $("#results-body").classList.toggle("hidden", !c);
  if (!c) return;
  if (allOptimal(c)) setResultsStatus("ok", "");
  else setResultsStatus("stale", "<b>Plans found — optimality not proven</b> for at least one scenario; figures are feasible but may not be minimal.");
  renderPlanFlow(c);
  renderRecBanner(c);
  renderMaps();
  renderFleetTable(c);
  renderCharts(c);
  renderWhatChanged(c);
  renderDetail(c);
  renderCostDetails(c);
  renderSolverDetails(c);
}

// ---------- API ----------
async function post(url, body) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify(body), signal: ctrl.signal });
    const j = await r.json().catch(() => ({}));
    if (r.status === 422) throw { kind: "validation", detail: j.detail };
    if (!r.ok) throw { kind: "server", detail: j.detail || `HTTP ${r.status}` };
    return j;
  } catch (e) {
    if (e.name === "AbortError") throw { kind: "server", detail: "Request timed out." };
    if (e.kind) throw e;
    throw { kind: "server", detail: "Cannot reach the server." };
  } finally { clearTimeout(timer); }
}

function errorHtml(e) {
  if (e.kind === "validation") {
    const items = (Array.isArray(e.detail) ? e.detail : [{ msg: String(e.detail) }])
      .map(d => `<li>${esc((d.loc || []).filter(x => x !== "body").join(" › "))}${d.loc ? ": " : ""}${esc(d.msg)}</li>`).join("");
    return `<b>Input validation failed</b> — please correct in Scenario Configuration:<ul>${items}</ul>`;
  }
  return `<b>Server error</b> — ${esc(e.detail)}`;
}

async function runCompare() {
  if (state.busy) return;
  state.busy = true;
  const buttons = [$("#btn-compare"), $("#btn-compare-2"), $("#btn-rerun")];
  const labels = buttons.map(b => b.textContent);
  buttons.forEach(b => { b.disabled = true; b.textContent = "Running optimization…"; });
  const msg = "Running OR-Tools SCIP for mixed routing and full Cape…";
  setInputMessage("loading", msg);
  setResultsStatus("loading", msg);
  const snapshot = structuredClone(state.input);
  try {
    state.comparison = await post("/api/compare", snapshot);
    state.runInput = snapshot;
    state.visibleServices = new Set(snapshot.services.map(s => s.service_id));
    clearStale();
    setInputMessage(null, "");
    goto("results");
    renderResults();
  } catch (e) {
    state.comparison = null;  // never keep results that do not match the inputs
    state.runInput = null;
    clearStale();
    renderResults();
    setResultsStatus("error", errorHtml(e));
    setInputMessage("error", errorHtml(e));
  } finally {
    buttons.forEach((b, i) => { b.disabled = false; b.textContent = labels[i]; });
    state.busy = false;
  }
}

// ---------- init ----------
async function init() {
  try {
    state.config = await (await fetch("/api/config")).json();
  } catch {
    setResultsStatus("error", "<b>Cannot load configuration from the server.</b>");
    return;
  }
  state.input = structuredClone(state.config.defaults);
  renderModelPage();
  renderServiceEditor();
  renderRules();

  document.addEventListener("input", e => {
    const chk = e.target.closest && e.target.closest("[data-svc-check]");
    if (chk) {
      const ids = new Set(state.visibleServices);
      if (chk.checked) ids.add(chk.dataset.svcCheck); else ids.delete(chk.dataset.svcCheck);
      setVisibleServices(state.runInput.services.map(s => s.service_id).filter(id => ids.has(id)));
      return;
    }
    onInput(e);
  });
  // cost breakdown chart is rendered when its collapsed section is opened (Plotly needs a visible container)
  ["#detailed", "#fold-breakdown"].forEach(id => $(id).addEventListener("toggle", () => {
    if (state.comparison && $("#detailed").open && $("#fold-breakdown").open) {
      renderCostBreakdown($("#chart-breakdown"), scenarioStates(state.comparison).filter(st => st.feasible));
    }
  }));
  document.addEventListener("click", e => {
    const nav = e.target.closest(".nav-item");
    if (nav) goto(nav.dataset.page);
    const link = e.target.closest("[data-goto]");
    if (link) { e.preventDefault(); goto(link.dataset.goto); }
    if (e.target.closest("[data-svc-all]")) setVisibleServices(state.runInput.services.map(s => s.service_id));
    if (e.target.closest("[data-svc-clear]")) setVisibleServices([]);
  });
  ["#btn-compare", "#btn-compare-2", "#btn-rerun"].forEach(id => $(id).addEventListener("click", runCompare));
  $("#btn-reset").addEventListener("click", () => {
    state.input = structuredClone(state.config.defaults);
    renderServiceEditor(); renderRules(); syncInputs(); markStale();
    setInputMessage(null, "");
  });

  maps = new MapSync(Object.fromEntries(SCENARIO_ORDER.map(k => [k, $(`[data-map="${k}"]`)])), {
    play: $("#map-play"), reset: $("#map-reset"), overview: $("#map-overview"),
    scrub: $("#map-scrub"), day: $("#map-day"), rate: $("#map-rate"),
  }, state.config.routes, () => renderServiceFilter());
  window.fleetMaps = maps;  // inspection hook for browser tests

  runCompare();  // the dashboard opens on a real optimization of the default scenario
}

window.addEventListener("load", init);
