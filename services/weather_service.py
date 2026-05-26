import httpx
import os

# ─────────────────────────────────────────────
# WeatherAPI.com
# Key already set — add to Render env:
# WEATHERAPI_KEY=c2b6ffa4d17042f19b9114144262605
#
# One call returns current + 3-day forecast
# Docs: https://www.weatherapi.com/docs/
# ─────────────────────────────────────────────

WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY", "")
WEATHERAPI_URL = "https://api.weatherapi.com/v1/forecast.json"

# Pre-cached locations for your target area
# WeatherAPI also accepts city name strings directly,
# but this avoids any ambiguity
KNOWN_LOCATIONS = {
    "bharuch":    "Bharuch,Gujarat,India",
    "hansot":     "Hansot,Gujarat,India",
    "ankleshwar": "Ankleshwar,Gujarat,India",
    "amod":       "Amod,Gujarat,India",
    "jambusar":   "Jambusar,Gujarat,India",
    "vagra":      "Vagra,Gujarat,India",
    "jhagadia":   "Jhagadia,Gujarat,India",
    "valia":      "Valia,Gujarat,India",
    "surat":      "Surat,Gujarat,India",
    "vadodara":   "Vadodara,Gujarat,India",
    "ahmedabad":  "Ahmedabad,Gujarat,India",
    "navsari":    "Navsari,Gujarat,India",
    "rajkot":     "Rajkot,Gujarat,India",
    "narmada":    "Narmada,Gujarat,India",
}


def _condition_gujarati(text: str, precip_mm: float = 0) -> str:
    """Convert WeatherAPI English condition to Gujarati emoji + text."""
    t = text.lower()
    if "thunder" in t:
        return "⛈️ ગર્જનાવાળો વરસાદ"
    elif "heavy rain" in t or "torrential" in t:
        return "🌧️ ભારે વરસાદ"
    elif "moderate rain" in t:
        return "🌧️ મધ્યમ વરસાદ"
    elif "light rain" in t or "drizzle" in t or "patchy rain" in t:
        return "🌦️ હળવો વરસાદ"
    elif "rain" in t:
        return "🌧️ વરસાદ"
    elif "snow" in t or "sleet" in t or "blizzard" in t:
        return "❄️ હિમ"
    elif "fog" in t or "mist" in t:
        return "🌫️ ધુમ્મસ"
    elif "overcast" in t:
        return "☁️ વાદળ છે"
    elif "cloudy" in t:
        return "⛅ વાદળ"
    elif "partly cloudy" in t:
        return "🌤️ અડધો વાદળ"
    elif "sunny" in t or "clear" in t:
        return "☀️ સ્વચ્છ/તડકો"
    elif "haze" in t or "smoke" in t or "dust" in t:
        return "🌫️ ઝાકળ/ધૂળ"
    elif "wind" in t:
        return "🌬️ પવનવાળો"
    elif precip_mm > 0:
        return "🌧️ વરસાદ"
    return "🌤️ સામાન્ย"


async def fetch_weather(taluka: str) -> dict | None:
    """
    Fetch current weather + 3-day forecast from WeatherAPI.com.
    Single API call returns everything.
    """
    if not WEATHERAPI_KEY:
        print("⚠️  WEATHERAPI_KEY not set in Render environment variables")
        return None

    # Build location query
    location_key = taluka.strip().lower()
    query = KNOWN_LOCATIONS.get(location_key, f"{taluka},Gujarat,India")

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(WEATHERAPI_URL, params={
                "key":     WEATHERAPI_KEY,
                "q":       query,
                "days":    4,  # Fetch 4 days — skip today, show next 3
                "aqi":     "no",
                "alerts":  "no",
            })

        print(f"🌤️  WeatherAPI: {r.status_code} for '{query}'")

        if r.status_code == 401:
            print("⚠️  Invalid API key — check WEATHERAPI_KEY in Render")
            return None
        if r.status_code == 400:
            print(f"⚠️  Location not found: '{query}'")
            return None
        if r.status_code != 200:
            print(f"⚠️  WeatherAPI error: {r.status_code} {r.text[:150]}")
            return None

        data     = r.json()
        location = data["location"]
        current  = data["current"]
        forecast_days = data["forecast"]["forecastday"]

        # Current conditions
        precip   = current["precip_mm"]
        cond_txt = current["condition"]["text"]
        condition = _condition_gujarati(cond_txt, precip)

        # 3-day forecast
        forecast = []
        for day in forecast_days[1:]:  # Skip today — already shown as current
            d = day["day"]
            forecast.append({
                "date":      day["date"],
                "max_temp":  round(d["maxtemp_c"]),
                "min_temp":  round(d["mintemp_c"]),
                "rain_mm":   round(d["totalprecip_mm"], 1),
                "rain_chance": d.get("daily_chance_of_rain", 0),
                "condition": _condition_gujarati(d["condition"]["text"], d["totalprecip_mm"]),
            })

        result = {
            "taluka":      location["name"],
            "region":      location["region"],
            "condition":   condition,
            "temp":        round(current["temp_c"]),
            "feels_like":  round(current["feelslike_c"]),
            "humidity":    current["humidity"],
            "wind":        round(current["wind_kph"]),
            "rain_now":    round(precip, 1),
            "uv_index":    current.get("uv", 0),
            "forecast":    forecast,
        }

        print(f"✅  Weather OK: {result['taluka']} — {result['temp']}°C, {cond_txt}")
        return result

    except Exception as e:
        print(f"⚠️  WeatherAPI exception: {e}")
        return None


# ─────────────────────────────────────────────
# Format for AI system prompt
# ─────────────────────────────────────────────

def format_weather_for_prompt(weather: dict) -> str:
    """Compact block injected into AI context before every response."""
    if not weather:
        return ""

    alerts = []
    if weather["humidity"] > 80:
        alerts.append("ભેજ વધારે — ફૂગ/રોગનો ખતરો")
    if weather["humidity"] < 25:
        alerts.append("ભેજ ઓછો — સૂકવણી")
    if weather["temp"] > 42:
        alerts.append("ભારે ગરમી — સવાર/સાંજ સિંચાઈ")
    if weather["temp"] < 10:
        alerts.append("ઠંડી — નાના પાકને જોખમ")
    if weather["rain_now"] > 5:
        alerts.append("વરસાદ — છંટકાવ ટાળો")
    if weather["wind"] > 35:
        alerts.append("તેજ પવન — છંટકાવ ટાળો")

    forecast_lines = "\n".join(
        f"  {f['date']}: {f['condition']}, "
        f"{f['min_temp']}–{f['max_temp']}°C, "
        f"વરસાદ {f['rain_mm']}mm ({f['rain_chance']}% chance)"
        for f in weather["forecast"]
    )

    return f"""
━━━ હવામાન — {weather['taluka']}, {weather['region']} ━━━
{weather['condition']} | {weather['temp']}°C (feels {weather['feels_like']}°C)
ભેજ: {weather['humidity']}% | પવન: {weather['wind']} km/h | વરસાદ: {weather['rain_now']}mm
ખેતી ચેતવણી: {' | '.join(alerts) if alerts else 'સામાન્ય'}
આગામી 3 દિવસ:
{forecast_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


# ─────────────────────────────────────────────
# Format for direct farmer weather query
# ─────────────────────────────────────────────

def format_weather_for_farmer(weather: dict) -> str:
    """Full Gujarati weather card shown when farmer asks about weather."""
    if not weather:
        return (
            "😔 હાલ હવામાનની માહિતી ઉપલબ્ધ નથી.\n"
            "કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો."
        )

    lines = [f"🌤️ *{weather['taluka']}, {weather['region']} — આજનું હવામાન*\n"]
    lines.append(weather["condition"])
    lines.append(f"🌡️ તાપમાન: *{weather['temp']}°C* (feels like {weather['feels_like']}°C)")
    lines.append(f"💧 ભેજ: *{weather['humidity']}%*")
    lines.append(f"🌬️ પવન: *{weather['wind']} km/h*")
    if weather["rain_now"] > 0:
        lines.append(f"🌧️ વરસાદ: *{weather['rain_now']}mm*")
    if weather["uv_index"] >= 8:
        lines.append(f"☀️ UV Index: *{weather['uv_index']}* (ખૂબ વધારે — ઢાંકીને રહો)")

    lines.append("\n📅 *આગામી 3 દિવસ:*")
    for f in weather["forecast"]:
        rain_text = f" | 🌧️ {f['rain_mm']}mm ({f['rain_chance']}%)" if f["rain_chance"] > 10 else ""
        lines.append(
            f"  {f['date']}: {f['condition']}, "
            f"{f['min_temp']}–{f['max_temp']}°C{rain_text}"
        )

    lines.append("\n💡 *ખેતી સલાહ:*")
    if weather["rain_now"] > 5:
        lines.append("  વરસાદ છે — આજે દવા છંટકાવ ટાળો.")
    elif weather["humidity"] > 80:
        lines.append("  ભેજ વધારે — ફૂગના રોગ માટે સતર્ક રહો.")
    elif weather["temp"] > 42:
        lines.append("  ભારે ગરમી — સવારે/સાંજે સિંચાઈ કરો.")
    elif weather["wind"] > 35:
        lines.append("  તેજ પવન — આજે છંટકાવ ટાળો.")
    else:
        lines.append("  હવામાન સામાન્ય — ખેતી માટે સારો દિવસ. ✅")

    lines.append("\n_સ્ત્રોત: WeatherAPI.com_")
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