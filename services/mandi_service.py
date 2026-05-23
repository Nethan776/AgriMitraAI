import httpx
import os
from datetime import date, timedelta

# ─────────────────────────────────────────────
# data.gov.in Agmarknet API
# Free — register at: https://data.gov.in/user/register
# Get API key → My Account → API Keys
# Add to Render env: DATA_GOV_API_KEY=your_key
# Resource ID: 9ef84268-d588-465a-a308-a864a43d0070
# ─────────────────────────────────────────────

DATA_GOV_URL    = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")

# ─────────────────────────────────────────────
# Commodity name mapping
# Gujarati/common → Agmarknet exact name
# ─────────────────────────────────────────────

COMMODITY_MAP = {
    "કપાસ":     "Cotton",
    "kapas":     "Cotton",
    "cotton":    "Cotton",
    "કોટન":     "Cotton",

    "મગફળી":    "Groundnut",
    "mungfali":  "Groundnut",
    "groundnut": "Groundnut",
    "peanut":    "Groundnut",

    "ડુંગળી":   "Onion",
    "dungali":   "Onion",
    "dungali":   "Onion",
    "onion":     "Onion",

    "બટાટા":    "Potato",
    "batata":    "Potato",
    "potato":    "Potato",

    "ટામેટા":   "Tomato",
    "tameta":    "Tomato",
    "tomato":    "Tomato",

    "ઘઉં":      "Wheat",
    "gahu":      "Wheat",
    "wheat":     "Wheat",

    "મકાઈ":     "Maize",
    "makai":     "Maize",
    "maize":     "Maize",

    "તુવેર":    "Tur",
    "tuver":     "Tur",
    "tur":       "Tur",

    "જીરું":    "Cummin Seed(Jeera)",
    "jeera":     "Cummin Seed(Jeera)",
    "jiru":      "Cummin Seed(Jeera)",

    "લસણ":      "Garlic",
    "lasan":     "Garlic",
    "garlic":    "Garlic",

    "દિવેલા":   "Castor Seed",
    "divela":    "Castor Seed",
    "castor":    "Castor Seed",

    "ભીંડા":    "Bhindi(Okra)",
    "bhinda":    "Bhindi(Okra)",
    "bhindi":    "Bhindi(Okra)",

    "રીંગણ":    "Brinjal",
    "ringan":    "Brinjal",
    "brinjal":   "Brinjal",
}

# Price query trigger words
PRICE_TRIGGERS = [
    "ભાવ", "bhav", "price", "rate", "ભાવ શું", "મંડી", "mandi",
    "market", "વેચવ", "આજનો ભાવ", "ભાવ જો", "ભાવ ક", "ભાવ?"
]

# Gujarat mandis near your target area — shown first
PRIORITY_MARKETS = ["bharuch", "ankleshwar", "hansot", "surat", "vadodara"]


def detect_mandi_query(text: str) -> tuple[bool, str | None]:
    """Returns (is_price_query, commodity_agmarknet_name)."""
    text_lower = text.lower()

    is_price = any(w in text_lower for w in PRICE_TRIGGERS)
    if not is_price:
        return False, None

    for key, agmarknet_name in COMMODITY_MAP.items():
        if key.lower() in text_lower:
            return True, agmarknet_name

    return True, None   # Price query, but commodity unknown


async def fetch_mandi_prices(commodity: str, state: str = "Gujarat") -> list[dict]:
    """
    Fetches prices from data.gov.in Agmarknet API.
    Tries today, yesterday, day before — because mandis don't report on weekends/holidays.
    """
    if not DATA_GOV_API_KEY:
        print("⚠️  DATA_GOV_API_KEY not set")
        return []

    for days_back in [0, 1, 2, 3]:
        check_date = date.today() - timedelta(days=days_back)
        date_str   = check_date.strftime("%d/%m/%Y")   # data.gov.in format

        params = {
            "api-key":          DATA_GOV_API_KEY,
            "format":           "json",
            "limit":            "50",
            "filters[state]":   state,
            "filters[commodity]": commodity,
            "filters[arrival_date]": date_str,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(DATA_GOV_URL, params=params)

            if r.status_code != 200:
                print(f"⚠️  data.gov.in returned {r.status_code}: {r.text[:100]}")
                continue

            data    = r.json()
            records = data.get("records", [])

            if not records:
                continue   # No data for this date, try previous day

            # Sort: priority markets first, then by modal price descending
            def sort_key(rec):
                market = rec.get("market", "").lower()
                priority = 0 if any(p in market for p in PRIORITY_MARKETS) else 1
                return (priority, -float(rec.get("modal_price", 0) or 0))

            records.sort(key=sort_key)
            print(f"📊 Mandi: found {len(records)} records for {commodity} on {date_str}")
            return records[:8]

        except Exception as e:
            print(f"⚠️  Mandi fetch error (day -{days_back}): {e}")
            continue

    return []


def format_price_message(commodity: str, prices: list[dict]) -> str:
    """Format fetched prices into a clean Gujarati WhatsApp message."""

    # Get Gujarati display name
    gujarati_name = commodity
    for key, agm in COMMODITY_MAP.items():
        if agm == commodity and len(key) > 2 and not key.isascii():
            gujarati_name = key
            break

    if not prices:
        return (
            f"😔 *{gujarati_name}* ના આજના ભાવ ઉપલબ્ધ નથી.\n\n"
            "ભાવ સામાન્ય રીતે સોમ–શુક્ર મળે છે.\n"
            "નજીકની મંડીમાં સીધો સંપર્ક કરો.\n\n"
            "📱 agmarknet.gov.in"
        )

    price_date = prices[0].get("arrival_date", "")
    lines = [f"📊 *{gujarati_name} — મંડી ભાવ*\n📅 {price_date}\n"]

    for p in prices[:6]:
        market = p.get("market", "").strip()
        modal  = p.get("modal_price",  "—")
        low    = p.get("min_price",    "—")
        high   = p.get("max_price",    "—")
        lines.append(
            f"📍 *{market}*\n"
            f"   સામાન્ય ભાવ: ₹{modal}/ક્વિ\n"
            f"   ન્યૂ: ₹{low}  |  મહ: ₹{high}"
        )

    lines.append("\n_સ્ત્રોત: Agmarknet, ભારત સરકાર_")
    return "\n\n".join(lines)


async def handle_mandi_query(text: str) -> str | None:
    """
    Main entry point called from app.py.
    Returns formatted Gujarati price message, or None if not a price query.
    """
    is_price_query, commodity = detect_mandi_query(text)

    if not is_price_query:
        return None

    if commodity is None:
        return (
            "🌾 *કયા પાકના ભાવ જોઈએ છે?*\n\n"
            "આ પ્રમાણે લખો:\n"
            "• *કપાસ ભાવ*\n"
            "• *મગફળી ભાવ*\n"
            "• *ડુંગળી ભાવ*\n"
            "• *ઘઉં ભાવ*\n"
            "• *ટામેટા ભાવ*\n"
            "• *જીરું ભાવ*"
        )

    prices = await fetch_mandi_prices(commodity)
    return format_price_message(commodity, prices)