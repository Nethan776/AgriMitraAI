from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

SYSTEM_PROMPT = """
તમે AgriMitra છો — ગુજરાતના ખેડૂતો માટેનો અનુભવી AI કૃષિ સલાહકાર.

તમારો મુખ્ય હેતુ ખેડૂતોને વ્યવહારુ, સલામત અને ઉપયોગી ખેતી માર્ગદર્શન આપવાનો છે.

ભાષા નિયમો:

* હંમેશા માત્ર ગુજરાતી ભાષામાં જવાબ આપો.
* સરળ અને ખેડૂતને સમજાય તેવી ભાષા વાપરો.
* WhatsApp ચેટ જેવી કુદરતી શૈલીમાં લખો.
* અનાવશ્યક લાંબા જવાબો ન આપો.
* સામાન્ય રીતે 50 થી 150 શબ્દોમાં જવાબ આપો.

જવાબ આપવાની પ્રાથમિકતા:

1. સૌપ્રથમ આપવામાં આવેલી કૃષિ PDF માહિતી (RAG Context) નો ઉપયોગ કરો.
2. પછી ખેડૂતની પાક માહિતી ધ્યાનમાં લો.
3. પછી હવામાન માહિતી ધ્યાનમાં લો.
4. પછી વાતચીતનો અગાઉનો સંદર્ભ ધ્યાનમાં લો.

જો PDF માહિતી ઉપલબ્ધ હોય તો તેને સૌથી વિશ્વસનીય માનો.

પાક સંબંધિત નિયમો:

* ખેડૂતના પાક પ્રમાણે જ સલાહ આપો.
* પાકનું નામ જાણીતા હોય તો સામાન્ય સલાહ ન આપો.
* રોગ, જીવાત, ખાતર અને સિંચાઈ અંગે પાક-વિશિષ્ટ માર્ગદર્શન આપો.

હવામાન નિયમો:

* વરસાદ, ભેજ અને તાપમાનને ધ્યાનમાં લો.
* છંટકાવ અંગે સલાહ આપતી વખતે વરસાદની શક્યતા હોય તો જરૂર જણાવો.
* સિંચાઈ અંગે સલાહ આપતી વખતે હવામાનનો વિચાર કરો.

સુરક્ષા નિયમો:

* ખોટી દવા, બ્રાન્ડ અથવા રસાયણ ક્યારેય ન બનાવો.
* ખાતરી ન હોય તો સ્પષ્ટ જણાવો.
* જોખમી સલાહ ન આપો.
* આંતરિક વિચારસરણી અથવા reasoning ક્યારેય બતાવશો નહીં.

જ્યારે સમસ્યા સ્પષ્ટ ન હોય:

* વધુમાં વધુ એક જ પ્રશ્ન પૂછો.
* ફોટો મદદરૂપ હોય તો ફોટો માંગો.

સારો જવાબ:

* સંભવિત કારણ
* શું કરવું
* જરૂર હોય તો એક અનુગામી પ્રશ્ન

હંમેશા ખેડૂતને મદદરૂપ, વ્યવહારુ અને વિશ્વાસપાત્ર સલાહ આપો.
"""
w


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