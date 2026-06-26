# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import os

from services.ai_service import (
    generate_ai_response,
    generate_image_diagnosis,
    transcribe_audio,
)
from services.whatsapp_service import (
    parse_incoming_message,
    send_whatsapp_reply,
    send_typing,
    mark_as_read,
    download_whatsapp_media,
    download_whatsapp_media_base64,
)
from services.memory_service import (
    get_or_create_farmer,
    get_recent_messages,
    update_farmer_details,
    save_message,
    update_last_active,
    is_duplicate_message,
)
from services.weather_service import (
    fetch_weather,
    format_weather_for_farmer,
    is_weather_query,
)

load_dotenv()

app = FastAPI()

# ─────────────────────────────────────────────
# Welcome message — sent when farmer says hi/hello
# Scraps onboarding entirely. Farmer goes straight
# to AI flow on every message including the first.
# ─────────────────────────────────────────────

def get_welcome_message(farmer_name: str | None = None) -> str:
    """
    Returns a personalized welcome message.
    """

    if farmer_name:
        greeting = f"🌾 *નમસ્તે {farmer_name}!* 👋\n\n"
    else:
        greeting = "🌾 *નમસ્તે!* 👋\n\n"

    return (
        greeting +

        "કૃષિ મિત્રમાં આપનું સ્વાગત છે. 🙏\n\n"

        "હું *AgriMitra* — તમારો ડિજિટલ ખેતી સહાયક.\n"
        "ગુજરાતીમાં 24×7 ખેતી સંબંધિત માર્ગદર્શન આપવા માટે તૈયાર છું.\n\n"

        "📌 *હું તમને આ બાબતોમાં મદદ કરી શકું છું:*\n\n"

        "📷 પાક, પાન, જીવાત અથવા રોગનો ફોટો\n"
        "🎤 અવાજમાં પૂછેલા પ્રશ્નો\n"
        "💬 કોઈપણ ખેતી સંબંધિત પ્રશ્ન\n"
        "🌦️ આજનું હવામાન અને વરસાદની માહિતી\n"
        "🌿 ખાતર અથવા દવાના પેકેટનો ફોટો\n"
        "🚁 ડ્રોન સ્પ્રે સંબંધિત માર્ગદર્શન\n\n"

        "💡 *જેટલી વધુ માહિતી અથવા સ્પષ્ટ ફોટો મોકલશો,"
        " તેટલી વધુ ચોક્કસ સલાહ આપી શકીશ.*\n\n"

        "👇 હવે તમારો પ્રશ્ન મોકલો."
    )


# Words that trigger the welcome message
GREETING_WORDS = {
    "hi",
    "hello",
    "hey",
    "helo",
    "hii",
    "hiii",
    "namaste",
    "નમસ્તે",
    "નમસ્કાર",
    "જય",
    "જય શ્રી કૃષ્ણ",
    "kem cho",
    "કેમ છો",
    "કેમ",
    "start",
    "શરૂ",
    "help",
    "મદદ",
    "info",
}


def _is_greeting(text: str)  -> bool :
    """
    Returns True if the incoming message
    is simply a greeting/help request.
    """
    if not text:
        return False

    cleaned = text.strip().lower()

    if cleaned in GREETING_WORDS:
        return True

    words = cleaned.split()

    return (
        len(words) <= 3
        and words[0] in GREETING_WORDS
    )


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {
        "status": "running",
        "app":    "AgriMitra 🌾"
    }


@app.get("/privacy")
async def privacy():
    return HTMLResponse("""
    <h1>Privacy Policy</h1>
    <p>AgriMitra AI collects WhatsApp messages and phone numbers solely
    to provide agricultural assistance. User data is not sold or shared
    with third parties. Conversation data may be stored to improve
    response quality and provide conversational context.</p>
    <p>For questions, contact: your@email.com</p>
    """)


# ─────────────────────────────────────────────
# OpenWA Webhook — single entry point
# ─────────────────────────────────────────────

@app.post("/openwa-webhook")
async def openwa_webhook(request: Request):
    try:
        payload    = await request.json()
        parsed     = parse_incoming_message(payload)

        if not parsed:
            return {"status": "ok"}

        phone      = parsed["phone"]
        msg_type   = parsed["type"]
        text       = parsed["text"]
        media      = parsed["media_id"]
        message_id = parsed["message_id"]
        session_id = payload.get("sessionId")

        print(f"\n📩 [{msg_type}] from {phone}: {text or '(media)'}")

        # ── FARMER LOAD ───────────────────────────────────────────────────
        farmer, _ = get_or_create_farmer(phone)

        # Auto-save name from OpenWA contact info if available
        contact     = payload.get("data", {}).get("contact", {})
        farmer_name = contact.get("pushName") or contact.get("name")
        if farmer_name and farmer.get("name") != farmer_name:
            update_farmer_details(farmer["id"], {"name": farmer_name})
            farmer["name"] = farmer_name
            print(f"✅ Saved farmer name from contact: {farmer_name}")

        update_last_active(farmer["id"])

        # ── DEDUPLICATION ─────────────────────────────────────────────────
        if is_duplicate_message(farmer["id"], message_id):
            print(f"⚠️  Duplicate ignored: {message_id}")
            return {"status": "ok"}

        # ── MARK AS READ ──────────────────────────────────────────────────
        await mark_as_read(message_id, session_id=session_id)

        # ── GREETING — welcome + feature info, then continue to AI ───────
        # Triggered by hi/hello/નમસ્તે etc. on ANY message (not just first).
        # After sending welcome, we let the message fall through to the
        # normal AI flow so the farmer gets a real response too if they
        # asked something alongside the greeting.
        # Exception: if it's ONLY a greeting with nothing else, we stop
        # after sending the welcome (no point running AI on "hi").
        if _is_greeting(text) and len(text.split()) <= 3:
            save_message(farmer["id"], "user",      text, whatsapp_message_id=message_id)
            welcome = get_welcome_message(farmer.get("name"))
            save_message(farmer["id"], "assistant", welcome)
            await send_whatsapp_reply(
                phone,
                welcome,
                session_id=session_id
)
            return {"status": "ok"}

        # ── IMAGE — vision model diagnosis ────────────────────────────────
        if msg_type == "image":
            if not media:
                await send_whatsapp_reply(
                    phone,
                    "🌾 ફોટો મળ્યો, પણ ડાઉનલોડ ન થઈ શક્યો. કૃપા કરીને ફરી મોકલો.",
                    session_id=session_id
                )
                return {"status": "ok"}

            print("📷 Downloading image for diagnosis...")
            image_base64 = await download_whatsapp_media_base64(media)

            if not image_base64:
                await send_whatsapp_reply(
                    phone,
                    "🌾 ફોટો ડાઉનલોડ ન થઈ શક્યો. ફરી મોકલો અથવા સમસ્યા ટેક્સ્ટમાં લખો.",
                    session_id=session_id
                )
                return {"status": "ok"}

            await send_typing(phone, session_id=session_id)

            diagnosis = generate_image_diagnosis(
                image_base64=image_base64,
                caption=text,
                farmer=farmer
            )

            save_message(farmer["id"], "user",      text or "(ફોટો)", whatsapp_message_id=message_id)
            save_message(farmer["id"], "assistant", diagnosis)
            await send_whatsapp_reply(phone, diagnosis, session_id=session_id)
            return {"status": "ok"}

        # ── VOICE NOTE — transcribe then continue to AI ───────────────────
        if msg_type == "audio" and media:
            print("🎤 Downloading voice note...")
            audio_bytes = await download_whatsapp_media(media)

            if audio_bytes:
                transcribed = transcribe_audio(audio_bytes)
                if transcribed:
                    text = transcribed
                    print(f"📝 Transcribed: {text}")
                else:
                    await send_whatsapp_reply(
                        phone,
                        "અત્યારે અવાજ સમજવામાં તકલીફ થઈ.\nકૃપા કરીને ટેક્સ્ટમાં લખો 🙏",
                        session_id=session_id
                    )
                    return {"status": "ok"}
            else:
                await send_whatsapp_reply(
                    phone,
                    "અવાજ સંદેશ ડાઉનલોડ ન થઈ શક્યો. ફરી પ્રયાસ કરો.",
                    session_id=session_id
                )
                return {"status": "ok"}

        # ── EMPTY / UNSUPPORTED (sticker, reaction, location etc.) ────────
        if not text or not text.strip():
            await send_whatsapp_reply(
                phone,
                "🌾 ટેક્સ્ટ, ફોટો, કે અવાજ સંદેશ મોકલો — હું મદદ કરીશ.",
                session_id=session_id
            )
            return {"status": "ok"}

        # ── WEATHER DIRECT QUERY ──────────────────────────────────────────
        taluka  = farmer.get("taluka") or farmer.get("village") or "Bharuch"
        weather = await fetch_weather(taluka)

        if is_weather_query(text):
            weather_reply = format_weather_for_farmer(weather)
            save_message(farmer["id"], "user",      text,          whatsapp_message_id=message_id)
            save_message(farmer["id"], "assistant", weather_reply)
            await send_whatsapp_reply(phone, weather_reply, session_id=session_id)
            return {"status": "ok"}

        # ── AI RESPONSE ───────────────────────────────────────────────────
        history = get_recent_messages(farmer["id"], limit=5)
        await send_typing(phone, session_id=session_id)

        reply = generate_ai_response(
            user_message=text,
            history=history,
            farmer=farmer,
            weather=weather
        )

        save_message(farmer["id"], "user",      text,  whatsapp_message_id=message_id)
        save_message(farmer["id"], "assistant", reply)
        await send_whatsapp_reply(phone, reply, session_id=session_id)
        return {"status": "ok"}

    except Exception as e:
        print(f"\n❌ WEBHOOK ERROR: {e}\n")
        return {"status": "ok"}


# uvicorn app:app --reload