"""Current weather for the desk screen, from Open-Meteo (free weather API, no key, not an AI model).

Set QUIETDESK_CITY (e.g. Guwahati) or QUIETDESK_LAT / QUIETDESK_LON in .env. Without them, no weather.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

REFRESH_SECONDS = 15 * 60
_current = None  # {"temp": 27, "code": 3, "day": True}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def _place():
    lat, lon = os.getenv("QUIETDESK_LAT"), os.getenv("QUIETDESK_LON")
    if lat and lon:
        return float(lat), float(lon)
    city = os.getenv("QUIETDESK_CITY", "").strip()
    if not city:
        return None
    q = urllib.parse.urlencode({"name": city, "count": 1})
    hits = _get(f"https://geocoding-api.open-meteo.com/v1/search?{q}").get("results") or []
    return (hits[0]["latitude"], hits[0]["longitude"]) if hits else None


def _loop():
    global _current
    place = None
    while True:
        try:
            place = place or _place()
            if place is None:
                return  # no city set: the screen simply shows no weather
            q = urllib.parse.urlencode({"latitude": place[0], "longitude": place[1],
                                        "current": "temperature_2m,weather_code,is_day"})
            c = _get(f"https://api.open-meteo.com/v1/forecast?{q}")["current"]
            _current = {"temp": round(c["temperature_2m"]), "code": int(c["weather_code"]), "day": bool(c["is_day"])}
        except Exception as e:  # e.g. Wi-Fi not up yet right after boot: try again in a minute
            print(f"  weather: {e}")
            time.sleep(60)
            continue
        time.sleep(REFRESH_SECONDS)


def start() -> None:
    threading.Thread(target=_loop, daemon=True, name="weather").start()


def current():
    return _current
