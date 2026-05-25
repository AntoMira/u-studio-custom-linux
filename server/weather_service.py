import os
import logging
import time
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class WeatherService:
    """
    Service to fetch weather data from OpenWeather API, with caching and fallback mock values.
    """
    def __init__(self, api_key: str, city: str):
        self.api_key = api_key.strip() if api_key else ""
        self.city = city.strip() if city else "Sao Paulo,BR"
        self._cache = None
        self._cache_time = 0
        self._cache_duration = 3600  # 1 hour cache lifetime

    def is_mock_mode(self) -> bool:
        """
        Returns True if the OpenWeather API Key is unset or is using the default template value.
        """
        return not self.api_key or self.api_key == "your_openweather_api_key" or self.api_key.startswith("your_")

    def clear_cache(self):
        """
        Force invalidates the current weather cache.
        """
        logging.info("WeatherService: Cache cleared manually.")
        self._cache_time = 0

    def get_weather_type_and_priority(self, weather_id: int) -> tuple:
        """
        Maps OpenWeather weather IDs to a simpler set of categories and prioritizes severe events
        so that a day with rain/thunderstorms is correctly represented.
        Priority: Thunderstorm (5) > Rain (4) > Snow (3) > Mist (2) > Clouds (1) > Clear (0).
        """
        if 200 <= weather_id < 300:
            return "thunderstorm", 5
        elif 300 <= weather_id < 600:
            return "rain", 4
        elif 600 <= weather_id < 700:
            return "snow", 3
        elif 700 <= weather_id < 800:
            return "mist", 2
        elif weather_id == 800:
            return "clear", 0
        elif 801 <= weather_id < 900:
            return "clouds", 1
        return "clear", 0

    def get_weather_data(self) -> dict:
        """
        Returns parsed weather data for today ('weather') and tomorrow ('weather+1').
        Uses cache if valid, otherwise queries the real API or falls back to simulated/mock data.
        """
        now = time.time()
        # Use cache if valid
        if self._cache and (now - self._cache_time < self._cache_duration):
            return self._cache

        # If key is missing/placeholder, yield premium mock data
        if self.is_mock_mode():
            logging.info("WeatherService: Operating in MOCK mode (No valid API key). Returning premium mock forecast.")
            self._cache = {
                "weather": { "min_temp": 18.0, "max_temp": 26.0, "type": "clear" },
                "weather+1": { "min_temp": 16.0, "max_temp": 22.0, "type": "rain" }
            }
            self._cache_time = now
            return self._cache

        # Query the OpenWeather 5 Day / 3 Hour Forecast API
        try:
            logging.info(f"WeatherService: Fetching fresh forecast for city: {self.city}")
            url = "https://api.openweathermap.org/data/2.5/forecast"
            params = {
                "q": self.city,
                "appid": self.api_key,
                "units": "metric"
            }
            response = requests.get(url, params=params, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                self._cache = self._parse_forecast_data(data)
                self._cache_time = now
                logging.info("WeatherService: Successfully updated weather cache from OpenWeather API.")
                return self._cache
            else:
                logging.error(f"WeatherService: OpenWeather API returned status code {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"WeatherService: Network or parsing exception during API fetch: {e}")

        # Fallback to expired cache if available during error, otherwise fall back to mock data
        if self._cache:
            logging.warning("WeatherService: Returning expired cache as fallback due to API failure.")
            return self._cache

        logging.warning("WeatherService: Returning simulated mock forecast due to API failure.")
        return {
            "weather": { "min_temp": 18.0, "max_temp": 26.0, "type": "clear" },
            "weather+1": { "min_temp": 16.0, "max_temp": 22.0, "type": "rain" }
        }

    def _parse_forecast_data(self, data: dict) -> dict:
        """
        Groups the 3-hour forecasts by logical calendar dates, extracts the daily temperature min/max,
        and determines the most significant weather condition for today and tomorrow.
        """
        today_date = datetime.now().date()
        tomorrow_date = today_date + timedelta(days=1)
        
        # Group items by their local date
        days_data = {}
        for item in data.get("list", []):
            dt = item.get("dt")
            if not dt:
                continue
            item_date = datetime.fromtimestamp(dt).date()
            if item_date not in days_data:
                days_data[item_date] = []
            days_data[item_date].append(item)

        # Fallback in case today's timezone boundary results in empty arrays
        sorted_dates = sorted(days_data.keys())
        today_records = days_data.get(today_date, [])
        tomorrow_records = days_data.get(tomorrow_date, [])

        if not today_records and len(sorted_dates) > 0:
            today_date = sorted_dates[0]
            today_records = days_data[today_date]
        if not tomorrow_records and len(sorted_dates) > 1:
            tomorrow_date = sorted_dates[1]
            tomorrow_records = days_data[tomorrow_date]

        parsed = {}
        
        # Parse today's weather
        if today_records:
            parsed["weather"] = self._aggregate_day_records(today_records)
        else:
            parsed["weather"] = { "min_temp": 18.0, "max_temp": 26.0, "type": "clear" }

        # Parse tomorrow's weather
        if tomorrow_records:
            parsed["weather+1"] = self._aggregate_day_records(tomorrow_records)
        else:
            parsed["weather+1"] = { "min_temp": 16.0, "max_temp": 22.0, "type": "rain" }

        return parsed

    def _aggregate_day_records(self, records: list) -> dict:
        """
        Aggregates temperatures and resolves the predominant weather category based on priority.
        """
        temps_min = []
        temps_max = []
        best_type = "clear"
        max_priority = -1

        for item in records:
            main = item.get("main", {})
            if "temp_min" in main:
                temps_min.append(main["temp_min"])
            if "temp_max" in main:
                temps_max.append(main["temp_max"])

            w_list = item.get("weather", [])
            if w_list:
                w_id = w_list[0].get("id", 800)
                w_type, priority = self.get_weather_type_and_priority(w_id)
                if priority > max_priority:
                    max_priority = priority
                    best_type = w_type

        min_temp = min(temps_min) if temps_min else 18.0
        max_temp = max(temps_max) if temps_max else 26.0

        return {
            "min_temp": min_temp,
            "max_temp": max_temp,
            "type": best_type
        }
