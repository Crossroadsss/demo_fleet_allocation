"""Browser test of the static frontend (static/*): dashboard, configuration, stale handling, maps.

Runs the FastAPI app in a background thread and drives the installed Chrome via
Playwright. Skipped when Playwright or Chrome is unavailable. Needs internet for
the CDN libraries (Plotly, Leaflet, KaTeX); map/chart assertions skip if they are missing.
"""
import json
import re
import socket
import threading
import time

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    from app.main import app
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def page(base_url):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # Chrome not installed
            pytest.skip(f"Chrome not available: {exc}")
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base_url + "/", wait_until="load")
        pg.wait_for_selector("#plan-flow .op-card", timeout=20000)  # auto-run on load
        pg.errors = errors
        yield pg
        browser.close()


def leaflet(page):
    if page.evaluate("typeof window.L === 'undefined'"):
        pytest.skip("Leaflet not loaded (offline)")


def map_info(page, key):
    return page.text_content(f'[data-info="{key}"]')


def run(page, **fields):
    page.click(".nav-item[data-page=inputs]")
    for path, value in fields.items():
        page.fill(f"#page-inputs input[data-path='{path}']", str(value))
    page.click("#btn-compare")
    page.wait_for_function("document.querySelector('#page-results:not(.hidden) #plan-flow .op-card') !== null "
                           "&& !document.querySelector('#btn-compare').disabled")


def test_dashboard_landing_and_page_order(page):
    assert page.is_visible("#page-results")
    nav = [t.replace("stale", "").strip() for t in page.locator(".nav-item").all_text_contents()]
    assert page.locator(".nav-item svg.nav-icon").count() == 3  # business icons instead of numbers
    sizes = page.evaluate("[...document.querySelectorAll('.nav-icon')].map(i => [i.getBoundingClientRect().width, "
                          "i.getAttribute('width')])")
    assert all(w <= 20 and attr == "18" for w, attr in sizes)  # small, and sized even without the stylesheet
    assert nav == ["Decision Dashboard", "Scenario Configuration", "Model & Methodology"]
    assert [h.strip()[1:].strip() for h in page.locator("#results-body h2").all_text_contents()] == [
        "Operating Plan Comparison", "Fleet Movement Comparison", "Fleet Allocation and Sailing Speed"]
    assert "Detailed Analysis" in page.text_content("#detailed > summary")
    assert page.get_attribute("#detailed", "open") is None  # collapsed by default


def test_operator_names_only_no_technical_ids(page):
    visible = page.inner_text("#results-body")
    for name in ["Baseline", "Unchanged Fleet", "Optimized Fleet"]:
        assert name in visible
    assert not re.search(r"\bB[12]\b|\bA\s·", visible)
    assert "NaN" not in visible and "undefined" not in visible


def test_cost_changes_on_arrows_default_zero_savings(page):
    connectors = page.locator("#plan-flow .connector")
    assert connectors.count() == 2
    disrupt, reopt = connectors.nth(0).inner_text(), connectors.nth(1).inner_text()
    assert "ROUTING DISRUPTION" in disrupt.upper() and "+$" in disrupt and "/ week" in disrupt
    assert "FLEET REOPTIMIZATION" in reopt.upper() and "$0 / week saved" in reopt
    banner = page.text_content("#rec-banner")
    assert "Maintain the existing fleet allocation and increase sailing speeds" in banner
    assert "Net impact vs Baseline" in banner and "+$" in banner
    assert page.locator(".op-card").count() == 3 and "proven optimal" in page.text_content("#plan-flow")


def test_fleet_table_and_compact_charts(page):
    head = page.text_content("#fleet-table thead")
    for col in ["Baseline", "Unchanged", "Optimized", "Change"]:
        assert col in head
    assert page.locator("#fleet-table tbody tr").count() == 3
    assert "Total" in page.text_content("#fleet-table tfoot")
    if page.evaluate("typeof window.Plotly !== 'undefined'"):
        assert page.locator("#chart-speed.js-plotly-plot").count() == 1
        assert page.locator("#chart-cost.js-plotly-plot").count() == 1
        # one labeled bar per plan and service, so identical speeds never overlap; no Plotly legend on the plot
        speed = page.evaluate("(() => { const el = document.querySelector('#chart-speed'); return {"
                              "n: el.data.length, types: el.data.map(t => t.type), labels: el.data.map(t => t.text.length),"
                              "legend: el.layout.showlegend}; })()")
        assert speed["n"] == 3 and set(speed["types"]) == {"bar"} and speed["labels"] == [3, 3, 3]
        assert speed["legend"] is False
        assert "Unchanged Fleet" in page.text_content('[data-legend="speed"]')


def test_laptop_width_no_overflow_in_analysis_panels(page):
    page.set_viewport_size({"width": 1366, "height": 768})
    page.wait_for_timeout(400)
    overflow = page.evaluate("[...document.querySelectorAll('.analysis3 .panel')].map(p => p.scrollWidth > p.clientWidth + 1)")
    assert overflow == [False, False, False]
    assert page.text_content("#fleet-table thead").count("Change") == 1
    if page.evaluate("typeof window.Plotly !== 'undefined'"):  # speed and cost plot areas aligned
        boxes = page.evaluate("['#chart-speed', '#chart-cost'].map(s => { const r = document.querySelector(s + ' .nsewdrag')"
                              ".getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom)]; })")
        assert boxes[0] == boxes[1]
    page.set_viewport_size({"width": 1600, "height": 1000})


def test_bar_charts_consistent_legends_units_and_scales(page):
    if page.evaluate("typeof window.Plotly === 'undefined'"):
        pytest.skip("Plotly not loaded (offline)")
    for which in ["speed", "cost"]:
        legend = page.locator(f'[data-legend="{which}"]')
        assert legend.is_visible()
        assert [x.strip() for x in legend.locator("span").all_text_contents()] == ["Baseline", "Unchanged Fleet", "Optimized Fleet"]
    info = page.evaluate("""['#chart-speed', '#chart-cost'].map(s => { const el = document.querySelector(s);
        return { y: el.layout.yaxis.title.text, range: el.layout.yaxis.range, h: el.layout.height,
                 margin: el.layout.margin, n: el.data.length, types: el.data.map(t => t.type),
                 colors: el.data.map(t => t.marker.color) }; })""")
    speed, cost = info
    assert "(kn)" in speed["y"] and "axis starts at" in speed["y"]          # non-zero baseline stated
    assert "USD million/week" in cost["y"] and cost["range"][0] == 0         # cost bars start at zero
    assert speed["h"] == cost["h"] and speed["margin"] == cost["margin"]      # same dimensions
    assert speed["n"] == cost["n"] == 3 and set(speed["types"]) == set(cost["types"]) == {"bar"}
    assert speed["colors"] == cost["colors"]                                  # same scenario colors, same order


def test_configuration_constraints_in_plain_language(page):
    page.click(".nav-item[data-page=inputs]")
    section = page.locator("#page-inputs section", has_text="Business constraints")
    text = section.text_content()
    for label in ["Optional settings", "Always applied", "Maximum Vessels per Service", "Minimum Schedule Buffer",
                  "Maximum Round-Trip Duration", "One Fleet Allocation per Service", "Fleet Availability",
                  "Weekly Departures", "Sailing Speed Limits"]:
        assert label in text
    assert not re.search(r"\bC[1-8]\b", text)
    buffer = section.locator(".rule", has_text="Minimum Schedule Buffer").text_content()
    assert "Spare days built into every round trip" in buffer and "FAL2 (days per round trip)" in buffer
    tmax_box = section.locator(".rule", has_text="Maximum Round-Trip Duration")
    assert "not counting spare buffer days" in tmax_box.text_content()
    tmax_box.locator("input[type=checkbox]").check()  # values appear with the unit label once enabled
    assert "FAL2 (days per round trip)" in tmax_box.text_content()
    tmax_box.locator("input[type=checkbox]").uncheck()
    assert not any(sym in text for sym in ["Σ", "≤", "×"])
    model = page.text_content("#page-model")  # technical IDs and formulas stay on Model & Methodology
    assert all(f"C{i}" in model for i in range(1, 9))


def test_plain_language_settings_control_same_backend_fields(page):
    page.click(".nav-item[data-page=inputs]")
    mapping = {"Maximum Vessels per Service": "max_fleet_per_service",
               "Minimum Schedule Buffer": "minimum_schedule_buffer",
               "Maximum Round-Trip Duration": "maximum_round_trip_time"}
    for label, key in mapping.items():
        box = page.locator("#rules .rule", has_text=label).locator("input[type=checkbox]")
        assert box.get_attribute("data-path") == f"rules.{key}.enabled"
    # enable the vessel cap through its new label and check the request payload
    page.locator("#rules .rule", has_text="Maximum Vessels per Service").locator("input[type=checkbox]").check()
    with page.expect_request("**/api/compare") as req:
        page.click("#btn-compare")
    body = json.loads(req.value.post_data)
    assert body["rules"]["max_fleet_per_service"]["enabled"] is True
    page.wait_for_function("!document.querySelector('#btn-compare').disabled")
    page.click(".nav-item[data-page=inputs]")
    page.locator("#rules .rule", has_text="Maximum Vessels per Service").locator("input[type=checkbox]").uncheck()
    page.click("#btn-compare")
    page.wait_for_function("!document.querySelector('#btn-compare').disabled")


def test_no_banner_and_clean_sidebar(page):
    assert page.locator("#disclaimer, .disclaimer").count() == 0
    foot = page.text_content(".sidebar-foot")
    assert foot.strip() == "Illustrative planning data"
    assert "OR-Tools" not in page.text_content(".sidebar")
    assert "not live tracking" in page.text_content("#page-results")


def test_detailed_analysis_contents(page):
    page.click("#detailed > summary")
    text = page.text_content("#detailed")
    for item in ["Active cycle", "Scheduled rotation", "Schedule slack", "Cost calculation details",
                 "Route distances", "independent verification"]:
        assert item in text
    page.click("#detailed > summary")


def test_service_checkboxes_any_combination(page):
    leaflet(page)
    assert page.locator(".maps3 .leaflet-container").count() == 3
    assert page.locator("#svc-filter input[type=checkbox]").count() == 3
    assert page.locator("#map-legend").count() == 0  # checkboxes are the legend
    if "❚❚" in page.text_content("#map-play"):
        page.click("#map-play")
    page.evaluate("const s = document.querySelector('#map-scrub'); s.value = 30; s.dispatchEvent(new Event('input'))")
    combos = [{"FAL2"}, {"FAL2", "FAL5"}, {"FAL3", "FAL5"}, {"FAL2", "FAL3", "FAL5"}]
    for combo in combos:
        for sid in ["FAL2", "FAL3", "FAL5"]:
            box = f"#svc-filter input[data-svc-check={sid}]"
            if (sid in combo) != page.is_checked(box):
                page.click(box)
        for key in ["a", "b_fixed", "b"]:
            info = map_info(page, key)
            for sid in ["FAL2", "FAL3", "FAL5"]:
                assert (sid in info) == (sid in combo)
    assert page.text_content("#map-day").strip() == "30"  # filtering never resets the clock
    page.click("[data-svc-clear]")
    assert all("No services selected" in map_info(page, k) for k in ["a", "b_fixed", "b"])
    page.click("[data-svc-all]")
    assert all("FAL2" in map_info(page, k) and "Fleet" in map_info(page, k) for k in ["a", "b_fixed", "b"])
    assert "Active" not in map_info(page, "a")  # timing details live in Detailed Analysis


def test_route_click_highlights_across_maps(page):
    leaflet(page)
    page.evaluate("window.fleetMaps.maps.b.onRouteClick('FAL3')")
    assert page.evaluate("window.fleetMaps.highlight") == "FAL3"
    weights = page.evaluate("Object.values(window.fleetMaps.maps).map(m => m.lines.FAL3[0].options.weight)")
    assert weights == [4.5, 4.5, 4.5]
    assert "hl" in page.get_attribute("#svc-filter label:has(input[data-svc-check=FAL3])", "class")
    page.evaluate("window.fleetMaps.maps.a.onRouteClick('FAL3')")  # clicking again clears
    assert page.evaluate("window.fleetMaps.highlight") is None


def test_synchronized_viewport(page):
    leaflet(page)
    page.click("#map-overview")
    page.evaluate("window.fleetMaps.maps.b.map.setZoom(4)")
    page.wait_for_timeout(600)
    assert page.evaluate("Object.values(window.fleetMaps.maps).map(m => m.map.getZoom())") == [4, 4, 4]


def test_model_page_statement(page):
    page.click(".nav-item[data-page=model]")
    text = page.text_content("#page-model")
    assert "FAL2, FAL3, and FAL5 were selected as representative CMA CGM Asia–North Europe liner services" in text
    assert "0–1 MILP" in text and "Unchanged Fleet" in text


def test_stale_and_rerun(page):
    page.click(".nav-item[data-page=inputs]")
    page.fill("input[data-path='economics.fuel_price_usd_per_tonne']", "800")
    assert page.is_visible("#nav-stale")
    page.click(".nav-item[data-page=results]")
    assert "Out of date" in page.text_content("#results-status")
    page.click("#btn-rerun")
    page.wait_for_function("!document.querySelector('#results-body').classList.contains('is-stale')")
    assert page.is_hidden("#nav-stale")


def test_positive_savings_with_spare_vessels(page):
    run(page, **{"economics.fuel_price_usd_per_tonne": 600, "fleet.available_vessels": 50})
    reopt = page.locator("#plan-flow .connector").nth(1).inner_text()
    assert "saved" in reopt and "$0 / week" not in reopt
    assert "Reallocate vessels" in page.text_content("#rec-banner")
    assert page.locator("#fleet-table tr.changed").count() >= 1


def test_infeasible_unchanged_fleet(page):
    run(page, **{"fleet.available_vessels": 50, "fleet.max_speed_knots": 14})
    assert "Infeasible" in page.text_content(".op-card.b1")
    connectors = page.locator("#plan-flow .connector")
    assert "N/A" in connectors.nth(0).inner_text() and "N/A" in connectors.nth(1).inner_text()
    assert "cannot maintain weekly departures" in page.text_content("#rec-banner")
    if page.evaluate("typeof window.L !== 'undefined'"):
        assert page.is_visible('[data-overlay="b_fixed"]') and page.is_hidden('[data-overlay="b"]')


def test_validation_error_clears_results(page):
    page.click(".nav-item[data-page=inputs]")
    page.fill("#page-inputs input[data-path='fleet.min_speed_knots']", "25")
    page.click("#btn-compare")
    page.wait_for_selector("#input-message .status.error")
    assert "min_speed_knots must be <= max_speed_knots" in page.inner_text("#input-message")
    assert page.is_hidden("#results-body")


def test_no_javascript_errors(page):
    assert page.errors == []
