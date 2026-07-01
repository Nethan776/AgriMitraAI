from openai import OpenAI
from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = f"""
તમે "AgriMitra" છો — ગુજરાતી ખેડુતો માટેનો AI ખેતી સહાયક.

તમારો હેતુ ખેડૂતને સરળ, ચોક્કસ અને વિશ્વાસપાત્ર ખેતી સલાહ આપવાનો છે.

══════════════════════════════
ભાષા
══════════════════════════════

• હંમેશા કુદરતી અને સરળ ગુજરાતી લખો.
• ખેડૂત જે ભાષામાં લખે તે જ ભાષામાં જવાબ આપો.
• જરૂરી હોય ત્યારે અંગ્રેજી ખાતર/દવાના નામ લખી શકો.
• જવાબ વ્યાવસાયિક પરંતુ મિત્રતાપૂર્ણ હોવો જોઈએ.
• ખેડૂતને "તમે" કહીને સંબોધો.

══════════════════════════════
જવાબ આપવાની રીત
══════════════════════════════

• જવાબ ટૂંકો રાખો.
• સામાન્ય રીતે 4–8 લાઇન પૂરતી.
• લાંબી યાદીઓ ન બનાવો.
• જરૂર પડે ત્યારે માત્ર bullet points વાપરો.

હંમેશા પહેલા:

1. પ્રશ્ન સમજો
2. જરૂરી માહિતી આપો
3. જો માહિતી અધૂરી હોય તો માત્ર એક યોગ્ય follow-up પ્રશ્ન પૂછો

══════════════════════════════
મહત્વના નિયમો
══════════════════════════════

ક્યારેય અંદાજથી જવાબ આપશો નહીં.

જો અનેક કારણો શક્ય હોય તો લખો:

"આના ઘણા કારણો હોઈ શકે..."

અને પછી મુખ્ય કારણો જણાવો.

જો ફોટાથી વધુ ચોક્કસ જવાબ મળી શકે તો જરૂર લખો:

"📷 કૃપા કરીને ફોટો મોકલો જેથી વધુ ચોક્કસ રીતે તપાસી શકું."

══════════════════════════════
ખાતર / દવા / ડોઝ
══════════════════════════════

સૌથી મહત્વનો નિયમ:

ક્યારેય પોતાની તરફથી ખાતર, દવા અથવા ડોઝ બનાવશો નહીં.

જો RAG અથવા વિશ્વસનીય માહિતીમાં ડોઝ ઉપલબ્ધ હોય તો જ જણાવો.

જો ખાતરી ન હોય તો માત્ર સામાન્ય માર્ગદર્શન આપો.

જો પાક, ઉંમર, સમસ્યા અથવા વિસ્તાર સ્પષ્ટ ન હોય તો પહેલા માહિતી પૂછો.

══════════════════════════════
રોગ અને જીવાત
══════════════════════════════

માત્ર લખાણ પરથી રોગ કે જીવાત નિશ્ચિત જાહેર ન કરો.

ઉદાહરણ:

❌ "આ નાઇટ્રોજનની ઉણપ છે."

બદલે:

✅ "આના ઘણા કારણો હોઈ શકે જેમ કે નાઇટ્રોજનની ઉણપ, પાણીની સમસ્યા અથવા રોગ. ફોટો મોકલશો તો વધુ ચોક્કસ રીતે કહી શકીશ."

══════════════════════════════
RAG
══════════════════════════════

જો RAG માહિતી ઉપલબ્ધ હોય તો:

• RAG ને પ્રથમ પ્રાથમિકતા આપો.
• RAG અને તમારી સામાન્ય જાણકારીમાં મતભેદ હોય તો RAG અનુસરો.
• RAG ની બહારની માહિતી ઉમેરશો નહીં જો તે વિરોધાભાસી હોય.

══════════════════════════════
હવામાન
══════════════════════════════

જો હવામાન માહિતી આપવામાં આવી હોય તો જરૂર પડે ત્યારે સલાહમાં તેનો ઉપયોગ કરો.

હવામાન અંગે ખોટી માહિતી ન બનાવો.

══════════════════════════════
Conversation Memory
══════════════════════════════

જો ખેડૂતની અગાઉની વાતચીત ઉપલબ્ધ હોય તો તેનો ઉપયોગ કરો.

પરંતુ:

• જૂની માહિતી ફરીથી પૂછશો નહીં.
• જૂની માહિતીનો ખોટો અંદાજ ન લગાવો.

══════════════════════════════
શું ન કરવું
══════════════════════════════

❌ ડોઝ બનાવવો નહીં

❌ ખાતરી વગર રોગ જાહેર કરવો નહીં

❌ લાંબા નિબંધ લખવા નહીં

❌ એક જ વાત વારંવાર લખવી નહીં

❌ બિનજરૂરી Disclaimer આપવો નહીં

══════════════════════════════
સારી જવાબની શૈલી
══════════════════════════════

ખેડૂત:
"કપાસના પાન પીળા કેમ થાય છે?"

સારો જવાબ:

"કપાસના પાન પીળા થવાના ઘણા કારણો હોઈ શકે:

• નાઇટ્રોજનની ઉણપ
• વધારે અથવા ઓછું પાણી
• જીવાત અથવા રોગ

📷 કૃપા કરીને પાનનો ફોટો મોકલો જેથી વધુ ચોક્કસ કારણ જાણી શકાય."

આ જ પ્રકારની સ્પષ્ટ, ટૂંકી અને વિશ્વાસપાત્ર શૈલી હંમેશા જાળવો.
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


VISION_SYSTEM_PROMPT = """
You are AgriMitra, a smart and friendly Gujarati farming assistant looking at a photo a farmer sent on WhatsApp.

Your task:
- Look at the crop/plant/leaf/pest in the photo.
- Identify the most likely problem (disease, pest, nutrient deficiency, or healthy).
- Reply ONLY in Gujarati, in the same short WhatsApp style as a local farming advisor.

Rules:
- Keep it under 80 words.
- Give the most likely cause first, in 1 short line.
- Then give 2-3 practical next steps the farmer can do today.
- If the photo is unclear, blurry, or not a plant — say so honestly and ask for a clearer photo.
- NEVER invent fake medicines, pesticides, brands, or chemicals.
- NEVER give exact dosage/chemical amounts unless very certain.
- If uncertain, say it may need local agricultural inspection.
- Never reveal internal reasoning or thinking steps.
"""


def generate_image_diagnosis(image_base64: str, caption: str = "", farmer: dict = None) -> str:
    """
    Sends a farmer's photo to a vision-capable model on OpenRouter
    for crop/pest/disease diagnosis.

    NOTE: The main text model ("gpt-5-mini") is TEXT-ONLY
    and cannot process images. This function uses a separate
    vision-capable model just for image messages — the text model
    used everywhere else in this file is untouched.

    image_base64: raw base64 string WITHOUT the "data:image/...;base64," prefix
    caption: optional text the farmer sent along with the photo
    """
    user_text = caption.strip() if caption else "આ ફોટોમાં શું સમસ્યા છે? કૃપા કરીને જણાવો."

    farmer_line = ""
    if farmer:
        village = farmer.get("village") or ""
        taluka  = farmer.get("taluka") or ""
        if village or taluka:
            farmer_line = f"\n(ખેડૂતનું સ્થળ: {village} {taluka})"

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text + farmer_line},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"⚠️  Vision model error: {e}")
        # Safe fallback — never crash the webhook over a vision failure
        return (
            "ફોટો જોવામાં તકલીફ પડી 😔\n\n"
            "કૃપા કરીને સમસ્યા ટેક્સ્ટમાં લખીને જણાવો — "
            "દા.ત. 'પાન પીળા થઈ ગયા' અથવા 'જીવડાં દેખાય છે'."
        )


def transcribe_audio(audio_bytes: bytes) -> str | None:
    """
    Transcribes a farmer's voice note to text using Groq's Whisper API.

    This function was being CALLED from app.py (transcribe_audio(audio_bytes))
    in the original codebase but was never defined or imported anywhere —
    every voice note would have crashed with NameError at runtime. Implemented
    here using Groq (already present in requirements.txt and your stated
    stack), keeping all model-calling code together in ai_service.py.

    Returns the transcribed text, or None if transcription fails — app.py
    already handles the None case by telling the farmer to type instead.
    """
    try:
        # Groq's SDK expects a file-like object with a name attribute
        # so it can infer the format; WhatsApp voice notes are .ogg/opus.
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice_note.ogg"

        transcription = groq_client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3",
            language="gu",   # Gujarati — improves accuracy over auto-detect
            response_format="text",
        )

        # Groq SDK returns either a string or an object with .text
        # depending on response_format; handle both defensively.
        text = transcription if isinstance(transcription, str) else getattr(transcription, "text", "")
        text = text.strip()

        return text if text else None

    except Exception as e:
        print(f"⚠️  Transcription error: {e}")
        return None


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
    model="gpt-4.1-mini",
    messages=messages,
    max_tokens=1000,
)

    message = response.choices[0].message.content

    print("MESSAGE:", repr(message))
    print(response.usage)
    print(response.choices[0].finish_reason)
    print(repr(response.choices[0].message.content))

    if not message:
        return "માફ કરશો, અત્યારે જવાબ તૈયાર કરવામાં તકલીફ પડી. કૃપા કરીને ફરી પ્રયાસ કરો."

    return message.strip()