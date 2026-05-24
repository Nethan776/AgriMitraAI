from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

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

━━━ અગત્યના નિયમ ━━━
• ખેડૂત કયો પાક ઉગાડે છે તે ક્યારેય ન પૂછો.
• નામ, ગામ, તાલુકો ક્યારેય ન પૂછો.
• જો "કપાસ IPM જ્ઞાન" વિભાગ આપ્યો હોય, તેનો ઉપયોગ ચોક્કસ ઉત્તર આપવા કરો.
• ફક્ત ખેડૂતની સમસ્યા સાંભળો અને સીધો ઉપાય આપો.

━━━ લંબાઈ ━━━
• 80 થી 150 શબ્દ.
• જો માહિતી અધૂરી હોય, ફક્ત 1 સ્પષ્ટ પ્રશ્ન પૂછો.
"""


def build_system_prompt(farmer: dict = None, rag_context: str = "", weather: dict = None) -> str:
    prompt = SYSTEM_PROMPT

    # Inject farmer profile
    if farmer:
        name    = farmer.get("name")    or "ખેડૂત"
        village = farmer.get("village") or "અજ્ઞાત"
        taluka  = farmer.get("taluka")  or "અજ્ઞાત"
        prompt += f"""
━━━ ખેડૂત માહિતી ━━━
• નામ: {name}
• ગામ: {village}
• તાલુકો: {taluka}
આ ખેડૂત સાથે વ્યક્તિગત અને આત્મીય રીતે વાત કરો.
"""

    # Inject weather context if available
    if weather:
        from services.weather_service import format_weather_for_prompt
        prompt += format_weather_for_prompt(weather)

    # Inject RAG context if available
    if rag_context:
        prompt += rag_context

    return prompt


def generate_ai_response(user_message: str, history: list = None, farmer: dict = None, weather: dict = None) -> str:
    # Get relevant knowledge from PDF
    try:
        from services.rag_service import get_rag_context
        rag_context = get_rag_context(user_message, history)
    except Exception as e:
        print(f"⚠️  RAG error: {e}")
        rag_context = ""

    messages = [{"role": "system", "content": build_system_prompt(farmer, rag_context, weather)}]

    if history:
        for msg in history:
            messages.append({
                "role":    msg["role"],
                "content": msg["content"]
            })

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b:free",
        messages=messages,
        temperature=0.3,
        max_tokens=500,
    )

    return response.choices[0].message.content.strip()