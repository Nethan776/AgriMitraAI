from openai import OpenAI
from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
- If multiple causes possible, give top 2 likely causes only.


Very important:
- NEVER invent fake medicines, pesticides, brands, or chemicals.
- NEVER give highly specific dosage or chemical measurements unless very certain.
- NEVER give risky or dangerous farming advice.
- If uncertain, clearly say the issue may need local agricultural inspection.
- Never reveal internal reasoning, analysis, or thinking steps.
- Never output English planning text or instructions.
- Responce must be under 80 words.

Good example:
"કપાસનાં પાન પીળા થવાનું કારણ પાણીની કમી અથવા ખાતરની અછત હોઈ શકે 🌿

જમીન બહુ સુકી લાગે તો નિયમિત પાણી આપો. જો પાનની નીચે સફેદ જીવાત દેખાય તો નીમ આધારિત દવા મદદરૂપ થઈ શકે.

ફોટો મોકલો તો વધુ સારી રીતે સમજાઈ શકે 📷"
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
            model="gpt-5-mini",
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
    model="gpt-5-mini",
    messages=messages,
    temperature=0.3,
    max_completion_tokens=500,
)

    return response.choices[0].message.content.strip()