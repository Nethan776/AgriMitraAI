import httpx
import os

# ─────────────────────────────────────────────
# OpenWeatherMap API
# Free tier: 1,000 calls/day — plenty for MVP
#
# Setup (2 minutes):
# 1. Go to https://openweathermap.org/api
# 2. Sign up free → API Keys → copy key
# 3. Add to Render env: OPENWEATHER_API_KEY=your_key
#
# Endpoints used:
#   Current weather: api.openweathermap.org/data/2.5/weather
#   5-day forecast:  api.openweathermap.org/data/2.5/forecast
# ─────────────────────────────────────────────

OWM_KEY          = os.getenv("OPENWEATHER_API_KEY", "")
OWM_CURRENT_URL  = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# ─────────────────────────────────────────────
# Pre-cached coordinates — avoids geocoding
# call on every message for your key talukas
# ─────────────────────────────────────────────

KNOWN_LOCATIONS = {
    "bharuch":    (21.7051, 72.9959),
    "hansot":     (21.5833, 72.8167),
    "ankleshwar": (21.6266, 72.9986),
    "amod":       (22.0167, 72.8667),
    "jambusar":   (22.0561, 72.8022),
    "vagra":      (21.4833, 72.9667),
    "jhagadia":   (21.5833, 73.0833),
    "valia":      (21.3833, 73.0833),
    "surat":      (21.1702, 72.8311),
    "vadodara":   (22.3072, 73.1812),
    "ahmedabad":  (23.0225, 72.5714),
    "navsari":    (20.9467, 72.9520),
    "narmada":    (21.8722, 73.4882),
    "rajkot":     (22.3039, 70.8022),
    "bharuch":    (21.7051, 72.9959),
}

# OWM weather condition IDs → Gujarati
def _condition_gujarati(weather_id: int, description: str) -> str:
    if 200 <= weather_id < 300:
        return "⛈️ ગર્જનાવાળો વરસાદ"
    elif 300 <= weather_id < 400:
        return "🌦️ ઝરમર વરસાદ"
    elif 500 <= weather_id < 600:
        if weather_id == 500:
            return "🌧️ હળવો વરસાદ"
        elif weather_id == 501:
            return "🌧️ મધ્યમ વરસાદ"
        elif weather_id >= 502:
            return "🌧️ ભારે વરસાદ"
        return "🌧️ વરસાદ"
    elif 600 <= weather_id < 700:
        return "❄️ હિમ"
    elif 700 <= weather_id < 800:
        if weather_id == 741:
            return "🌫️ ધુમ્મસ"
        elif weather_id == 721:
            return "🌫️ ઝાકળ"
        return "🌫️ અસ્પષ્ટ"
    elif weather_id == 800:
        return "☀️ સ્વચ્છ આકાશ"
    elif weather_id == 801:
        return "🌤️ થોડા વાદળ"
    elif weather_id == 802:
        return "⛅ અડધો વાદળ"
    elif weather_id in (803, 804):
        return "☁️ વાદળ છે"
    return "🌤️ " + description


async def _get_coords(taluka: str) -> tuple[float, float] | None:
    """Get coordinates — from cache first, then OWM geocoding."""
    key = taluka.strip().lower()

    # Check known locations
    if key in KNOWN_LOCATIONS:
        return KNOWN_LOCATIONS[key]

    # Try OWM geocoding for unknown talukas
    if not OWM_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://api.openweathermap.org/geo/1.0/direct",
                params={"q": f"{taluka},Gujarat,IN", "limit": 1, "appid": OWM_KEY}
            )
        results = r.json()
        if results:
            return results[0]["lat"], results[0]["lon"]
    except Exception as e:
        print(f"⚠️  OWM geocoding error: {e}")
    return None


async def fetch_weather(taluka: str) -> dict | None:
    """
    Fetch current weather + 3-day forecast from OpenWeatherMap.
    Returns structured dict or None on failure.
    """
    if not OWM_KEY:
        print("⚠️  OPENWEATHER_API_KEY not set")
        return None

    coords = await _get_coords(taluka)
    if not coords:
        print(f"⚠️  Could not get coords for '{taluka}'")
        return None

    lat, lon = coords

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Fetch current weather and forecast in parallel
            current_r, forecast_r = await asyncio.gather(
                client.get(OWM_CURRENT_URL, params={
                    "lat": lat, "lon": lon,
                    "appid": OWM_KEY,
                    "units": "metric",
                    "lang": "en"
                }),
                client.get(OWM_FORECAST_URL, params={
                    "lat": lat, "lon": lon,
                    "appid": OWM_KEY,
                    "units": "metric",
                    "cnt": 24,          # 24 x 3hr slots = 3 days
                    "lang": "en"
                })
            )

        if current_r.status_code != 200:
            print(f"⚠️  OWM current weather error: {current_r.status_code} {current_r.text[:100]}")
            return None

        cur  = current_r.json()
        fore = forecast_r.json() if forecast_r.status_code == 200 else {}

        # Current conditions
        weather_id  = cur["weather"][0]["id"]
        description = cur["weather"][0]["description"]
        temp        = round(cur["main"]["temp"])
        feels_like  = round(cur["main"]["feels_like"])
        humidity    = cur["main"]["humidity"]
        wind        = round(cur["wind"]["speed"] * 3.6)   # m/s → km/h
        rain_now    = cur.get("rain", {}).get("1h", 0)
        condition   = _condition_gujarati(weather_id, description)

        # Build daily forecast from 3-hour slots
        # Group by date, take max temp, min temp, sum rain, most common condition
        from collections import defaultdict
        daily = defaultdict(lambda: {"temps": [], "rain": 0, "conditions": []})

        for slot in fore.get("list", []):
            date = slot["dt_txt"].split(" ")[0]
            daily[date]["temps"].append(slot["main"]["temp"])
            daily[date]["rain"] += slot.get("rain", {}).get("3h", 0)
            daily[date]["conditions"].append(slot["weather"][0]["id"])

        forecast = []
        for date, d in sorted(daily.items())[:3]:
            most_common_id = max(set(d["conditions"]), key=d["conditions"].count)
            forecast.append({
                "date":      date,
                "max_temp":  round(max(d["temps"])),
                "min_temp":  round(min(d["temps"])),
                "rain_mm":   round(d["rain"], 1),
                "condition": _condition_gujarati(most_common_id, ""),
            })

        return {
            "taluka":     taluka,
            "condition":  condition,
            "temp":       temp,
            "feels_like": feels_like,
            "humidity":   humidity,
            "wind":       wind,
            "rain_now":   rain_now,
            "forecast":   forecast,
        }

    except Exception as e:
        print(f"⚠️  Weather fetch error: {e}")
        return None


# ─────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────

def format_weather_for_prompt(weather: dict) -> str:
    """Compact block injected into AI system prompt."""
    if not weather:
        return ""

    alerts = []
    if weather["humidity"] > 80:
        alerts.append("ભેજ વધારે — ફૂગ/રોગનો ખતરો")
    if weather["humidity"] < 25:
        alerts.append("ભેજ ઓછો — સૂકવણીનો ખતરો")
    if weather["temp"] > 42:
        alerts.append("ભારે ગરમી — સવાર/સાંજ સિંચાઈ")
    if weather["temp"] < 10:
        alerts.append("ઠંડી — નાના પાકને નુકસાન")
    if weather["rain_now"] > 5:
        alerts.append("વરસાદ — દવા છંટકાવ ટાળો")
    if weather["wind"] > 35:
        alerts.append("તેજ પવન — છંટકાવ ટાળો")

    forecast_lines = "\n".join(
        f"  {f['date']}: {f['condition']}, {f['min_temp']}–{f['max_temp']}°C, વરસાદ {f['rain_mm']}mm"
        for f in weather["forecast"]
    )

    alert_text = " | ".join(alerts) if alerts else "સામાન્ય"

    return f"""
━━━ હવામાન — {weather['taluka']} ━━━
{weather['condition']} | {weather['temp']}°C (feels {weather['feels_like']}°C)
ભેજ: {weather['humidity']}% | પવન: {weather['wind']} km/h | વરસાદ: {weather['rain_now']}mm
ખેતી ચેતવણી: {alert_text}
આગામી 3 દિવસ:
{forecast_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def format_weather_for_farmer(weather: dict) -> str:
    """Full Gujarati weather card for direct weather queries."""
    if not weather:
        return (
            "😔 હાલ હવામાનની માહિતી ઉપલબ્ધ નથી.\n"
            "કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો."
        )

    lines = [f"🌤️ *{weather['taluka']} — આજનું હવામાન*\n"]
    lines.append(f"{weather['condition']}")
    lines.append(f"🌡️ તાપમાન: *{weather['temp']}°C* (feels like {weather['feels_like']}°C)")
    lines.append(f"💧 ભેજ: *{weather['humidity']}%*")
    lines.append(f"🌬️ પવન: *{weather['wind']} km/h*")
    if weather["rain_now"] > 0:
        lines.append(f"🌧️ વરસાદ: *{weather['rain_now']}mm*")

    lines.append("\n📅 *આગામી 3 દિવસ:*")
    for f in weather["forecast"]:
        rain_text = f" | 🌧️ {f['rain_mm']}mm" if f["rain_mm"] > 0 else ""
        lines.append(f"  {f['date']}: {f['condition']}, {f['min_temp']}–{f['max_temp']}°C{rain_text}")

    # Farming tip
    lines.append("\n💡 *ખેતી સલાહ:*")
    if weather["rain_now"] > 5:
        lines.append("  વરસાદ છે — દવા છંટકાવ ટાળો.")
    elif weather["humidity"] > 80:
        lines.append("  ભેજ વધારે — ફૂગના રોગ માટે સતર્ક રહો.")
    elif weather["temp"] > 42:
        lines.append("  ભારે ગરમી — સવારે/સાંજે સિંચાઈ કરો.")
    elif weather["wind"] > 35:
        lines.append("  તેજ પવન — આજે છંટકાવ ટાળો.")
    else:
        lines.append("  હવામાન સામાન્ય — ખેતી માટે સારો દિવસ.")

    lines.append("\n_સ્ત્રોત: OpenWeatherMap_")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Weather query detection
# ─────────────────────────────────────────────

WEATHER_TRIGGERS = [
    "હવામાન", "weather", "વરસાદ", "rain", "ઠંડી", "ગરમી",
    "temperature", "તાપમાન", "વાદળ", "cloud", "ધુમ્મસ", "fog",
    "પવન", "wind", "humidity", "ભેજ", "આગાહી", "forecast",
    "આજ કેવ", "વાતાવ", "છંટકાવ કરવ"
]


def is_weather_query(text: str) -> bool:
    return any(w in text.lower() for w in WEATHER_TRIGGERS)


# asyncio needed for parallel fetch
import asyncio