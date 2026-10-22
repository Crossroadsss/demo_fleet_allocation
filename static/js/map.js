// Illustrative steady-state fleet animation (01 §9): three scenario maps (A, B1, B2)
// driven by one synthetic clock. Presentation only: ship positions come from each
// plan's optimized vessel count, speed, port time and slack.
import { SERVICE_COLORS } from "./charts.js";

const FPS = 20;
// Asia–Europe overview incl. Suez Canal and Cape of Good Hope
const OVERVIEW = [[-38, -22], [60, 126]];
const LABEL_ZOOM = 5;  // port names appear from this zoom level
const LANDMARKS = [
  { name: "Suez Canal", pos: [30.45, 32.35], dir: "left" },
  { name: "Cape of Good Hope", pos: [-34.36, 18.47], dir: "right" },
];

// One Leaflet map showing one plan.
class ScenarioMap {
  constructor(el, routes, onRouteClick, onBackgroundClick) {
    this.routes = routes;
    this.onRouteClick = onRouteClick;
    this.groups = {};     // service_id -> layerGroup (routes + ships)
    this.lines = {};      // service_id -> [westbound, eastbound] polylines
    this.ships = [];
    this.portMarkers = [];
    this.common = null;
    this.map = L.map(el, { preferCanvas: true, zoomSnap: 0.25, minZoom: 1, attributionControl: false });
    this.map.fitBounds(OVERVIEW);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 8 }).addTo(this.map);
    this.map.on("zoomend", () => this.refreshLabels());
    this.map.on("click", () => onBackgroundClick());
  }

  // routing: {westbound, eastbound}; services: input rows; plan: result rows or null;
  // visible: Set of shown service ids; highlight: service id or null
  show(routing, services, plan, visible, highlight) {
    Object.values(this.groups).forEach(g => g.remove());
    if (this.common) this.common.remove();
    this.groups = {};
    this.lines = {};
    this.ships = [];
    this.portMarkers = [];
    this.common = L.layerGroup().addTo(this.map);
    const byId = Object.fromEntries((plan || []).map(r => [r.service_id, r]));
    const ports = new Map();

    services.forEach((svc, idx) => {
      const route = this.routes[svc.service_id];
      if (!route) return;  // service without authored waypoints
      const color = SERVICE_COLORS[idx % SERVICE_COLORS.length];
      const g = L.layerGroup();
      this.groups[svc.service_id] = g;
      const wb = route.westbound[routing.westbound];
      const eb = route.eastbound[routing.eastbound];
      const via = v => (v === "cape" ? "Cape of Good Hope" : "Suez Canal");
      const wbLine = L.polyline(wb, { color, weight: 2.5, opacity: 0.85 })
        .bindTooltip(`${svc.service_id} westbound (Asia → Europe) via ${via(routing.westbound)} — click to highlight`, { sticky: true }).addTo(g);
      const ebLine = L.polyline(eb, { color, weight: 2.5, opacity: 0.85, dashArray: "8 6" })
        .bindTooltip(`${svc.service_id} eastbound (Europe → Asia) via ${via(routing.eastbound)} — click to highlight`, { sticky: true }).addTo(g);
      for (const line of [wbLine, ebLine]) {
        line.on("click", e => { L.DomEvent.stopPropagation(e); this.onRouteClick(svc.service_id); });
      }
      this.lines[svc.service_id] = [wbLine, ebLine];
      for (const p of [...wb, ...eb]) if (p.length > 2 && !ports.has(p[2])) ports.set(p[2], p);

      const r = byId[svc.service_id];
      if (r) {
        const schedule = buildSchedule(wb, eb, r);
        for (let i = 0; i < r.selected_vessels; i++) {
          const m = L.circleMarker(wb[0], { radius: 4.5, color: "#fff", weight: 1.2, fillColor: color, fillOpacity: 1 }).addTo(g);
          const ship = { marker: m, svc, r, schedule, i, routing };
          m.bindTooltip(() => shipTooltip(ship, this.day || 0));
          this.ships.push(ship);
        }
      }
    });
    for (const [name, pos] of ports) {
      const m = L.circleMarker(pos, { radius: 2.5, color: "#142235", weight: 1, fillColor: "#fff", fillOpacity: 1 }).addTo(this.common);
      m.bindTooltip(name, { direction: "right", offset: [4, 0], className: "port-label" });
      this.portMarkers.push(m);
    }
    for (const lm of LANDMARKS) {
      L.circleMarker(lm.pos, { radius: 4, color: "#0f2a4a", weight: 2, fillColor: "#f3c969", fillOpacity: 1 })
        .bindTooltip(lm.name, { permanent: true, direction: lm.dir, offset: [lm.dir === "left" ? -5 : 5, 0], className: "landmark-label" })
        .addTo(this.common);
    }
    this.setFilter(visible);
    this.setHighlight(highlight);
    this.refreshLabels();
  }

  setFilter(visible) {
    for (const [sid, g] of Object.entries(this.groups)) {
      if (visible.has(sid)) g.addTo(this.map); else g.remove();
    }
  }

  // Emphasize one service; others stay visible but dimmed (nothing is hidden by a click).
  setHighlight(sid) {
    for (const [id, lines] of Object.entries(this.lines)) {
      const on = !sid || id === sid;
      lines.forEach(l => l.setStyle({ weight: id === sid ? 4.5 : 2.5, opacity: on ? 0.9 : 0.22 }));
      if (id === sid) lines.forEach(l => l.bringToFront());
    }
    for (const ship of this.ships) {
      const on = !sid || ship.svc.service_id === sid;
      ship.marker.setStyle({ fillOpacity: on ? 1 : 0.25, opacity: on ? 1 : 0.25 });
    }
  }

  refreshLabels() {
    const zoomed = this.map.getZoom() >= LABEL_ZOOM;
    for (const m of this.portMarkers) {
      const t = m.getTooltip();
      if (t.options.permanent !== zoomed) {
        const name = t.getContent();
        m.unbindTooltip();
        m.bindTooltip(name, { permanent: zoomed, direction: "right", offset: [4, 0], className: "port-label" });
      }
    }
  }

  render(day) {
    this.day = day;
    for (const ship of this.ships) {
      const st = stateAt(ship.schedule, phaseOf(day, ship.i, ship.r.scheduled_rotation_days));
      ship.marker.setLatLng(st.pos);
      if (ship.marker.isTooltipOpen()) ship.marker.setTooltipContent(shipTooltip(ship, day));
    }
  }
}

// Three maps, one clock, one set of controls, one service filter, synchronized pan/zoom.
export class MapSync {
  constructor(mapEls, controls, routes, onHighlight) {
    this.controls = controls;  // {play, reset, overview, scrub, day, rate}
    this.day = 0;
    this.playing = false;
    this.visible = new Set(Object.keys(routes));
    this.highlight = null;
    this.onHighlight = onHighlight || (() => {});
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.available = !!window.L;
    if (!this.available) {
      Object.values(mapEls).forEach(el => (el.innerHTML = '<div class="map-fallback">Map unavailable (offline). Results above remain complete.</div>'));
      Object.values(controls).forEach(c => c && (c.disabled = true));
      return;
    }
    const routeClick = sid => this.setHighlight(this.highlight === sid ? null : sid);
    const backgroundClick = () => { if (this.highlight) this.setHighlight(null); };
    this.maps = Object.fromEntries(Object.entries(mapEls).map(([k, el]) => [k, new ScenarioMap(el, routes, routeClick, backgroundClick)]));
    this.syncing = false;
    for (const m of Object.values(this.maps)) {
      m.map.on("move zoomend moveend", () => this.syncView(m));
    }
    controls.play.addEventListener("click", () => this.toggle());
    controls.reset.addEventListener("click", () => { this.day = 0; this.render(); });
    controls.overview.addEventListener("click", () => this.overview());
    controls.scrub.addEventListener("input", () => { this.day = Number(controls.scrub.value); this.render(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) this.pause(); });
  }

  syncView(source) {
    if (this.syncing) return;
    this.syncing = true;
    for (const m of Object.values(this.maps)) {
      if (m !== source) m.map.setView(source.map.getCenter(), source.map.getZoom(), { animate: false });
    }
    this.syncing = false;
  }

  resize() {
    if (!this.available) return;
    Object.values(this.maps).forEach(m => m.map.invalidateSize());
    this.overview();
  }

  overview() {
    if (!this.available) return;
    const first = Object.values(this.maps)[0];
    first.map.fitBounds(OVERVIEW, { padding: [6, 6] });
    this.syncView(first);
  }

  // plans: {a: {routing, plan|null}, b_fixed: {...}, b: {...}} — all from the same optimization run
  load(plans, services) {
    if (!this.available) return;
    this.pause();
    Object.values(this.maps).forEach(m => m.map.invalidateSize());
    for (const [k, m] of Object.entries(this.maps)) m.show(plans[k].routing, services, plans[k].plan, this.visible, this.highlight);
    const rots = Object.values(plans).flatMap(p => (p.plan || []).map(r => r.scheduled_rotation_days));
    this.controls.scrub.max = String(Math.max(28, ...rots));
    this.day = 0;
    this.overview();
    this.render();
    if (Object.values(this.maps).some(m => m.ships.length) && !this.reducedMotion) this.play();
  }

  // Filtering never reruns the optimization or resets the clock.
  setFilter(visibleIds) {
    this.visible = new Set(visibleIds);
    if (this.highlight && !this.visible.has(this.highlight)) this.setHighlight(null);
    if (this.available) Object.values(this.maps).forEach(m => m.setFilter(this.visible));
  }

  setHighlight(sid) {
    this.highlight = sid;
    if (this.available) Object.values(this.maps).forEach(m => m.setHighlight(sid));
    this.onHighlight(sid);
  }

  toggle() { this.playing ? this.pause() : this.play(); }

  play() {
    if (!this.available || this.playing) return;
    this.playing = true;
    this.controls.play.textContent = "❚❚";
    let last = performance.now();
    const tick = now => {
      if (!this.playing) return;
      const dt = (now - last) / 1000;
      if (dt >= 1 / FPS) {
        last = now;
        this.day = (this.day + dt * Number(this.controls.rate.value)) % Number(this.controls.scrub.max);
        this.render();
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  pause() {
    this.playing = false;
    if (this.raf) cancelAnimationFrame(this.raf);
    if (this.controls.play) this.controls.play.textContent = "▶";
  }

  render() {
    this.controls.scrub.value = String(this.day);
    this.controls.day.textContent = this.day.toFixed(0);
    if (this.available) Object.values(this.maps).forEach(m => m.render(this.day));
  }
}

function shipTooltip(ship, day) {
  const st = stateAt(ship.schedule, phaseOf(day, ship.i, ship.r.scheduled_rotation_days));
  const name = `Demo Vessel ${ship.svc.service_id}-${String(ship.i + 1).padStart(2, "0")}`;
  let what;
  if (st.type === "sail") {
    const via = ship.routing[st.dir] === "cape" ? "Cape" : "Suez";
    what = `Sailing ${st.dir} via ${via} · ${ship.r.speed_knots.toFixed(1)} kn (model)`;
  } else if (st.type === "port") what = `In port: ${st.port}`;
  else what = `Schedule slack / layover at ${st.port}`;
  return `${ship.svc.service_id} · ${name}<br>${what}<br>Synthetic day ${day.toFixed(0)}`;
}

export function phaseOf(day, i, rotation) {
  return (((day - 7 * i) % rotation) + rotation) % rotation;
}

// Timeline of one ship's loop: sail segments (time ∝ length, total = model sailing days),
// equal dwell at each named port, then slack at the origin.
export function buildSchedule(wb, eb, r) {
  const loop = [...wb.map(p => ({ p, dir: "westbound" })), ...eb.slice(1).map(p => ({ p, dir: "eastbound" }))];
  const lens = [];
  for (let k = 1; k < loop.length; k++) lens.push(dist(loop[k - 1].p, loop[k].p));
  const totalLen = lens.reduce((a, b) => a + b, 0) || 1;
  const calls = loop.slice(0, -1).filter(x => x.p.length > 2).length;  // final origin = start of next loop
  const portDays = r.active_cycle_days - r.sailing_days;
  const dwell = calls ? portDays / calls : 0;
  const events = [];
  let t = 0;
  for (let k = 0; k < loop.length - 1; k++) {
    const cur = loop[k];
    if (cur.p.length > 2 && dwell > 0) { events.push({ t0: t, t1: t + dwell, type: "port", port: cur.p[2], pos: cur.p }); t += dwell; }
    const d = r.sailing_days * lens[k] / totalLen;
    events.push({ t0: t, t1: t + d, type: "sail", dir: loop[k + 1].dir, a: cur.p, b: loop[k + 1].p });
    t += d;
  }
  events.push({ t0: t, t1: Infinity, type: "slack", port: loop[0].p[2], pos: loop[0].p });
  return events;
}

export function stateAt(events, phase) {
  for (const e of events) {
    if (phase < e.t1) {
      if (e.type !== "sail") return { ...e, pos: [e.pos[0], e.pos[1]] };
      const f = (phase - e.t0) / ((e.t1 - e.t0) || 1);
      return { ...e, pos: [e.a[0] + (e.b[0] - e.a[0]) * f, e.a[1] + (e.b[1] - e.a[1]) * f] };
    }
  }
  const last = events[events.length - 1];
  return { ...last, pos: [last.pos[0], last.pos[1]] };
}

function dist(a, b) {
  const dy = b[0] - a[0], dx = (b[1] - a[1]) * Math.cos(((a[0] + b[0]) / 2) * Math.PI / 180);
  return Math.hypot(dx, dy);
}
