
import os
import time
import httpx

VISUAL_CROSSING_API_KEY = os.getenv("VISUAL_CROSSING_API_KEY", "")
BASE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
CACHE_TTL = 900
_weather_cache = {}

def _condition_gujarati(condition: str) -> str:
    if not condition:
        return "🌤️ સામાન્ય"
    c = condition.lower()
    mapping = {
        "clear":"☀️ સ્વચ્છ","partially cloudy":"⛅ આંશિક વાદળછાયું",
        "partly cloudy":"⛅ આંશિક વાદળછાયું","cloudy":"☁️ વાદળછાયું",
        "overcast":"☁️ ઘેરા વાદળ","rain":"🌧️ વરસાદ",
        "showers":"🌦️ ઝાપટાં","thunderstorm":"⛈️ ગાજવીજ સાથે વરસાદ",
        "fog":"🌫️ ધુમ્મસ","mist":"🌫️ ઝાકળ","snow":"❄️ હિમવર્ષા",
    }
    for k,v in mapping.items():
        if k in c:
            return v
    return condition

async def fetch_weather(location:str)->dict|None:
    if not VISUAL_CROSSING_API_KEY:
        print("VISUAL_CROSSING_API_KEY missing")
        return None
    location=(location or "Bharuch").strip()
    cache=_weather_cache.get(location.lower())
    if cache and time.time()-cache["time"]<CACHE_TTL:
        return cache["data"]
    url=(f"{BASE_URL}/{location},Gujarat,India"
         f"?unitGroup=metric&include=current,days"
         f"&key={VISUAL_CROSSING_API_KEY}&contentType=json")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.get(url)
        if r.status_code!=200:
            print(r.text)
            return None
        raw=r.json()
        current=raw.get("currentConditions",{})
        days=raw.get("days",[])
        forecast=[]
        for d in days[1:4]:
            forecast.append({
                "date":d.get("datetime"),
                "condition":_condition_gujarati(d.get("conditions","")),
                "max_temp":round(d.get("tempmax",0)),
                "min_temp":round(d.get("tempmin",0)),
                "rain_probability":d.get("precipprob",0),
            })
        weather={
            "location":location,
            "condition":_condition_gujarati(current.get("conditions","")),
            "today_desc":current.get("conditions",""),
            "temp":round(current.get("temp",0)),
            "max_temp":round(days[0].get("tempmax",current.get("temp",0))),
            "min_temp":round(days[0].get("tempmin",current.get("temp",0))),
            "humidity":current.get("humidity",0),
            "rain_probability":days[0].get("precipprob",0),
            "wind_speed":current.get("windspeed",0),
            "uv":current.get("uvindex",0),
            "sunrise":current.get("sunrise",""),
            "sunset":current.get("sunset",""),
            "forecast":forecast,
            "source":"Visual Crossing"
        }
        _weather_cache[location.lower()]={"time":time.time(),"data":weather}
        return weather
    except Exception as e:
        print(e)
        return None

def format_weather_for_prompt(weather):
    if not weather:
        return ""
    alerts=[]
    if weather["rain_probability"]>=60: alerts.append("વરસાદની શક્યતા વધારે")
    if weather["humidity"]>=80: alerts.append("ભેજ વધારે")
    if weather["max_temp"]>=40: alerts.append("ગરમી વધારે")
    forecast="\n".join(f"{d['date']}: {d['condition']} ({d['min_temp']}–{d['max_temp']}°C)" for d in weather["forecast"])
    return f"""સ્થળ: {weather['location']}
હવામાન: {weather['condition']}
તાપમાન: {weather['min_temp']}–{weather['max_temp']}°C
ભેજ: {weather['humidity']}%
વરસાદની શક્યતા: {weather['rain_probability']}%
ચેતવણી: {', '.join(alerts) if alerts else 'કોઈ ખાસ નથી'}

આગામી દિવસો:
{forecast}"""

def format_weather_for_farmer(weather):
    if not weather:
        return "😔 હાલમાં હવામાનની માહિતી ઉપલબ્ધ નથી."
    advice="✅ આજે ખેતી માટે સામાન્ય દિવસ."
    if weather["rain_probability"]>=60:
        advice="🌧️ આજે છંટકાવ ટાળવો."
    elif weather["humidity"]>=80:
        advice="🍃 ભેજ વધારે છે. ફૂગના રોગ પર નજર રાખો."
    elif weather["max_temp"]>=40:
        advice="☀️ સવારે અથવા સાંજે સિંચાઈ કરવી."
    lines=[
        f"🌤️ *{weather['location']} - આજનું હવામાન*","",
        weather["condition"],
        f"🌡️ {weather['min_temp']}°C - {weather['max_temp']}°C",
        f"💧 ભેજ: {weather['humidity']}%",
        f"🌧️ વરસાદની શક્યતા: {weather['rain_probability']}%",
        f"💨 પવન: {weather['wind_speed']} km/h","","📅 આગામી 3 દિવસ:"
    ]
    for d in weather["forecast"]:
        lines.append(f"• {d['date']}: {d['condition']} ({d['min_temp']}–{d['max_temp']}°C)")
    lines.extend(["","💡 ખેતી સલાહ:",advice])
    return "\n".join(lines)

WEATHER_TRIGGERS=["weather","હવામાન","વરસાદ","rain","તાપમાન","temperature","ભેજ","humidity","forecast","આગાહી","wind","પવન"]

def is_weather_query(text):
    return bool(text) and any(w in text.lower() for w in WEATHER_TRIGGERS)
