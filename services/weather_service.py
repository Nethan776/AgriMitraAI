import httpx

# ─────────────────────────────────────────────
# Open-Meteo — completely free, no API key
# https://open-meteo.com
# ─────────────────────────────────────────────

WEATHER_URL  = "https://api.open-meteo.com/v1/forecast"
GEO_URL      = "https://geocoding-api.open-meteo.com/v1/search"

# Pre-cached coordinates for your target talukas + nearby towns
# Avoids a geocoding API call on every message
KNOWN_LOCATIONS = {
    # Bharuch district
    "bharuch":     (21.7051, 72.9959),
    "hansot":      (21.5833, 72.8167),
    "ankleshwar":  (21.6266, 72.9986),
    "amod":        (22.0167, 72.8667),
    "jambusar":    (22.0561, 72.8022),
    "vagra":       (21.4833, 72.9667),
    "jhagadia":    (21.5833, 73.0833),
    "valia":       (21.3833, 73.0833),

    # Nearby districts
    "surat":       (21.1702, 72.8311),
    "vadodara":    (22.3072, 73.1812),
    "ahmedabad":   (23.0225, 72.5714),
    "navsari":     (20.9467, 72.9520),
    "narmada":     (21.8722, 73.4882),
}

# WMO weather code → simple Gujarati description
WEATHER_DESCRIPTIONS = {
    0:  "맑은 하늘",   # fallback, replaced below
}

WMO_TO_GUJARATI = {
    0:  "☀️ સ્વચ્છ આકાશ",
    1:  "🌤️ મોટે ભાગે સ્વચ્છ",
    2:  "⛅ અડધો વાદળ",
    3:  "☁️ વાદળ છે",
    45: "🌫️ ધુમ્મસ",
    48: "🌫️ ભારે ધુમ્મસ",
    51: "🌦️ હળવો ઝરમર",
    53: "🌦️ ઝરમર વરસાદ",
    55: "🌧️ ભારે ઝરમર",
    61: "🌧️ હળવો વરસાદ",
    63: "🌧️ મધ્યમ વરસાદ",
    65: "🌧️ ભારે વરસાદ",
    71: "❄️ હળવો હિમ",
    73: "❄️ મધ્યમ હિમ",
    75: "❄️ ભારે હિમ",
    80: "🌦️ વરસાદના ઝાપટા",
    81: "🌧️ મધ્યમ ઝાપટા",
    82: "⛈️ ભારે ઝાપટા",
    95: "⛈️ ગર્જનાવાળો વરસાદ",
    96: "⛈️ કરા સાથે વાવાઝોડું",
    99: "⛈️ ભારે કરા સાથે",
}


def _get_coordinates(taluka: str) -> tuple[float, float] | None:
    """Get lat/lon for a taluka. Checks known list first."""
    if not taluka:
        return None
    key = taluka.strip().lower()
    return KNOWN_LOCATIONS.get(key)


async def _geocode(location: str) -> tuple[float, float] | None:
    """Fallback: geocode any unknown location via Open-Meteo geocoding API."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(GEO_URL, params={
                "name":     f"{location} Gujarat India",
                "count":    1,
                "language": "en"
            })
        data = r.json()
        if data.get("results"):
            res = data["results"][0]
            return res["latitude"], res["longitude"]
    except Exception as e:
        print(f"⚠️  Geocoding failed for '{location}': {e}")
    return None


async def fetch_weather(taluka: str) -> dict | None:
    """
    Fetch current weather + 3-day forecast for a taluka.
    Returns a structured dict or None on failure.
    """
    coords = _get_coordinates(taluka)

    if not coords:
        # Try geocoding for unknown talukas
        coords = await _geocode(taluka)

    if not coords:
        print(f"⚠️  Could not get coordinates for '{taluka}'")
        return None

    lat, lon = coords

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(WEATHER_URL, params={
                "latitude":   lat,
                "longitude":  lon,
                "current":    "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
                "daily":      "precipitation_sum,temperature_2m_max,temperature_2m_min,weather_code",
                "forecast_days": 3,
                "timezone":   "Asia/Kolkata"
            })

        if r.status_code != 200:
            print(f"⚠️  Open-Meteo returned {r.status_code}")
            return None

        data    = r.json()
        current = data.get("current", {})
        daily   = data.get("daily", {})

        weather_code = current.get("weather_code", 0)
        humidity     = current.get("relative_humidity_2m", 0)
        temp         = current.get("temperature_2m", 0)
        rain_now     = current.get("precipitation", 0)
        wind         = current.get("wind_speed_10m", 0)

        # Build 3-day forecast
        forecast = []
        dates      = daily.get("time", [])
        max_temps  = daily.get("temperature_2m_max", [])
        min_temps  = daily.get("temperature_2m_min", [])
        rain_daily = daily.get("precipitation_sum", [])
        day_codes  = daily.get("weather_code", [])

        for i in range(min(3, len(dates))):
            forecast.append({
                "date":     dates[i],
                "max_temp": max_temps[i] if i < len(max_temps) else None,
                "min_temp": min_temps[i] if i < len(min_temps) else None,
                "rain_mm":  rain_daily[i] if i < len(rain_daily) else 0,
                "condition": WMO_TO_GUJARATI.get(day_codes[i] if i < len(day_codes) else 0, "—"),
            })

        return {
            "taluka":      taluka,
            "condition":   WMO_TO_GUJARATI.get(weather_code, "—"),
            "temp":        temp,
            "humidity":    humidity,
            "rain_now":    rain_now,
            "wind":        wind,
            "forecast":    forecast,
        }

    except Exception as e:
        print(f"⚠️  Weather fetch error: {e}")
        return None


def format_weather_for_prompt(weather: dict) -> str:
    """
    Format weather data as a compact context block
    to inject into the AI system prompt.
    """
    if not weather:
        return ""

    taluka   = weather["taluka"]
    cond     = weather["condition"]
    temp     = weather["temp"]
    humidity = weather["humidity"]
    rain     = weather["rain_now"]
    wind     = weather["wind"]

    # Farming-relevant alerts
    alerts = []
    if humidity > 80:
        alerts.append("ભેજ વધારે — ફૂગ/રોગનો ખતરો")
    if humidity < 30:
        alerts.append("ભેજ ઓછો — સૂકવણીનો ખતરો")
    if temp > 42:
        alerts.append("ભારે ગરમી — સિંચાઈ જરૂરી")
    if temp < 10:
        alerts.append("ઠંડી — પ્રારંભિક અવસ્થાના પાકને નુકસાન")
    if rain > 20:
        alerts.append("ભારે વરસાદ — ખેતર ભૂ-ક્ષારવાળું ન થાય")
    if wind > 40:
        alerts.append("તેજ પવન — દવા છંટકાવ ટાળો")

    forecast_lines = []
    for f in weather.get("forecast", []):
        forecast_lines.append(
            f"  {f['date']}: {f['condition']}, "
            f"max {f['max_temp']}°C, "
            f"વરસાદ {f['rain_mm']}mm"
        )

    alert_text = " | ".join(alerts) if alerts else "સામાન્ય"

    return f"""
━━━ હવામાન — {taluka} (હાલ) ━━━
સ્થિતિ: {cond}
તાપમાન: {temp}°C | ભેજ: {humidity}% | પવન: {wind} km/h | વરસાદ: {rain}mm
ખેતી ચેતવણી: {alert_text}

આગામી 3 દિવસ:
{chr(10).join(forecast_lines)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def format_weather_for_farmer(weather: dict) -> str:
    """
    Format weather as a readable Gujarati reply
    when farmer directly asks about weather.
    """
    if not weather:
        return (
            "😔 હાલ હવામાનની માહિતી ઉપલબ્ધ નથી.\n"
            "કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો."
        )

    taluka   = weather["taluka"]
    cond     = weather["condition"]
    temp     = weather["temp"]
    humidity = weather["humidity"]
    rain     = weather["rain_now"]
    wind     = weather["wind"]

    lines = [f"🌤️ *{taluka} — આજનું હવામાન*\n"]
    lines.append(f"{cond}")
    lines.append(f"🌡️ તાપમાન: *{temp}°C*")
    lines.append(f"💧 ભેજ: *{humidity}%*")
    lines.append(f"🌬️ પવન: *{wind} km/h*")
    if rain > 0:
        lines.append(f"🌧️ વરસાદ: *{rain}mm*")

    lines.append("\n📅 *આગામી 3 દિવસ:*")
    for f in weather.get("forecast", []):
        rain_text = f" | 🌧️ {f['rain_mm']}mm" if f['rain_mm'] > 0 else ""
        lines.append(
            f"  {f['date']}: {f['condition']}, "
            f"{f['min_temp']}–{f['max_temp']}°C{rain_text}"
        )

    # Farming tip based on weather
    lines.append("\n💡 *ખેતી સલાહ:*")
    if rain > 10:
        lines.append("  આજે દવા છંટકાવ ટાળો.")
    elif humidity > 80:
        lines.append("  ભેજ વધારે છે — ફૂગના રોગ માટે સતર્ક રહો.")
    elif temp > 40:
        lines.append("  ભારે ગરમી — સવારે અથવા સાંજે સિંચાઈ કરો.")
    elif wind > 30:
        lines.append("  તેજ પવન — આજે છંટકાવ ટાળો.")
    else:
        lines.append("  હવામાન સામાન્ય — ખેતી માટે સારો દિવસ.")

    lines.append("\n_સ્ત્રોત: Open-Meteo_")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Weather query detection
# ─────────────────────────────────────────────

WEATHER_TRIGGERS = [
    "હવામાન", "weather", "વરસાદ", "rain", "ઠંડી", "ગરમી",
    "temperature", "તાપમાન", "વાદળ", "cloud", "ધુમ્મસ", "fog",
    "પવન", "wind", "humidity", "ભેજ", "આગાહી", "forecast",
    "આજ કેવ", "આજ ક", "વાતાવ"
]


def is_weather_query(text: str) -> bool:
    text_lower = text.lower()
    return any(w in text_lower for w in WEATHER_TRIGGERS)