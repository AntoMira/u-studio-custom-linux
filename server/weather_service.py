import math
import os
import logging
import time
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class WeatherService:
    """
    Service to fetch weather data from the free Open-Meteo API (no API key needed),
    with caching and fallback mock values.
    """
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    HOURLY_STEP = 3  # hours per entry in the "hourly" series (one bar per 3 h on the weather graph)

    def __init__(self, city: str = "", timezone=None, latitude=None, longitude=None, mock: bool = False):
        self.timezone = timezone  # tzinfo used to group forecasts by local date (None = system timezone)
        self.city = city.strip() if city else "Sao Paulo,BR"
        self.latitude = self._to_float(latitude)
        self.longitude = self._to_float(longitude)
        self.mock = mock
        self._cache = None
        self._cache_time = 0
        self._cache_duration = 3600  # 1 hour cache lifetime

    @staticmethod
    def _to_float(value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def is_mock_mode(self) -> bool:
        """
        Returns True when the service was explicitly created in mock mode (tests / offline use).
        """
        return self.mock

    def clear_cache(self):
        """
        Force invalidates the current weather cache.
        """
        logging.info("WeatherService: Cache cleared manually.")
        self._cache_time = 0

    def get_weather_type_and_priority(self, code: int) -> tuple:
        """
        Maps WMO weather codes (used by Open-Meteo) to a simpler set of categories and prioritizes
        severe events so that a day with rain/thunderstorms is correctly represented.
        Priority: Thunderstorm (5) > Rain (4) > Snow (3) > Mist (2) > Clouds (1) > Clear (0).
        """
        if code is None:
            return "clear", 0
        code = int(code)
        if code >= 95:
            return "thunderstorm", 5
        if 51 <= code <= 67 or 80 <= code <= 82:
            return "rain", 4
        if 71 <= code <= 77 or 85 <= code <= 86:
            return "snow", 3
        if code in (45, 48):
            return "mist", 2
        if code in (2, 3):
            return "clouds", 1
        return "clear", 0  # 0 = clear sky, 1 = mainly clear

    def display_type(self, current: dict, now=None) -> str:
        """
        Weather type to draw for the current conditions: a clear sky after sunset (or before
        sunrise) becomes "clear_night" so the widgets show a moon instead of a sun.
        """
        w_type = current.get("type", "clear")
        if w_type != "clear":
            return w_type
        now = now or datetime.now(self.timezone)
        # Sunrise/sunset come from the API as unix timestamps; compare only the local time of day
        # so a cached value from a previous day still works. Mock mode falls back to 06:00-18:00.
        def tod(ts, default):
            if not ts:
                return default
            t = datetime.fromtimestamp(ts, self.timezone)
            return t.hour * 3600 + t.minute * 60 + t.second
        sunrise = tod(current.get("sunrise"), 6 * 3600)
        sunset = tod(current.get("sunset"), 18 * 3600)
        now_s = now.hour * 3600 + now.minute * 60 + now.second
        return "clear" if sunrise <= now_s < sunset else "clear_night"

    def _resolve_location(self):
        """
        Returns (latitude, longitude). Uses the configured coordinates, otherwise looks the city up
        once with the Open-Meteo geocoding API ("Name" or "Name,CC" where CC is the ISO country code).
        """
        if self.latitude is not None and self.longitude is not None:
            return self.latitude, self.longitude
        name, _, country = self.city.partition(",")
        params = {"name": name.strip(), "count": 1, "format": "json"}
        if country.strip():
            params["countryCode"] = country.strip().upper()
        response = requests.get(self.GEOCODING_URL, params=params, timeout=15)
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise ValueError(f"city '{self.city}' not found by the Open-Meteo geocoding API")
        self.latitude, self.longitude = results[0]["latitude"], results[0]["longitude"]
        logging.info(f"WeatherService: Resolved '{self.city}' to {self.latitude:.4f}, {self.longitude:.4f}")
        return self.latitude, self.longitude

    def _timezone_param(self) -> str:
        # Open-Meteo groups daily values by this timezone; "auto" = the location's own timezone
        return getattr(self.timezone, "key", None) or "auto"

    def get_weather_data(self) -> dict:
        """
        Returns parsed weather data for today ('weather') and tomorrow ('weather+1').
        Uses cache if valid, otherwise queries the real API or falls back to simulated/mock data.
        """
        now = time.time()
        # Use cache if valid
        if self._cache and (now - self._cache_time < self._cache_duration):
            return self._cache

        if self.is_mock_mode():
            logging.info("WeatherService: Operating in MOCK mode. Returning premium mock forecast.")
            self._cache = self._mock_data()
            self._cache_time = now
            return self._cache

        try:
            lat, lon = self._resolve_location()
            logging.info(f"WeatherService: Fetching fresh forecast from Open-Meteo for {lat:.2f}, {lon:.2f}")
            params = {
                # Rounded to ~1 km (like the flight radar): finer than the forecast grid, so no loss
                "latitude": round(lat, 2),
                "longitude": round(lon, 2),
                "current": "temperature_2m,weather_code",
                "hourly": "temperature_2m,precipitation,precipitation_probability",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,sunrise,sunset",
                "timezone": self._timezone_param(),
                "timeformat": "unixtime",
                "forecast_days": 6,
            }
            response = requests.get(self.FORECAST_URL, params=params, timeout=15)
            if response.status_code == 200:
                self._cache = self._parse_forecast_data(response.json())
                self._cache_time = now
                logging.info("WeatherService: Successfully updated weather cache from Open-Meteo.")
                return self._cache
            logging.error(f"WeatherService: Open-Meteo returned status code {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"WeatherService: Network or parsing exception during API fetch: {e}")

        # Fallback to expired cache if available during error, otherwise fall back to mock data
        if self._cache:
            logging.warning("WeatherService: Returning expired cache as fallback due to API failure.")
            return self._cache

        logging.warning("WeatherService: Returning simulated mock forecast due to API failure.")
        return self._mock_data()

    def _mock_data(self) -> dict:
        today = datetime.now(self.timezone).date()
        mock_days = [
            (18.0, 26.0, "clear", 0.05), (16.0, 22.0, "rain", 0.8), (15.0, 21.0, "clouds", 0.2),
            (14.0, 24.0, "clear", 0.0), (17.0, 29.0, "thunderstorm", 0.6),
        ]
        return {
            "weather": { "temp": 20.5, "pop": 0.35, "type": "clouds" },
            "weather_forecast": { "min_temp": 18.0, "max_temp": 26.0, "type": "clear" },
            "weather_forecast+1": { "min_temp": 16.0, "max_temp": 22.0, "type": "rain" },
            "hourly": [
                { "date": (datetime.now(self.timezone) + timedelta(hours=3 * i)).date().isoformat(), "temp": 21 + 7 * math.sin((i - 3) * math.pi / 4), "rain": max(0.0, 12 * math.sin((i - 5) * math.pi / 8)) if i < 16 else 0.0 }
                for i in range(32)
            ],
            "daily": [
                { "date": (today + timedelta(days=i)).isoformat(), "min_temp": lo, "max_temp": hi, "type": t, "pop": pop }
                for i, (lo, hi, t, pop) in enumerate(mock_days)
            ],
        }

    def _parse_forecast_data(self, data: dict, now=None) -> dict:
        """
        Converts an Open-Meteo forecast (timeformat=unixtime) into the structure used by the widgets:
        current conditions, today's/tomorrow's summaries, 3-hour temperature/rain series and daily summaries.
        """
        now_ts = now if now is not None else time.time()
        hourly = data.get("hourly") or {}
        h_time = hourly.get("time") or []
        h_temp = hourly.get("temperature_2m") or []
        h_rain = hourly.get("precipitation") or []
        h_pop = hourly.get("precipitation_probability") or []

        def at(series, i, default=0.0):
            v = series[i] if i < len(series) else None
            return default if v is None else v

        # First hourly entry of the current hour (falls back to the start of the series)
        first = next((i for i, t in enumerate(h_time) if t + 3600 > now_ts), 0)

        # Daily summaries, today first
        daily = data.get("daily") or {}
        days = []
        for i, t in enumerate(daily.get("time") or []):
            w_type, _ = self.get_weather_type_and_priority(at(daily.get("weather_code") or [], i, 0))
            days.append({
                "date": datetime.fromtimestamp(t, self.timezone).date().isoformat(),
                "min_temp": at(daily.get("temperature_2m_min") or [], i, 18.0),
                "max_temp": at(daily.get("temperature_2m_max") or [], i, 26.0),
                "type": w_type,
                "pop": at(daily.get("precipitation_probability_max") or [], i, 0.0) / 100.0,
                "sunrise": at(daily.get("sunrise") or [], i, None),
                "sunset": at(daily.get("sunset") or [], i, None),
            })
        today_iso = datetime.fromtimestamp(now_ts, self.timezone).date().isoformat()
        while len(days) > 1 and days[0]["date"] < today_iso:
            days.pop(0)

        def summary(day, default):
            return {k: day[k] for k in ("min_temp", "max_temp", "type", "pop")} if day else default

        current = data.get("current") or {}
        current_type, _ = self.get_weather_type_and_priority(current.get("weather_code", 0))
        # Rain chance for the next 3 hours (what the 3-hour forecast used to report)
        next_pops = [at(h_pop, i) for i in range(first, min(first + self.HOURLY_STEP, len(h_time)))]
        parsed = {
            "weather": {
                "temp": current.get("temperature_2m", at(h_temp, first, 18.0)),
                "pop": (max(next_pops) if next_pops else 0.0) / 100.0,
                "type": current_type,
                "sunrise": days[0]["sunrise"] if days else None,
                "sunset": days[0]["sunset"] if days else None,
            },
            "weather_forecast": summary(days[0] if days else None, {"min_temp": 18.0, "max_temp": 26.0, "type": "clear"}),
            "weather_forecast+1": summary(days[1] if len(days) > 1 else None, {"min_temp": 16.0, "max_temp": 22.0, "type": "rain"}),
        }

        # 3-hour temperature and rain (mm summed over the 3 hours) series for the weather graph
        parsed["hourly"] = []
        for i in range(first, len(h_time) - self.HOURLY_STEP + 1, self.HOURLY_STEP):
            parsed["hourly"].append({
                "date": datetime.fromtimestamp(h_time[i], self.timezone).date().isoformat(),
                "temp": at(h_temp, i),
                "rain": round(sum(at(h_rain, j) for j in range(i, i + self.HOURLY_STEP)), 2),
            })

        parsed["daily"] = [dict(summary(d, None), date=d["date"]) for d in days[:5]]
        return parsed
