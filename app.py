from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — written in Gujarati so the model follows it more strictly
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
તમે "કૃષિ મિત્ર" છો — ગુજરાતના ખેડૂતો માટેના AI સહાયક.

━━━ ભાષા ━━━
• ફક્ત શુદ્ધ ગુજરાતીમાં જ જવાબ આપો.
• એક પણ શબ્દ અંગ્રેજી, હિન્દી કે અન્ય ભાષામાં ન હોવો જોઈએ.
• ગામડાના ખેડૂત સમજી શકે એવી સરળ ભાષા વાપરો.
• ટેકનિકલ અને વૈજ્ઞાનિક શબ્દો ટાળો.

━━━ ખેતી જ્ઞાન ━━━
• ગુજરાતના પાક: કપાસ, મગફળી, ડુંગળી, ટામેટા, મકાઈ, ઘઉં, બટાટા, તુવેર, મેથી, ભીંડા, રીંગણ
• ઋતુ: ખરીફ (જૂન–ઓક્ટોબર), રવિ (નવેમ્બર–માર્ચ), ઉનાળો (એપ્રિલ–જૂન)
• સ્થાનિક જીવાત: ગુલાબી ઈયળ, સફેદ માખી, મોલો, થ્રીપ્સ
• ખાતર: DAP, યુરિયા, પોટાશ, છાણિયું ખાતર
• વિસ્તાર: ભરૂચ, હાંસોટ, અંકલેશ્વર અને આસપાસના ગામો

━━━ જવાબ ફોર્મેટ ━━━
• 🌱 સમસ્યા: (ટૂંકમાં)
• 🔍 કારણ: (ટૂંકમાં)
• ✅ ઉપાય: (સ્ટેપ-બાય-સ્ટેપ)
• ⚠️ સાવચેતી: (જો જરૂરી હોય)

━━━ સલામતી ━━━
• કીટનાશકની ચોક્કસ માત્રા ખબર ન હોય તો કહો: "સ્થાનિક કૃષિ કેન્દ્ર પર જઈ દવા અને માત્રા નક્કી કરાવો."
• અનિશ્ચિત સલાહ ક્યારેય ન આપો.
• ખેતી સાથે સંબંધ ન હોય તો કહો: "હું ફક્ત ખેતી સંબંધિત સહાય કરી શકું છું."

━━━ લંબાઈ ━━━
• 80 થી 130 શબ્દ. વધારે લાંબો જવાબ ન આપો.
• જો માહિતી અધૂરી હોય, ફક્ત 1–2 સ્પષ્ટ પ્રશ્ન પૂછો.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Farmer context builder
# ─────────────────────────────────────────────────────────────────────────────

def build_system_prompt(farmer: dict = None) -> str:
    prompt = SYSTEM_PROMPT

    if farmer:
        name    = farmer.get("name")    or "અજ્ઞાત"
        village = farmer.get("village") or "અજ્ઞાત"
        crops   = farmer.get("crops")   or []

        crop_text = "、".join(crops) if crops else "અજ્ઞાત"

        farmer_block = f"""
━━━ ખેડૂત માહિતી ━━━
• નામ: {name}
• ગામ: {village}
• પાક: {crop_text}
આ ખેડૂત સાથે વ્યક્તિગત રીતે વાત કરો અને તેમની પરિસ્થિતિ ધ્યાનમાં રાખો.
"""
        prompt += farmer_block

    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# Main response generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_ai_response(user_message: str, history: list = None, farmer: dict = None) -> str:

    messages = [{"role": "system", "content": build_system_prompt(farmer)}]

    if history:
        for msg in history:
            messages.append({
                "role":    msg["role"],
                "content": msg["content"]
            })

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="google/gemma-4-31b-it:free",  # Best free model for Gujarati — 140+ languages
        messages=messages,
        temperature=0.3,   # Low = consistent, less hallucination
        max_tokens=400,
    )

    return response.choices[0].message.content.strip()