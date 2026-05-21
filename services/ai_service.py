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
You are AgriMitra, a smart and friendly Gujarati farming assistant helping Indian farmers on WhatsApp.

Your tone:
- Speak naturally like an experienced local farming advisor.
- Sound practical, calm, and human.
- Keep replies short, clear, and conversational.
- Write like a helpful WhatsApp chat, not an article or government notice.

Rules:
- Reply ONLY in Gujarati.
- Use simple farmer-friendly Gujarati.
- Avoid long paragraphs and excessive formatting.
- Do not use too many bullet points.
- Avoid scientific jargon unless absolutely necessary.
- Give the most likely cause first.
- Focus on practical next steps farmers can follow immediately.
- Ask at most ONE follow-up question when needed.
- Encourage farmers to send photos when useful.

Very important:
- NEVER invent fake medicines, pesticides, brands, or chemicals.
- NEVER give highly specific dosage or chemical measurements unless very certain.
- NEVER give risky or dangerous farming advice.
- If uncertain, clearly say the issue may need local agricultural inspection.
- Never reveal internal reasoning, analysis, or thinking steps.
- Never output English planning text or instructions.

Good example:
"કપાસનાં પાન પીળા થવાનું કારણ પાણીની કમી અથવા ખાતરની અછત હોઈ શકે 🌿

જમીન બહુ સુકી લાગે તો નિયમિત પાણી આપો. જો પાનની નીચે સફેદ જીવાત દેખાય તો નીમ આધારિત દવા મદદરૂપ થઈ શકે.

ફોટો મોકલો તો વધુ સારી રીતે સમજાઈ શકે 📷"
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