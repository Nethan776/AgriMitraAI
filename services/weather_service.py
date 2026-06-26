import httpx
import os

# ─────────────────────────────────────────────
# indianapi.in — IMD (India Meteorological Dept)
# Docs: https://indianapi.in/documentation/weather-api
# Base URL: https://weather.indianapi.in
# Auth: x-api-key header
#
# Add to Render env: INDIANAPI_KEY=your_key
# Get free key: https://indianapi.in/weather-api
# ─────────────────────────────────────────────

INDIANAPI_KEY  = os.getenv("INDIANAPI_KEY", "")
BASE_URL       = "https://weather.indianapi.in"

# Bharuch district talukas → nearest IMD city
# IMD uses fuzzy matching so city names don't need to be exact
TALUKA_TO_CITY = {
    "bharuch":    "Bharuch",
    "hansot":     "Bharuch",
    "ankleshwar": "Bharuch",
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


def _to_gujarati(description: str) -> str:
    """Convert IMD English forecast description to Gujarati."""
    if not description:
        return "🌤️ સામાન્ય"
    d = description.lower()
    if "thunder" in d:
        return "⛈️ ગર્જનાવાળો વરસાદ"
    if "heavy rain" in d:
        return "🌧️ ભારે વરસાદ"
    if "moderate rain" in d:
        return "🌧️ મધ્યમ વરસાદ"
    if "light rain" in d or "drizzle" in d:
        return "🌦️ હળવો વરસાદ"
    if "rain" in d or "shower" in d:
        return "🌧️ વરસાદ"
    if "snow" in d or "hail" in d:
        return "❄️ હિમ/કરા"
    if "fog" in d or "mist" in d:
        return "🌫️ ધુમ્મસ"
    if "overcast" in d:
        return "☁️ ઘેરા વાદળ"
    if "cloudy" in d:
        return "⛅ વાદળ"
    if "partly cloudy" in d:
        return "🌤️ અડધો વાદળ"
    if "clear" in d or "sunny" in d or "fair" in d or "mainly clear" in d:
        return "☀️ સ્વચ્છ/તડકો"
    if "dust" in d or "haze" in d or "smoke" in d:
        return "🌫️ ધૂળ/ઝાકળ"
    if "wind" in d or "squall" in d:
        return "🌬️ પવન"
    return "🌤️ " + description[:25]


async def fetch_weather(taluka: str) -> dict | None:
    """
    Fetch IMD weather for a taluka.
    Primary: /india/weather (IMD data, most accurate for India)
    Fallback: /global/weather (if city not in IMD database)
    """
    if not INDIANAPI_KEY:
        print("⚠️  INDIANAPI_KEY not set in Render environment variables")
        return None

    city = TALUKA_TO_CITY.get(taluka.strip().lower(), taluka.strip())
    headers = {"x-api-key": INDIANAPI_KEY}

    async with httpx.AsyncClient(timeout=12) as client:

        # ── Primary: IMD endpoint ──────────────────────────────
        try:
            r = await client.get(
                f"{BASE_URL}/india/weather",
                params={"city": city},
                headers=headers
            )
            print(f"🌤️  IMD [{city}]: {r.status_code}")

            if r.status_code == 200:
                raw = r.json()
                result = _parse_imd(raw, taluka)
                if result:
                    return result

        except Exception as e:
            print(f"⚠️  IMD request error: {e}")

        # ── Fallback: global endpoint ─────────────────────────
        try:
            r2 = await client.get(
                f"{BASE_URL}/global/weather",
                params={"location": f"{city},Gujarat,India", "days": 3},
                headers=headers
            )
            print(f"🌤️  Global fallback [{city}]: {r2.status_code}")

            if r2.status_code == 200:
                return _parse_global(r2.json(), taluka)

        except Exception as e:
            print(f"⚠️  Global fallback error: {e}")

    print(f"⚠️  All weather fetches failed for '{taluka}'")
    return None


def _parse_imd(data: dict, taluka: str) -> dict | None:
    """
    Parse /india/weather response.

    Response structure:
    {
      "city": "Bharuch",
      "weather": {
        "current": {
          "humidity": {"morning": 60, "evening": 45},
          "rainfall": null or number,
          "temperature": {
            "max": {"value": 40.0, "departure": 1.2},
            "min": {"value": 28.0, "departure": 0.5}
          }
        },
        "forecast": [
          {"date": "31-May-2026", "max_temp": 41, "min_temp": 28, "description": "Clear sky"},
          {"date": "01-Jun-2026", "max_temp": 40, "min_temp": 27, "description": "Partly cloudy"},
          ...
        ],
        "astronomical": {"sunrise": "06:01", "sunset": "19:42", ...}
      }
    }
    """
    try:
        city_name = data.get("city", taluka)
        weather   = data.get("weather", {})
        current   = weather.get("current", {})
        forecast  = weather.get("forecast", [])
        astro     = weather.get("astronomical", {})

        # Temperature
        temp_data = current.get("temperature", {})
        max_temp  = temp_data.get("max", {}).get("value")
        min_temp  = temp_data.get("min", {}).get("value")

        # Humidity — take morning or evening, whichever is available
        hum_data  = current.get("humidity", {})
        humidity  = hum_data.get("morning") or hum_data.get("evening") or 0

        # Rainfall
        rainfall  = current.get("rainfall") or 0

        # Today's condition comes from forecast[0] description
        today_desc = forecast[0].get("description", "") if forecast else ""
        condition  = _to_gujarati(today_desc)

        # Next 3 days — skip index 0 (today)
        future = []
        for day in forecast[1:4]:
            future.append({
                "date":      day.get("date", ""),
                "max_temp":  day.get("max_temp"),
                "min_temp":  day.get("min_temp"),
                "condition": _to_gujarati(day.get("description", "")),
            })

        print(f"✅  IMD parsed: {city_name} — {max_temp}°C max, {min_temp}°C min, {humidity}% humidity")

        return {
            "taluka":   taluka,
            "city":     city_name,
            "source":   "IMD",
            "condition": condition,
            "today_desc": today_desc,
            "max_temp": max_temp,
            "min_temp": min_temp,
            "humidity": humidity,
            "rainfall": rainfall,
            "sunrise":  astro.get("sunrise", ""),
            "sunset":   astro.get("sunset", ""),
            "forecast": future,
        }

    except Exception as e:
        print(f"⚠️  IMD parse error: {e} | raw: {str(data)[:200]}")
        return None


def _parse_global(data: dict, taluka: str) -> dict | None:
    """
    Parse /global/weather fallback response.

    Response structure:
    {
      "location": "Bharuch, Gujarat",
      "current": {
        "temperature": 38.0, "feels_like": 42.0,
        "humidity": 35, "wind_speed": 18.0,
        "condition": "Sunny", "uv_index": 8
      },
      "forecast": [
        {"date": "2026-05-31", "max_temp": 41, "min_temp": 28,
         "hourly": [{"condition": "Sunny", "chance_of_rain": 0, ...}, ...]}
      ]
    }
    """
    try:
        current  = data.get("current", {})
        raw_fore = data.get("forecast", [])

        # Skip index 0 if it's today
        future = []
        for day in raw_fore[1:4]:
            hourly   = day.get("hourly", [{}])
            rain_ch  = max((h.get("chance_of_rain", 0) for h in hourly), default=0)
            future.append({
                "date":      day.get("date", ""),
                "max_temp":  day.get("max_temp"),
                "min_temp":  day.get("min_temp"),
                "condition": _to_gujarati(
                    hourly[12].get("condition", "") if len(hourly) > 12
                    else (hourly[0].get("condition", "") if hourly else "")
                ),
            })

        temp = round(current.get("temperature", 0))
        print(f"✅  Global parsed: {taluka} — {temp}°C")

        return {
            "taluka":     taluka,
            "city":       data.get("location", taluka),
            "source":     "Global",
            "condition":  _to_gujarati(current.get("condition", "")),
            "today_desc": current.get("condition", ""),
            "max_temp":   temp,
            "min_temp":   temp,
            "humidity":   current.get("humidity", 0),
            "rainfall":   0,
            "sunrise":    "",
            "sunset":     "",
            "forecast":   future,
        }

    except Exception as e:
        print(f"⚠️  Global parse error: {e}")
        return None


# ─────────────────────────────────────────────
# Format for AI system prompt context
# ─────────────────────────────────────────────

def format_weather_for_prompt(weather: dict) -> str:
    if not weather:
        return ""

    alerts = []
    max_t = weather.get("max_temp") or 0
    if weather["humidity"] > 80:
        alerts.append("ભેજ વધારે — ફૂગ/રોગનો ખતરો")
    if weather["humidity"] < 25:
        alerts.append("ભેજ ઓછો — સૂકવણી")
    if max_t > 42:
        alerts.append("ભારે ગરમી — સવાર/સાંજ સિંચાઈ")
    if max_t < 10:
        alerts.append("ઠંડી — નાના પાકને જોખમ")
    if weather["rainfall"] and weather["rainfall"] > 5:
        alerts.append("વરસાદ — છંટકાવ ટાળો")

    forecast_lines = "\n".join(
        f"  {f['date']}: {f['condition']}, {f['min_temp']}–{f['max_temp']}°C"
        for f in weather["forecast"]
    )

    return f"""
━━━ હવામાન — {weather['taluka']} ({weather['source']}) ━━━
{weather['condition']}
તાપમાન: {weather['min_temp']}–{weather['max_temp']}°C | ભેજ: {weather['humidity']}%
ચેતવણી: {' | '.join(alerts) if alerts else 'સામાન્ય'}
આગામી 3 દિવસ:
{forecast_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


# ─────────────────────────────────────────────
# Format for direct farmer weather query
# ─────────────────────────────────────────────

def format_weather_for_farmer(weather: dict) -> str:
    if not weather:
        return (
            "😔 હાલ હવામાનની માહિતી ઉપલબ્ધ નથી.\n"
            "કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો."
        )

    max_t    = weather.get("max_temp")
    min_t    = weather.get("min_temp")
    humidity = weather["humidity"]
    rainfall = weather.get("rainfall") or 0
    source   = weather.get("source", "IMD")

    lines = [f"🌤️ *{weather['taluka']} — આજનું હવામાન* (સ્ત્રોત: {source})\n"]
    lines.append(weather["condition"])

    if max_t and min_t:
        lines.append(f"🌡️ તાપમાન: *{min_t}°C – {max_t}°C*")
    elif max_t:
        lines.append(f"🌡️ તાપમાન: *{max_t}°C*")

    lines.append(f"💧 ભેજ: *{humidity}%*")

    if rainfall and rainfall > 0:
        lines.append(f"🌧️ વરસાદ: *{rainfall}mm*")

    if weather.get("sunrise"):
        lines.append(f"🌅 સૂર્યોદય: {weather['sunrise']} | 🌇 સૂર્યાસ્ત: {weather['sunset']}")

    if weather["forecast"]:
        lines.append("\n📅 *આગામી 3 દિવસ:*")
        for f in weather["forecast"]:
            lines.append(
                f"  {f['date']}: {f['condition']}, "
                f"{f['min_temp']}–{f['max_temp']}°C"
            )

    lines.append("\n💡 *ખેતી સલાહ:*")
    if rainfall > 5:
        lines.append("  વરસાદ છે — આજે દવા છંટકાવ ટાળો.")
    elif humidity > 80:
        lines.append("  ભેજ વધારે — ફૂગના રોગ સતર્ક રહો.")
    elif max_t and max_t > 42:
        lines.append("  ભારે ગરમી — સવારે/સાંજે સિંચાઈ કરો.")
    else:
        lines.append("  હવામાન સામાન્ય — ખેતી માટે સારો દિવસ. ✅")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Weather query detection
# ─────────────────────────────────────────────

WEATHER_TRIGGERS = [
    "હવામાન", "weather",
    "વરસાદ", "rain", "ઠંડી", "ગરમી",
    "temperature", "તાપમાન",
    "વાદળ", "cloud", "ધુમ્મસ", "fog",
    "પવન", "wind",
    "humidity", "ભેજ",
    "આગાહી", "forecast",
    "આજ કેવ", "વાતાવ", "તડકો",
]


def is_weather_query(text: str) -> bool:
    return any(w in text.lower() for w in WEATHER_TRIGGERS)