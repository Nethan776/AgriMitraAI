import httpx
import os

# ─────────────────────────────────────────────
# indianapi.in — IMD (India Meteorological Dept)
# Same source as Google Weather for India
#
# Get free key (1000 req): https://indianapi.in/weather-api
# Add to Render env: INDIANAPI_KEY=your_key
#
# Endpoints used:
#   /india/weather?city=Bharuch   ← IMD data, India only
#   /global/weather?location=...  ← fallback for unknown cities
# ─────────────────────────────────────────────

INDIANAPI_KEY  = os.getenv("INDIANAPI_KEY", "")
INDIANAPI_BASE = "https://weather.indianapi.in"

# ─────────────────────────────────────────────
# Your target talukas mapped to IMD city names
# Use exact city names that IMD recognises
# ─────────────────────────────────────────────

KNOWN_CITIES = {
    "bharuch":    "Bharuch",
    "hansot":     "Bharuch",      # Hansot is too small for IMD — use Bharuch
    "ankleshwar": "Ankleshwar",
    "amod":       "Bharuch",
    "jambusar":   "Bharuch",
    "vagra":      "Bharuch",
    "jhagadia":   "Bharuch",
    "valia":      "Bharuch",
    "surat":      "Surat",
    "vadodara":   "Vadodara",
    "ahmedabad":  "Ahmedabad",
    "navsari":    "Navsari",
    "rajkot":     "Rajkot",
    "narmada":    "Bharuch",
}

# Forecast description → Gujarati
def _condition_gujarati(description: str) -> str:
    if not description:
        return "🌤️ સામાન્ય"
    d = description.lower()
    if "thunder" in d or "thunderstorm" in d:
        return "⛈️ ગર્જનાવાળો વરસાદ"
    elif "heavy rain" in d or "heavy rainfall" in d:
        return "🌧️ ભારે વરસાદ"
    elif "moderate rain" in d:
        return "🌧️ મધ્યમ વરસાદ"
    elif "light rain" in d or "drizzle" in d:
        return "🌦️ હળવો વરસાદ"
    elif "rain" in d or "rainfall" in d or "shower" in d:
        return "🌧️ વરસાદ"
    elif "snow" in d or "hail" in d:
        return "❄️ હિમ/કરા"
    elif "fog" in d or "mist" in d:
        return "🌫️ ધુમ્મસ"
    elif "overcast" in d or "cloudy" in d:
        return "☁️ વાદળ"
    elif "partly cloudy" in d or "partly" in d:
        return "🌤️ અડધો વાદળ"
    elif "clear" in d or "sunny" in d or "fair" in d:
        return "☀️ સ્વચ્છ/તડકો"
    elif "dust" in d or "haze" in d or "smoke" in d:
        return "🌫️ ધૂળ/ઝાકળ"
    elif "wind" in d or "squall" in d:
        return "🌬️ પવન"
    return "🌤️ " + description[:30]


async def fetch_weather(taluka: str) -> dict | None:
    """
    Fetch IMD weather data for a taluka via indianapi.in.
    Falls back to /global/weather if IMD city not found.
    """
    if not INDIANAPI_KEY:
        print("⚠️  INDIANAPI_KEY not set in Render environment variables")
        return None

    key_lower  = taluka.strip().lower()
    city_query = KNOWN_CITIES.get(key_lower, taluka.strip())

    headers = {"x-api-key": INDIANAPI_KEY}

    try:
        async with httpx.AsyncClient(timeout=12) as client:

            # ── Try IMD endpoint first ──────────────────────────
            r = await client.get(
                f"{INDIANAPI_BASE}/india/weather",
                params={"city": city_query},
                headers=headers
            )
            print(f"🌤️  indianapi /india/weather [{city_query}]: {r.status_code}")

            if r.status_code == 200:
                data = r.json()
                return _parse_india_response(data, taluka)

            # ── Fallback to global endpoint ─────────────────────
            print(f"⚠️  IMD endpoint failed ({r.status_code}) — trying global fallback")
            r2 = await client.get(
                f"{INDIANAPI_BASE}/global/weather",
                params={"location": f"{taluka},Gujarat,India", "days": 3},
                headers=headers
            )
            print(f"🌤️  indianapi /global/weather: {r2.status_code}")

            if r2.status_code == 200:
                return _parse_global_response(r2.json(), taluka)

            print(f"⚠️  Both endpoints failed. Last error: {r2.text[:150]}")
            return None

    except Exception as e:
        print(f"⚠️  Weather fetch exception: {e}")
        return None


def _parse_india_response(data: dict, taluka: str) -> dict | None:
    """Parse the /india/weather IMD response format."""
    try:
        city    = data.get("city", taluka)
        weather = data.get("weather", {})
        current = weather.get("current", {})

        temp_data = current.get("temperature", {})
        max_temp  = temp_data.get("max", {}).get("value")
        min_temp  = temp_data.get("min", {}).get("value")
        avg_temp  = round((max_temp + min_temp) / 2) if max_temp and min_temp else None

        humidity_data = current.get("humidity", {})
        humidity = humidity_data.get("morning") or humidity_data.get("evening") or 0

        rainfall = current.get("rainfall") or 0

        # Build forecast from IMD daily forecast
        raw_forecast = weather.get("forecast", [])
        forecast = []
        for day in raw_forecast[1:4]:   # Skip today (index 0), take next 3
            forecast.append({
                "date":        day.get("date", ""),
                "max_temp":    day.get("max_temp"),
                "min_temp":    day.get("min_temp"),
                "rain_mm":     0,       # IMD forecast has description not mm
                "rain_chance": 0,
                "condition":   _condition_gujarati(day.get("description", "")),
            })

        # Today's condition from forecast[0] description
        today_desc = raw_forecast[0].get("description", "") if raw_forecast else ""
        condition  = _condition_gujarati(today_desc)

        print(f"✅  IMD weather: {city} — max {max_temp}°C, min {min_temp}°C")

        return {
            "taluka":     taluka,
            "city":       city,
            "source":     "IMD",
            "condition":  condition,
            "temp":       avg_temp or max_temp,
            "temp_max":   max_temp,
            "temp_min":   min_temp,
            "feels_like": avg_temp,    # IMD doesn't provide feels_like
            "humidity":   humidity,
            "wind":       0,            # IMD current doesn't give wind speed
            "rain_now":   rainfall,
            "uv_index":   0,
            "forecast":   forecast,
        }

    except Exception as e:
        print(f"⚠️  IMD parse error: {e}")
        return None


def _parse_global_response(data: dict, taluka: str) -> dict | None:
    """Parse the /global/weather fallback response format."""
    try:
        current  = data.get("current", {})
        forecast = []

        for day in data.get("forecast", []):
            hourly   = day.get("hourly", [{}])
            rain_ch  = max((h.get("chance_of_rain", 0) for h in hourly), default=0)
            forecast.append({
                "date":        day.get("date", ""),
                "max_temp":    day.get("max_temp"),
                "min_temp":    day.get("min_temp"),
                "rain_mm":     0,
                "rain_chance": rain_ch,
                "condition":   _condition_gujarati(day.get("condition", "")),
            })

        # Skip today from forecast
        forecast = forecast[1:4]

        condition = _condition_gujarati(current.get("condition", ""))
        temp      = round(current.get("temperature", 0))

        print(f"✅  Global weather fallback: {taluka} — {temp}°C")

        return {
            "taluka":     taluka,
            "city":       data.get("location", taluka),
            "source":     "Global",
            "condition":  condition,
            "temp":       temp,
            "temp_max":   temp,
            "temp_min":   temp,
            "feels_like": round(current.get("feels_like", temp)),
            "humidity":   current.get("humidity", 0),
            "wind":       round(current.get("wind_speed", 0)),
            "rain_now":   0,
            "uv_index":   current.get("uv_index", 0),
            "forecast":   forecast,
        }

    except Exception as e:
        print(f"⚠️  Global parse error: {e}")
        return None


# ─────────────────────────────────────────────
# Format for AI system prompt
# ─────────────────────────────────────────────

def format_weather_for_prompt(weather: dict) -> str:
    if not weather:
        return ""

    alerts = []
    temp = weather.get("temp") or weather.get("temp_max") or 0
    if weather["humidity"] > 80:
        alerts.append("ભેજ વધારે — ફૂગ/રોગનો ખતરો")
    if weather["humidity"] < 25:
        alerts.append("ભેજ ઓછો — સૂકવણી")
    if temp > 42:
        alerts.append("ભારે ગરમી — સવાર/સાંજ સિંચાઈ")
    if temp < 10:
        alerts.append("ઠંડી — નાના પાકને જોખમ")
    if weather["rain_now"] > 5:
        alerts.append("વરસાદ — છંટકાવ ટાળો")
    if weather["wind"] > 35:
        alerts.append("તેજ પવન — છંટકાવ ટાળો")

    forecast_lines = "\n".join(
        f"  {f['date']}: {f['condition']}, {f['min_temp']}–{f['max_temp']}°C"
        for f in weather["forecast"]
    )

    temp_display = (
        f"{weather['temp_min']}–{weather['temp_max']}°C"
        if weather.get("temp_max") and weather.get("temp_min")
        else f"{temp}°C"
    )

    return f"""
━━━ હવામાન — {weather['taluka']} (IMD) ━━━
{weather['condition']} | {temp_display}
ભેજ: {weather['humidity']}% | વરસાદ: {weather['rain_now']}mm
ખેતી ચેતવણી: {' | '.join(alerts) if alerts else 'સામાન્ય'}
આગામી 3 દિવસ:
{forecast_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


# ─────────────────────────────────────────────
# Format for farmer direct weather query
# ─────────────────────────────────────────────

def format_weather_for_farmer(weather: dict) -> str:
    if not weather:
        return (
            "😔 હાલ હવામાનની માહિતી ઉપલબ્ધ નથી.\n"
            "કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો."
        )

    temp     = weather.get("temp") or weather.get("temp_max")
    temp_max = weather.get("temp_max")
    temp_min = weather.get("temp_min")
    source   = weather.get("source", "IMD")

    lines = [f"🌤️ *{weather['taluka']} — આજનું હવામાન* (સ્ત્રોત: {source})\n"]
    lines.append(weather["condition"])

    if temp_max and temp_min:
        lines.append(f"🌡️ તાપમાન: *{temp_min}°C – {temp_max}°C*")
    else:
        lines.append(f"🌡️ તાપમાન: *{temp}°C*")

    lines.append(f"💧 ભેજ: *{weather['humidity']}%*")

    if weather["wind"] > 0:
        lines.append(f"🌬️ પવન: *{weather['wind']} km/h*")
    if weather["rain_now"] > 0:
        lines.append(f"🌧️ વરસાદ: *{weather['rain_now']}mm*")

    if weather["forecast"]:
        lines.append("\n📅 *આગામી 3 દિવસ:*")
        for f in weather["forecast"]:
            lines.append(
                f"  {f['date']}: {f['condition']}, "
                f"{f['min_temp']}–{f['max_temp']}°C"
            )

    lines.append("\n💡 *ખેતી સલાહ:*")
    if weather["rain_now"] > 5:
        lines.append("  વરસાદ છે — આજે દવા છંટકાવ ટાળો.")
    elif weather["humidity"] > 80:
        lines.append("  ભેજ વધારે — ફૂગના રોગ સતર્ક રહો.")
    elif temp and temp > 42:
        lines.append("  ભારે ગરમી — સવારે/સાંજે સિંચાઈ કરો.")
    elif weather["wind"] > 35:
        lines.append("  તેજ પવન — આજે છંટકાવ ટાળો.")
    else:
        lines.append("  હવામાન સામાન્ય — ખેતી માટે સારો દિવસ. ✅")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Weather query detection
# ─────────────────────────────────────────────

WEATHER_TRIGGERS = [
    "હવામાન", "weather", "વરસાદ", "rain", "ઠંડી", "ગરમી",
    "temperature", "તાપમાન", "વાદળ", "cloud", "ધુમ્મસ",
    "પવન", "wind", "humidity", "ભેજ", "આગાહી", "forecast",
    "આજ કેવ", "વાતાવ", "uv", "તડકો",
]


def is_weather_query(text: str) -> bool:
    return any(w in text.lower() for w in WEATHER_TRIGGERS)