"""Default inputs, scenarios, port rotations and map waypoints.

Services are CMA CGM Asia-North Europe loops (FAL2, FAL3, FAL5) with port rotations
taken from public carrier/port announcements (see SOURCES). Leg distances are
NOT typed in: they are the great-circle length of the authored sea-lane
waypoints below (the same paths the map draws), checked in tests against a
published Shanghai-Rotterdam reference. All economic values are illustrative,
not CMA CGM financial or operational data.
"""
from app.modeling import polyline_nm

# --- Scenarios: which route variant each direction uses -------------------
# westbound = Asia -> Europe, eastbound = Europe -> Asia.
SCENARIOS = {
    "mixed_routing": {
        "label": "Mixed routing (baseline)",
        "short": "Mixed",
        "routing": {"westbound": "cape", "eastbound": "suez"},
        "description": "Westbound Asia→Europe via the Cape of Good Hope; eastbound Europe→Asia via Suez / Red Sea.",
    },
    "full_cape": {
        "label": "Red Sea disruption (full Cape)",
        "short": "Full Cape",
        "routing": {"westbound": "cape", "eastbound": "cape"},
        "description": "Both directions via the Cape of Good Hope; no Suez / Red Sea transit.",
    },
}

# --- Ports (approximate terminal coordinates) ----------------------------
P = {
    "Qingdao": [36.0, 120.3], "Shanghai": [30.6, 122.1], "Ningbo": [29.9, 122.0],
    "Xiamen": [24.45, 118.1], "Nansha": [22.7, 113.65], "Shekou": [22.47, 113.88],
    "Yantian": [22.55, 114.28], "Vung Tau": [10.3, 107.05], "Singapore": [1.25, 103.8],
    "Port Klang": [3.0, 101.35], "Tangier": [35.88, -5.5], "Le Havre": [49.48, 0.1],
    "Dunkirk": [51.05, 2.35], "Southampton": [50.88, -1.4], "Gdansk": [54.4, 18.67],
    "Rotterdam": [51.95, 4.05], "Hamburg": [53.55, 9.95], "Antwerp": [51.28, 4.3],
    "Tianjin Xingang": [38.98, 117.85], "Dalian": [38.93, 121.68], "Felixstowe": [51.95, 1.33],
    "Zeebrugge": [51.35, 3.2], "Wilhelmshaven": [53.58, 8.15],
}


def port(name):
    return [*P[name], name]


def rev(points):
    return list(reversed(points))


# --- Reusable sea-lane segments (lat, lon), drawn to stay at sea ----------
EAST_CHINA_TO_TAIWAN_STRAIT = [[27.0, 121.2], [25.9, 120.6], [24.5, 119.8]]
TAIWAN_STRAIT_TO_PRD = [[23.2, 117.6], [22.2, 115.5], [22.4, 114.45]]
PRD_TO_SINGAPORE = [[21.6, 114.6], [18.0, 113.0], [12.0, 110.3], [5.0, 105.8], [1.4, 104.6]]
SINGAPORE_TO_MALACCA_NORTH = [[1.15, 103.5], [2.0, 102.0], [3.0, 100.6], [5.5, 97.5], [6.5, 95.0]]
MALACCA_NORTH_TO_SRI_LANKA = [[5.6, 80.5]]
SRI_LANKA_TO_SUEZ = [[11.5, 60.0], [13.2, 52.0], [12.3, 46.0], [12.6, 43.4], [15.5, 41.8], [20.0, 38.8],
                     [24.0, 36.2], [27.5, 34.0], [29.5, 32.6], [30.5, 32.35], [31.4, 32.35]]
PORT_SAID_TO_SICILY_CHANNEL = [[33.5, 28.0], [35.5, 18.0]]
SICILY_CHANNEL_TO_GIBRALTAR = [[37.4, 11.2], [38.0, 8.0], [37.4, 3.0], [36.3, -2.0], [35.95, -5.6]]
MALACCA_TO_CAPE = [[-5.0, 80.0], [-20.0, 60.0], [-30.0, 40.0], [-35.0, 25.0], [-35.2, 18.5]]
CAPE_TO_CANARIES = [[-30.0, 13.0], [-20.0, 6.0], [-5.0, -5.0], [10.0, -20.0], [16.0, -19.0], [25.0, -19.5], [31.0, -17.0]]
CANARIES_TO_FINISTERRE = [[36.8, -10.0], [43.5, -9.8]]
FINISTERRE_TO_CHANNEL = [[48.5, -5.5], [50.0, -2.5]]
CANARIES_TO_GIBRALTAR = [[35.5, -7.0], [35.95, -5.8]]
GIBRALTAR_TO_FINISTERRE = [[36.8, -9.5], [43.5, -9.8]]
CHANNEL_TO_DOVER = [[50.3, -0.5], [50.9, 1.3]]
DOVER_TO_SKAGEN = [[52.0, 3.0], [53.5, 5.0], [54.5, 7.0], [56.0, 7.5], [57.6, 9.5], [57.95, 10.8]]
SKAGEN_TO_GDANSK = [[56.8, 11.8], [55.7, 11.0], [54.8, 11.0], [54.5, 12.5], [54.75, 14.5], [55.0, 18.0], [54.75, 19.0]]
NORTH_SEA_TO_ELBE = [[53.5, 5.0], [54.0, 7.5], [53.9, 8.6]]
SOLENT = [[50.7, -0.95], [50.78, -1.15]]  # east approach to Southampton, avoids Isle of Wight
ATLANTIC_TO_INDIAN_EASTBOUND = rev(CAPE_TO_CANARIES) + rev(MALACCA_TO_CAPE) + [[5.8, 90.0], [6.5, 95.0], [5.5, 97.5], [3.0, 100.6]]
PORT_KLANG_TO_TAIWAN_STRAIT = [[2.0, 102.0], [1.15, 103.5]] + rev(PRD_TO_SINGAPORE) + [[22.2, 115.5], [23.2, 117.6]] + [[24.5, 119.8], [25.9, 120.6], [27.0, 121.2]]
INDIAN_FROM_SUEZ_TO_PORT_KLANG = rev(SRI_LANKA_TO_SUEZ) + [[5.6, 80.5], [6.5, 95.0], [5.5, 97.5], [3.0, 100.6]]

ASIA_TO_CAPE = SINGAPORE_TO_MALACCA_NORTH + MALACCA_TO_CAPE + CAPE_TO_CANARIES
# Eastbound from the Strait of Malacca (after Suez or Cape) to Singapore, then north to the Taiwan Strait
MALACCA_TO_SINGAPORE = [[2.0, 102.0], [1.15, 103.5]]
SINGAPORE_TO_TAIWAN_STRAIT = [[1.4, 104.6], *rev(PRD_TO_SINGAPORE)[1:], [22.2, 115.5], [23.2, 117.6],
                              [24.5, 119.8], [25.9, 120.6], [27.0, 121.2]]
EAST_CHINA_SEA_TO_QINGDAO = [[31.0, 123.0], [34.5, 122.5], [35.6, 120.8]]
BOHAI = [[38.7, 119.5], [38.3, 121.0]]  # Tianjin Xingang <-> Bohai Strait
SUEZ_EASTBOUND = [*rev(GIBRALTAR_TO_FINISTERRE), *rev(SICILY_CHANNEL_TO_GIBRALTAR), *rev(PORT_SAID_TO_SICILY_CHANNEL),
                  *INDIAN_FROM_SUEZ_TO_PORT_KLANG]
CAPE_EASTBOUND = [[43.5, -9.8], *ATLANTIC_TO_INDIAN_EASTBOUND]

# --- Service rotations: per direction and route variant ------------------
# Westbound ends at the first European call; eastbound runs from there via the remaining
# European calls back to the Asian origin (the Suez/Cape choice is in the eastbound ocean leg).
_FAL2_EUROPE = [port("Rotterdam"), [52.3, 3.9], *NORTH_SEA_TO_ELBE, port("Hamburg"), *rev(NORTH_SEA_TO_ELBE),
                [51.8, 3.3], [51.42, 3.5], port("Antwerp"), [51.42, 3.5], [51.0, 1.6], *rev(CHANNEL_TO_DOVER)[1:],
                *rev(FINISTERRE_TO_CHANNEL)]
_FAL2_ASIA_HOME = [*MALACCA_TO_SINGAPORE, port("Singapore"), *SINGAPORE_TO_TAIWAN_STRAIT, *EAST_CHINA_SEA_TO_QINGDAO[:2],
                   [37.5, 123.2], *rev(BOHAI), port("Tianjin Xingang")]
_FAL5_EUROPE = [port("Felixstowe"), [51.7, 1.9], [51.45, 3.0], port("Zeebrugge"), [51.6, 3.0], *DOVER_TO_SKAGEN,
                *SKAGEN_TO_GDANSK, port("Gdansk"), *rev(SKAGEN_TO_GDANSK), *rev(DOVER_TO_SKAGEN)[:4], [53.9, 7.9],
                port("Wilhelmshaven"), [53.9, 7.9], [53.5, 5.0], [52.0, 3.0], [51.0, 1.6], *rev(CHANNEL_TO_DOVER)[1:],
                *rev(FINISTERRE_TO_CHANNEL)]
_FAL5_ASIA_HOME = [*MALACCA_TO_SINGAPORE, port("Singapore"), [1.4, 104.6], *rev(PRD_TO_SINGAPORE)[1:], port("Yantian"),
                   *TAIWAN_STRAIT_TO_PRD[::-1], [24.5, 119.8], [25.9, 120.6], [27.0, 121.2],
                   *EAST_CHINA_SEA_TO_QINGDAO, port("Qingdao")]

ROUTES = {
    "FAL2": {
        "ports_note": "Tianjin Xingang – Dalian – Qingdao – Shanghai – Ningbo – Singapore – Rotterdam – Hamburg – "
                      "Antwerp – Singapore – Tianjin Xingang (eastbound Singapore call assumed: 10 calls published, 9 named)",
        "westbound": {
            "cape": [port("Tianjin Xingang"), *BOHAI, [38.75, 121.8], port("Dalian"), [38.5, 122.3], [37.5, 123.2],
                     [36.6, 122.6], [35.9, 120.6], port("Qingdao"), [35.4, 121.2], [32.5, 123.0], port("Shanghai"),
                     port("Ningbo"), *EAST_CHINA_TO_TAIWAN_STRAIT, *TAIWAN_STRAIT_TO_PRD, *PRD_TO_SINGAPORE,
                     port("Singapore"), *ASIA_TO_CAPE, *CANARIES_TO_FINISTERRE, *FINISTERRE_TO_CHANNEL,
                     [50.3, 0.4], [50.9, 1.4], [51.6, 3.0], port("Rotterdam")],
        },
        "eastbound": {
            "suez": [*_FAL2_EUROPE, *SUEZ_EASTBOUND, *_FAL2_ASIA_HOME],
            "cape": [*_FAL2_EUROPE, *CAPE_EASTBOUND, *_FAL2_ASIA_HOME],
        },
    },
    "FAL3": {
        "ports_note": "Ningbo – Shanghai – Yantian – Singapore – Le Havre – Rotterdam – Hamburg – Antwerp – "
                      "Tangier – Port Klang – Ningbo",
        "westbound": {
            "cape": [port("Ningbo"), port("Shanghai"), *EAST_CHINA_TO_TAIWAN_STRAIT, *TAIWAN_STRAIT_TO_PRD,
                     port("Yantian"), *PRD_TO_SINGAPORE, port("Singapore"), *ASIA_TO_CAPE, *CANARIES_TO_FINISTERRE,
                     *FINISTERRE_TO_CHANNEL, [49.8, -0.4], port("Le Havre"), [50.3, 0.4], [50.9, 1.4], [51.6, 3.0],
                     port("Rotterdam"), [52.3, 3.9], *NORTH_SEA_TO_ELBE, port("Hamburg")],
        },
        "eastbound": {
            "suez": [port("Hamburg"), *rev(NORTH_SEA_TO_ELBE), [51.8, 3.3], [51.42, 3.5], port("Antwerp"), [51.42, 3.5],
                     [51.0, 1.6], *rev(CHANNEL_TO_DOVER)[1:], *rev(FINISTERRE_TO_CHANNEL), *rev(GIBRALTAR_TO_FINISTERRE),
                     port("Tangier"), *rev(SICILY_CHANNEL_TO_GIBRALTAR)[1:], *rev(PORT_SAID_TO_SICILY_CHANNEL),
                     *INDIAN_FROM_SUEZ_TO_PORT_KLANG, port("Port Klang"), *PORT_KLANG_TO_TAIWAN_STRAIT, port("Ningbo")],
            "cape": [port("Hamburg"), *rev(NORTH_SEA_TO_ELBE), [51.8, 3.3], [51.42, 3.5], port("Antwerp"), [51.42, 3.5],
                     [51.0, 1.6], *rev(CHANNEL_TO_DOVER)[1:], *rev(FINISTERRE_TO_CHANNEL), *rev(GIBRALTAR_TO_FINISTERRE),
                     port("Tangier"), *rev(CANARIES_TO_GIBRALTAR), *ATLANTIC_TO_INDIAN_EASTBOUND, port("Port Klang"),
                     *PORT_KLANG_TO_TAIWAN_STRAIT, port("Ningbo")],
        },
    },
    "FAL5": {
        "ports_note": "Qingdao – Shanghai – Ningbo – Xiamen – Yantian – Singapore – Felixstowe – Zeebrugge – Gdansk – "
                      "Wilhelmshaven – Singapore – Yantian – Qingdao",
        "westbound": {
            "cape": [port("Qingdao"), [35.4, 121.2], [32.5, 123.0], port("Shanghai"), port("Ningbo"),
                     *EAST_CHINA_TO_TAIWAN_STRAIT, [24.3, 118.6], port("Xiamen"), *TAIWAN_STRAIT_TO_PRD,
                     port("Yantian"), *PRD_TO_SINGAPORE, port("Singapore"), *ASIA_TO_CAPE, *CANARIES_TO_FINISTERRE,
                     *FINISTERRE_TO_CHANNEL, *CHANNEL_TO_DOVER, [51.5, 1.8], port("Felixstowe")],
        },
        "eastbound": {
            "suez": [*_FAL5_EUROPE, *SUEZ_EASTBOUND, *_FAL5_ASIA_HOME],
            "cape": [*_FAL5_EUROPE, *CAPE_EASTBOUND, *_FAL5_ASIA_HOME],
        },
    },
}

# Reference route for validating the waypoint geometry (test only):
# Shanghai -> Rotterdam, published ~10,600 nm via Suez and ~13,800 nm via Cape.
REFERENCE_SHANGHAI_ROTTERDAM = {
    "suez": [port("Shanghai"), *EAST_CHINA_TO_TAIWAN_STRAIT, *TAIWAN_STRAIT_TO_PRD, *PRD_TO_SINGAPORE,
             port("Singapore"), *SINGAPORE_TO_MALACCA_NORTH, *MALACCA_NORTH_TO_SRI_LANKA, *SRI_LANKA_TO_SUEZ,
             *PORT_SAID_TO_SICILY_CHANNEL, *SICILY_CHANNEL_TO_GIBRALTAR, *GIBRALTAR_TO_FINISTERRE,
             *FINISTERRE_TO_CHANNEL, *CHANNEL_TO_DOVER, [51.6, 3.0], port("Rotterdam")],
    "cape": [port("Shanghai"), *EAST_CHINA_TO_TAIWAN_STRAIT, *TAIWAN_STRAIT_TO_PRD, *PRD_TO_SINGAPORE,
             port("Singapore"), *ASIA_TO_CAPE, *CANARIES_TO_FINISTERRE, *FINISTERRE_TO_CHANNEL, *CHANNEL_TO_DOVER,
             [51.6, 3.0], port("Rotterdam")],
    "published_nm": {"suez": 10600, "cape": 13800},
}

PORT_DAYS_PER_CALL = 1.5  # illustrative average berth time per call for large vessels at major hubs (assumption)


def _port_calls(sid):
    """Port calls in one full loop (turnaround port counted once, origin once)."""
    r = ROUTES[sid]
    wb = [p[2] for p in r["westbound"]["cape"] if len(p) > 2]
    eb = [p[2] for p in next(iter(r["eastbound"].values())) if len(p) > 2]
    return wb + eb[1:-1]


def _leg_nm(sid, direction, variant):
    return round(polyline_nm(ROUTES[sid][direction][variant]))


SERVICE_IDS = ("FAL2", "FAL3", "FAL5")
# Published deployments during full-Cape routing (context only; never used as model inputs)
SERVICE_META = {
    "FAL2": {"name": "FAL2 · French Asia Line 2 (North China – North Europe)", "published_vessels_full_cape": 14,
             "published_loop_days": 98},
    "FAL3": {"name": "FAL3 · French Asia Line 3 (Asia – North Europe)", "published_vessels_full_cape": 15,
             "published_loop_days": 105},
    "FAL5": {"name": "FAL5 · French Asia Line 5 (Asia – UK / Baltic)", "published_vessels_full_cape": 15,
             "published_loop_days": 105},
}

DEFAULT_INPUT = {
    "fleet": {
        "available_vessels": 44,  # 14 + 15 + 15 ships published for FAL2/FAL3/FAL5 under full Cape routing
        "min_speed_knots": 12.0,
        "max_speed_knots": 22.0,
        "reference_speed_knots": 18.0,
        "reference_fuel_tonnes_per_day": 100.0,
    },
    "economics": {
        "fuel_price_usd_per_tonne": 600.0,
        "deployment_cost_usd_per_vessel_week": 150000.0,
    },
    "services": [
        {
            "service_id": sid,
            "name": SERVICE_META[sid]["name"],
            "legs": {
                "westbound": {"cape": _leg_nm(sid, "westbound", "cape")},
                "eastbound": {"suez": _leg_nm(sid, "eastbound", "suez"), "cape": _leg_nm(sid, "eastbound", "cape")},
            },
            "port_days": PORT_DAYS_PER_CALL * len(_port_calls(sid)),
        }
        for sid in SERVICE_IDS
    ],
    "rules": {
        "max_fleet_per_service": {"enabled": False, "limits": {sid: 15 for sid in SERVICE_IDS}},
        "minimum_schedule_buffer": {"enabled": True, "days_by_service": {sid: 2.0 for sid in SERVICE_IDS}},
        "maximum_round_trip_time": {"enabled": False, "days_by_service": {sid: 105.0 for sid in SERVICE_IDS}},
    },
}

SOURCES = {
    "rotations": "Port rotations: FAL2 and FAL5 — Zencargo 'Carrier networks 2025: Asia – Europe' (Feb 2025), FAL5 also "
                 "CMA CGM service flyer (as indexed by search); FAL3 — Tanger Med Port Authority (June 2025) and TZP News "
                 "(Aug 2026). FAL2's eastbound Singapore call is an assumption (10 calls published, 9 named).",
    "routing": "Eastbound Suez returns were reported for some Ocean Alliance Asia–North Europe loops in 2026 (e.g. FAL3 "
               "from 22 Jul 2026, Linerlytica). Scenarios here are illustrative planning cases, not the routing of "
               "FAL2/FAL3/FAL5 at any date.",
    "fleet": "Published deployments for context: FAL2 14 vessels / 98 days, FAL5 15 vessels / 105 days (Zencargo, "
             "Feb 2025); FAL3 15-week rotation (Assahifa, early 2025). Default available fleet 44 = 14 + 15 + 15. "
             "Treating these vessels as one homogeneous, jointly allocatable fleet is an illustrative modeling assumption, "
             "not a claim about CMA CGM's actual vessel ownership or deployment flexibility.",
    "distances": "Leg distances = great-circle length of authored sea-lane waypoints through the named ports; "
                 "geometry checked against the published Shanghai–Rotterdam distance (~10,600 nm via Suez, "
                 "~13,800 nm via Cape; Port Economics, Management and Policy).",
    "economics": "Fuel curve (100 t/day at 18 kn), bunker price, incremental vessel operating cost and port days "
                 "(1.5 days per call) are illustrative assumptions, not CMA CGM data.",
}

INPUT_BOUNDS = {
    "max_services": 6,
    "available_vessels": {"min": 1, "max": 200},
    "speed_knots": {"min": 1.0, "max": 30.0},
    "fuel_price_usd_per_tonne": {"min": 1.0, "max": 3000.0},
    "deployment_cost_usd_per_vessel_week": {"min": 0.0, "max": 2_000_000.0},
    "reference_fuel_tonnes_per_day": {"min": 1.0, "max": 500.0},
    "leg_nm": {"min": 100.0, "max": 40000.0},
    "port_days": {"min": 0.0, "max": 60.0},
    "max_fleet_per_service": {"min": 1, "max": 200},
    "minimum_schedule_buffer_days": {"min": 0.0, "max": 30.0},
    "maximum_round_trip_days": {"min": 1.0, "max": 365.0},
}

DISCLAIMERS = [
    "Service names and port rotations from public sources; distances, costs and fuel data are illustrative estimates — not CMA CGM operational or financial data.",
    "The two routing scenarios are hypothetical planning cases, not a statement of current routing.",
    "Map animation is a stylized steady state — not live AIS, real ETAs or a repositioning plan.",
]
