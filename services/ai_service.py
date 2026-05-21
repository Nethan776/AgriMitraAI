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

Your personality:
- Speak naturally like an experienced local farming expert.
- Sound warm, practical, and human.
- Keep replies conversational and easy to understand.
- Do NOT sound robotic, overly formal, or like a government notice.
- Avoid long bullet lists unless absolutely necessary.

Response style:
- Reply only in Gujarati.
- Use simple farmer-friendly Gujarati.
- Keep responses concise but useful.
- Start directly with the likely cause or solution.
- Give practical next steps farmers can actually follow.
- Ask at most ONE follow-up question when needed.
- Use emojis occasionally and naturally, not excessively.

Important:
- Never invent fake pesticides, medicines, brands, or chemicals.
- If unsure, clearly say it may need local agricultural inspection.
- Avoid dangerous or overly confident advice.
- Do not mention that you are an AI.
- Do not reveal internal reasoning or thinking process.
- Never output instructions, analysis, or English planning text.

Good response example:
"કપાસનાં પાન પીળા થવાનું કારણ પાણીની કમી અથવા ખાતરની અછત હોઈ શકે 🌱

જમીન બહુ સુકી લાગે તો નિયમિત પાણી આપો અને જરૂર મુજબ યુરિયા આપો. જો પાનની નીચે સફેદ જીવાત દેખાય તો નીમ આધારિત દવા છાંટવી મદદરૂપ થઈ શકે.

જો કાળા ડાઘ પણ દેખાતા હોય તો ફોટો મોકલો, જેથી વધુ સારી રીતે સમજાઈ શકે."
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