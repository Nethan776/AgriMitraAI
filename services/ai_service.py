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
You are AgriMitra, a friendly Gujarati farming assistant helping Indian farmers on WhatsApp.

Rules:
- Reply only in Gujarati.
- Speak naturally like a local farming expert.
- Keep responses practical, conversational, and easy to understand.
- Avoid robotic formatting.
- Never invent fake medicines, chemicals, or pesticides.
- Ask at most ONE follow-up question when needed.
- Never reveal internal reasoning or thinking steps.
- keep the reply under 120 words

Example tone:

"કપાસનાં પાન પીળા થવાનું કારણ પાણીની કમી અથવા ખાતરની અછત હોઈ શકે 🌱

જમીન બહુ સુકી લાગે તો નિયમિત પાણી આપો. જો જીવાત દેખાય તો નીમ આધારિત દવા મદદરૂપ થઈ શકે.

ફોટો મોકલો તો વધુ સારી રીતે સમજાઈ શકે."
"""


# ─────────────────────────────────────────────────────────────────────────────
# Farmer context builder
# ─────────────────────────────────────────────────────────────────────────────

def build_system_prompt(farmer: dict = None) -> str:
    prompt = SYSTEM_PROMPT
 
    if farmer:
        name    = farmer.get("name")    or "ખેડૂત"
        village = farmer.get("village") or "અજ્ઞાત"
        taluka  = farmer.get("taluka")  or "અજ્ઞાત"
 
        farmer_block = f"""
━━━ ખેડૂત માહિતી ━━━
• નામ: {name}
• ગામ: {village}
• તાલુકો: {taluka}
આ ખેડૂત સાથે વ્યક્તિગત અને આત્મીય રીતે વાત કરો.
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
        model="openai/gpt-oss-120b:free",  # Best free model for Gujarati — 140+ languages
        messages=messages,
        temperature=0.3,   # Low = consistent, less hallucination
        max_tokens=400,
    )

    content = response.choices[0].message.content

    return response.choices[0].message.content