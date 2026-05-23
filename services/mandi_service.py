import httpx
import os
from datetime import date, timedelta
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# Commodity name mapping
# Gujarati/common name → Agmarknet exact name
# ─────────────────────────────────────────────

COMMODITY_MAP = {
    # Cotton
    "કપાસ":        "Kapas(Cotton Seed with Fibre)",
    "kapas":        "Kapas(Cotton Seed with Fibre)",
    "cotton":       "Kapas(Cotton Seed with Fibre)",
    "કોટન":        "Kapas(Cotton Seed with Fibre)",

    # Groundnut
    "મગફળી":       "Groundnut",
    "groundnut":    "Groundnut",
    "peanut":       "Groundnut",

    # Onion
    "ડુંગળી":      "Onion",
    "dungali":      "Onion",
    "onion":        "Onion",
    "dungli":       "Onion",

    # Potato
    "બટાટા":       "Potato",
    "batata":       "Potato",
    "potato":       "Potato",

    # Tomato
    "ટામેટા":      "Tomato",
    "tameta":       "Tomato",
    "tomato":       "Tomato",

    # Wheat
    "ઘઉં":         "Wheat",
    "gahu":         "Wheat",
    "wheat":        "Wheat",

    # Maize
    "મકાઈ":        "Maize",
    "makai":        "Maize",
    "maize":        "Maize",
    "corn":         "Maize",

    # Tuvar (Pigeon pea)
    "તુવેર":       "Tur",
    "tuver":        "Tur",
    "tur":          "Tur",
    "arhar":        "Tur",

    # Castor
    "દિવેલા":      "Castor Seed",
    "divela":       "Castor Seed",
    "castor":       "Castor Seed",

    # Cumin
    "જીરું":       "Cummin Seed(Jeera)",
    "jeera":        "Cummin Seed(Jeera)",
    "jiru":         "Cummin Seed(Jeera)",
    "cumin":        "Cummin Seed(Jeera)",

    # Garlic
    "લસણ":         "Garlic",
    "lasan":        "Garlic",
    "garlic":       "Garlic",
}

# Gujarat mandis to check (in priority order for your target area)
GUJARAT_MARKETS = [
    "Bharuch", "Ankleshwar", "Hansot",
    "Surat", "Vadodara", "Ahmedabad",
    "Rajkot", "Bhavnagar", "Gondal"
]


# ─────────────────────────────────────────────
# Price detection from farmer message
# ─────────────────────────────────────────────

PRICE_TRIGGER_WORDS = [
    "ભાવ", "bhav", "price", "rate", "ભાવ શું", "મંડી",
    "mandi", "market", "વેચવો", "વેચાણ", "આજનો ભાવ",
    "ભાવ જોઈ", "ભાવ કેટ", "ભાવ ક"
]


def detect_mandi_query(text: str) -> tuple[bool, str | None]:
    """
    Returns (is_mandi_query, commodity_agmarknet_name).
    Checks if farmer is asking about prices and which commodity.
    """
    text_lower = text.lower()

    # Check if it's a price query
    is_price = any(w in text_lower for w in PRICE_TRIGGER_WORDS)
    if not is_price:
        return False, None

    # Find which commodity they're asking about
    for gujarati_name, agmarknet_name in COMMODITY_MAP.items():
        if gujarati_name.lower() in text_lower:
            return True, agmarknet_name

    # Price query but commodity not detected — return True so we can ask
    return True, None


# ─────────────────────────────────────────────
# Agmarknet scraper
# ─────────────────────────────────────────────

async def fetch_mandi_prices(commodity_agmarknet: str, state: str = "Gujarat") -> list[dict]:
    """
    Scrapes today's prices from Agmarknet for a given commodity in Gujarat.
    Falls back to yesterday if today has no data yet (prices update by noon).
    Returns list of { market, min_price, max_price, modal_price, date }
    """
    results = []

    for days_back in [0, 1, 2]:   # Try today, yesterday, day before
        check_date = date.today() - timedelta(days=days_back)
        date_str = check_date.strftime("%d-%b-%Y")

        url = "https://agmarknet.gov.in/SearchCmmMkt.aspx"
        params = {
            "Tx_Commodity":     commodity_agmarknet,
            "Tx_State":         state,
            "Tx_District":      "0",
            "Tx_Market":        "0",
            "DateFrom":         date_str,
            "DateTo":           date_str,
            "Fr_Date":          date_str,
            "To_Date":          date_str,
            "Tx_Trend":         "0",
            "Tx_CommodityHead": commodity_agmarknet,
            "Tx_StateHead":     state,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer":    "https://agmarknet.gov.in/",
            "Accept":     "text/html,application/xhtml+xml"
        }

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", {"id": "cphBody_GridPriceData"})

            if not table:
                continue

            rows = table.find_all("tr")[1:]   # Skip header
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 8:
                    results.append({
                        "market":      cols[2],
                        "commodity":   cols[0],
                        "variety":     cols[1],
                        "min_price":   cols[4],
                        "max_price":   cols[5],
                        "modal_price": cols[6],
                        "date":        cols[7] if len(cols) > 7 else date_str,
                    })

            if results:
                # Prioritize mandis near your target area
                results.sort(key=lambda x: (
                    0 if any(m.lower() in x["market"].lower() for m in GUJARAT_MARKETS[:3])
                    else 1
                ))
                return results[:8]   # Return top 8 markets

        except Exception as e:
            print(f"⚠️  Agmarknet fetch error (day -{days_back}): {e}")
            continue

    return []


# ─────────────────────────────────────────────
# Format prices into Gujarati WhatsApp message
# ─────────────────────────────────────────────

def format_price_message(commodity_agmarknet: str, prices: list[dict]) -> str:
    """Format fetched prices into a clean Gujarati message."""

    # Find Gujarati name for display
    gujarati_name = commodity_agmarknet
    for guj, agm in COMMODITY_MAP.items():
        if agm == commodity_agmarknet and len(guj) > 2:
            gujarati_name = guj
            break

    if not prices:
        return (
            f"😔 આજે {gujarati_name}ના ભાવ Agmarknet પર ઉપલબ્ધ નથી.\n\n"
            f"કૃપા કરીને સ્થાનિક મંડીમાં સીધો સંપર્ક કરો અથવા થોડા સમય પછી ફરી પ્રયાસ કરો.\n\n"
            f"📱 Agmarknet: agmarknet.gov.in"
        )

    price_date = prices[0].get("date", "આજે")
    lines = [f"📊 *{gujarati_name} — મંડી ભાવ* ({price_date})\n"]

    for p in prices[:6]:
        market = p["market"]
        modal  = p["modal_price"]
        low    = p["min_price"]
        high   = p["max_price"]
        lines.append(
            f"📍 *{market}*\n"
            f"   સામાન્ય: ₹{modal}/ક્વિ\n"
            f"   ન્યૂનતમ: ₹{low} | મહત્તમ: ₹{high}"
        )

    lines.append("\n_સ્ત્રોત: Agmarknet (ભારત સરકાર)_")
    return "\n\n".join(lines)


# ─────────────────────────────────────────────
# Main function called from app.py
# ─────────────────────────────────────────────

async def handle_mandi_query(text: str) -> str | None:
    """
    If farmer is asking about prices, fetch and return formatted message.
    Returns None if this is not a price query.
    """
    is_price_query, commodity = detect_mandi_query(text)

    if not is_price_query:
        return None

    if commodity is None:
        # Price query but no commodity detected — ask which one
        return (
            "🌾 કયા પાકના ભાવ જોઈએ છે?\n\n"
            "ઉદ્દાહરણ:\n"
            "• *કપાસ ભાવ*\n"
            "• *મગફળી ભાવ*\n"
            "• *ડુંગળી ભાવ*\n"
            "• *ઘઉં ભાવ*\n"
            "• *ટામેટા ભાવ*"
        )

    print(f"📊 Mandi query: {commodity}")
    prices = await fetch_mandi_prices(commodity)
    return format_price_message(commodity, prices)