import logging
import math
import threading
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ICAO airline prefix (first 3 letters of the callsign) -> short display name
AIRLINES = {
    "TAM": "LATAM", "LAN": "LATAM", "LPE": "LATAM", "LXP": "LATAM",
    "GLO": "GOL", "AZU": "AZUL", "PTB": "PASSAREDO", "VOE": "VOEPASS",
    "ACN": "AZUL CONECTA", "TTL": "TOTAL", "SID": "SIDERAL", "LTG": "LATAM CARGO",
    "ABJ": "ABAETE", "MWM": "MODERN", "OMI": "OMNI", "TPA": "TAP CARGO",
    "TAP": "TAP", "AAL": "AMERICAN", "UAL": "UNITED", "DAL": "DELTA",
    "AFR": "AIR FRANCE", "KLM": "KLM", "DLH": "LUFTHANSA", "BAW": "BRITISH",
    "IBE": "IBERIA", "AEA": "AIR EUROPA", "ITY": "ITA", "SWR": "SWISS",
    "UAE": "EMIRATES", "QTR": "QATAR", "THY": "TURKISH", "ETH": "ETHIOPIAN",
    "ARG": "AEROLINEAS", "AVA": "AVIANCA", "CMP": "COPA", "SKU": "SKY",
    "JAT": "JETSMART", "FDX": "FEDEX", "UPS": "UPS", "DHL": "DHL", "BOV": "BOA",
    "FAB": "FAB",
}

KNOT_TO_KMH = 1.852
FT_TO_M = 0.3048
NM_TO_KM = 1.852


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Initial compass bearing (0 = north, clockwise) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass_point(deg: float) -> str:
    """Portuguese 8-point compass abbreviation (N, NE, L, SE, S, SO, O, NO)."""
    return ["N", "NE", "L", "SE", "S", "SO", "O", "NO"][int(((deg % 360) + 22.5) // 45) % 8]


class FlightService:
    """
    Finds aircraft near a fixed point using the free adsb.lol API (ADS-B community network) and
    looks up airline routes (origin/destination) on adsbdb.com, cached per callsign.

    The query center is rounded to 2 decimals (~1 km) before being sent to the API, the radius is
    padded to cover the rounding, and exact distances are computed locally from the real point.
    """
    API_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
    ROUTE_URL = "https://api.adsbdb.com/v0/callsign/{callsign}"
    ROUTE_CACHE_SECONDS = 6 * 3600
    HEADERS = {"User-Agent": "streamdeck-flight-radar/1.0"}

    def __init__(self, latitude: float, longitude: float, max_distance_km: float = 5.0,
                 include_ground: bool = False, max_altitude_m: float = None, timeout: float = 10.0):
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.max_distance_km = float(max_distance_km)
        self.include_ground = include_ground
        self.max_altitude_m = float(max_altitude_m) if max_altitude_m else None
        self.timeout = timeout
        self._routes = {}  # callsign -> (timestamp, route dict or None)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ fetch
    def fetch_raw(self) -> list:
        radius_nm = math.ceil((self.max_distance_km + 2.0) / NM_TO_KM)
        url = self.API_URL.format(lat=round(self.latitude, 2), lon=round(self.longitude, 2), radius=radius_nm)
        resp = requests.get(url, headers=self.HEADERS, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("ac", []) or []

    def get_nearby(self) -> list:
        """
        Returns the aircraft inside the radius, closest first, as normalized dicts.
        Raises on network errors so the caller can keep its previous list.
        """
        flights = [f for f in (self.normalize(a) for a in self.fetch_raw()) if f]
        flights.sort(key=lambda f: f["distance_km"])
        for f in flights:
            if f["is_airline"]:
                f["route"] = self.get_route(f["callsign"])
        return flights

    def normalize(self, ac: dict):
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            return None
        alt = ac.get("alt_baro")
        on_ground = alt == "ground"
        if on_ground and not self.include_ground:
            return None
        alt_m = None
        if isinstance(alt, (int, float)):
            alt_m = alt * FT_TO_M
        elif isinstance(ac.get("alt_geom"), (int, float)):
            alt_m = ac["alt_geom"] * FT_TO_M
        if self.max_altitude_m and alt_m is not None and alt_m > self.max_altitude_m:
            return None

        distance = haversine_km(self.latitude, self.longitude, lat, lon)
        if distance > self.max_distance_km:
            return None

        callsign = (ac.get("flight") or "").strip().upper()
        registration = (ac.get("r") or "").strip().upper()
        type_code = (ac.get("t") or "").strip().upper()
        prefix = callsign[:3]
        is_airline = len(callsign) > 3 and prefix.isalpha() and callsign[3:].isdigit() \
            and callsign.replace("-", "") != registration.replace("-", "")
        category = (ac.get("category") or "").upper()
        is_heli = category == "A7" or type_code.startswith(("R22", "R44", "R66", "AS3", "AS5", "EC", "H1", "H2", "B06", "B407", "B429", "A109", "A119", "A139", "S76"))

        rate = ac.get("baro_rate", ac.get("geom_rate"))
        squawk = str(ac.get("squawk") or "")
        gs = ac.get("gs")
        track = ac.get("track", ac.get("true_heading"))
        return {
            "hex": (ac.get("hex") or "").lower(),
            "callsign": callsign,
            "registration": registration,
            "type": type_code,
            "airline": AIRLINES.get(prefix) if is_airline else None,
            "airline_code": prefix if is_airline else None,
            "flight_number": callsign[3:] if is_airline else None,
            "is_airline": is_airline,
            "is_heli": is_heli,
            "lat": lat,
            "lon": lon,
            "distance_km": distance,
            "bearing": bearing_deg(self.latitude, self.longitude, lat, lon),
            "altitude_m": alt_m,
            "on_ground": on_ground,
            "speed_kmh": gs * KNOT_TO_KMH if isinstance(gs, (int, float)) else None,
            "track": track if isinstance(track, (int, float)) else None,
            "vertical_rate": rate if isinstance(rate, (int, float)) else None,  # ft/min
            "emergency": squawk in ("7500", "7600", "7700") or (ac.get("emergency") not in (None, "", "none")),
            "squawk": squawk,
            "route": None,
        }

    # ------------------------------------------------------------------ routes
    def get_route(self, callsign: str):
        """Origin/destination for an airline callsign, e.g. {"origin": "GRU", "destination": "POA"}."""
        if not callsign:
            return None
        now = time.time()
        with self._lock:
            cached = self._routes.get(callsign)
            if cached and now - cached[0] < self.ROUTE_CACHE_SECONDS:
                return cached[1]
        route = None
        try:
            resp = requests.get(self.ROUTE_URL.format(callsign=callsign), headers=self.HEADERS, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json().get("response")
                fr = data.get("flightroute") if isinstance(data, dict) else None
                if fr:
                    def code(ap):
                        return (ap or {}).get("iata_code") or (ap or {}).get("icao_code") or ""
                    route = {
                        "origin": code(fr.get("origin")),
                        "destination": code(fr.get("destination")),
                        "airline_name": (fr.get("airline") or {}).get("name"),
                    }
        except Exception as e:
            logging.warning(f"FlightService: Route lookup failed for {callsign}: {e}")
            return None  # network error: don't cache, try again next poll
        with self._lock:
            self._routes[callsign] = (now, route)
            if len(self._routes) > 500:
                for k, _ in sorted(self._routes.items(), key=lambda kv: kv[1][0])[:250]:
                    self._routes.pop(k, None)
        return route


class FlightRotation:
    """
    Decides what the flight button shows: each flight in the radius gets `pages` screens of
    `rotate_seconds` each, flights alternate, and a flight leaves the rotation after
    `max_display_seconds` from when it was first seen (it comes back if it leaves and re-enters).
    max_display_seconds <= 0 means no limit: a flight is shown for as long as it is inside the radius.
    It also keeps each flight's recent positions, attached to the flight as "trail": a list of
    (distance_km, bearing) from home, oldest first, without the current position.
    """
    TRAIL_SECONDS = 300
    TRAIL_POINTS = 30

    def __init__(self, rotate_seconds: float = 5.0, max_display_seconds: float = 0.0, pages: int = 2):
        self.rotate_seconds = max(1.0, float(rotate_seconds))
        self.max_display_seconds = float(max_display_seconds)
        self.pages = pages
        self.flights = {}      # hex -> latest flight dict
        self.first_seen = {}   # hex -> timestamp
        self._order = []       # hex list in rotation order
        self._pos = 0          # index into the (flight, page) sequence
        self._last_step = 0.0
        self.trails = {}       # hex -> [(timestamp, distance_km, bearing), ...]

    def update(self, flights: list, now: float = None):
        now = time.time() if now is None else now
        current = {f["hex"] or f["callsign"]: f for f in flights}
        for key in list(self.first_seen):
            if key not in current:
                self.first_seen.pop(key, None)  # left the radius: forget, so a re-entry is shown again
                self.trails.pop(key, None)
        for key, f in current.items():
            self.first_seen.setdefault(key, now)
            trail = [p for p in self.trails.get(key, []) if now - p[0] <= self.TRAIL_SECONDS]
            f["trail"] = [(d, b) for _, d, b in trail]
            if not trail or (trail[-1][1], trail[-1][2]) != (f["distance_km"], f["bearing"]):
                trail.append((now, f["distance_km"], f["bearing"]))
            self.trails[key] = trail[-self.TRAIL_POINTS:]
        self.flights = current

    def active(self, now: float = None) -> list:
        now = time.time() if now is None else now
        keys = [k for k in self.flights
                if self.max_display_seconds <= 0 or now - self.first_seen.get(k, now) < self.max_display_seconds]
        return sorted(keys, key=lambda k: self.flights[k]["distance_km"])

    def current(self, now: float = None):
        """Returns (flight, page, index, total) or None when nothing should be shown."""
        now = time.time() if now is None else now
        keys = self.active(now)
        if not keys:
            self._order, self._pos = [], 0
            return None
        # keep the order stable for flights already rotating; new ones go to the end
        self._order = [k for k in self._order if k in keys] + [k for k in keys if k not in self._order]
        if now - self._last_step >= self.rotate_seconds:
            if self._last_step:
                self._pos += 1
            self._last_step = now
        total = len(self._order)
        self._pos %= total * self.pages
        idx, page = divmod(self._pos, self.pages)
        return self.flights[self._order[idx]], page, idx, total

    def hidden_count(self, now: float = None) -> int:
        """Aircraft still in the radius but past their display time."""
        return len(self.flights) - len(self.active(now))
