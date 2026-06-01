# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from services.ai_service import generate_ai_response
from services.whatsapp_service import (
    parse_incoming_message,
    send_whatsapp_reply,
    send_typing,
    mark_as_read,
    download_whatsapp_media
)
from services.memory_service import (
    get_or_create_farmer,
    get_recent_messages,
    save_message,
    update_last_active,
    update_farmer_details,
    is_duplicate_message,
    is_onboarding_complete
)

from dotenv import load_dotenv
from services.weather_service import fetch_weather, format_weather_for_farmer, format_weather_for_prompt, is_weather_query
import os

load_dotenv()

app = FastAPI()


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {
        "status": "running",
        "app":    "Gujarati Farm AI Assistant 🌾"
    }


# ─────────────────────────────────────────────
# Local Test Endpoint (no WhatsApp, no DB)
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        ai_reply = generate_ai_response(request.message, history=[], farmer=None)
        return {"response": ai_reply}
    except Exception as e:
        print(f"CHAT ERROR: {e}")
        return {"error": str(e)}

@app.get("/privacy")
async def privacy():
    return HTMLResponse("""
    <h1>Privacy Policy</h1>
    <p>AgriMitra AI collects WhatsApp messages and phone numbers solely to provide agricultural assistance. User data is not sold or shared with third parties. Conversation data may be stored to improve response quality and provide conversational context.</p>
    <p>For questions, contact: your@email.com</p>
    """)
# ─────────────────────────────────────────────
# WhatsApp Webhook — Verification (GET)
# ─────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(
    hub_mode:         str = Query(alias="hub.mode",         default=None),
    hub_challenge:    str = Query(alias="hub.challenge",    default=None),
    hub_verify_token: str = Query(alias="hub.verify_token", default=None)
):
    if hub_verify_token == os.getenv("WEBHOOK_VERIFY_TOKEN"):
        print("✅ Webhook verified by Meta")
        return PlainTextResponse(hub_challenge)

    print("❌ Webhook verification failed")
    return PlainTextResponse("Forbidden", status_code=403)


# ─────────────────────────────────────────────
# Onboarding Handler
# Returns True if onboarding just completed this message
# Returns False if still in progress
# ─────────────────────────────────────────────

async def handle_onboarding(farmer: dict, text: str, phone: str, message_id: str) -> bool:
    """
    Handles one onboarding step per call.
    Returns True if onboarding just finished (taluka step done).
    Returns False if still collecting details.
    """
    step = farmer.get("onboarding_step", "ask_name")
    text = text.strip()

    # ── Step 1: received name, ask village ──
    if step == "ask_name":
        update_farmer_details(farmer["id"], {
            "name":            text,
            "onboarding_step": "ask_village"
        })
        save_message(farmer["id"], "user",      text, whatsapp_message_id=message_id)
        save_message(farmer["id"], "assistant", "તમારું ગામ કયું છે?")
        await send_whatsapp_reply(phone, "તમારું ગામ કયું છે?")
        return False

    # ── Step 2: received village, ask taluka ──
    elif step == "ask_village":
        update_farmer_details(farmer["id"], {
            "village":         text,
            "onboarding_step": "ask_taluka"
        })
        save_message(farmer["id"], "user",      text, whatsapp_message_id=message_id)
        save_message(farmer["id"], "assistant", "તમારો તાલુકો કયો છે?")
        await send_whatsapp_reply(phone, "તમારો તાલુકો કયો છે?")
        return False

    # ── Step 3: received taluka — onboarding complete ──
    elif step == "ask_taluka":
        update_farmer_details(farmer["id"], {
            "taluka":          text,
            "onboarding_step": "done"
        })
        save_message(farmer["id"], "user", text, whatsapp_message_id=message_id)

        name = farmer.get("name", "ખેડૂત")
        welcome = (
            f"આવકારો, {name}ભાઈ! 🌾\n\n"
            "હું કૃષિ મિત્ર છું — તમારો AI ખેતી સહાયક.\n\n"
            "હવે તમારી ખેતી સમસ્યા જણાવો — હું મદદ કરીશ! 🙏"
        )
        save_message(farmer["id"], "assistant", welcome)
        await send_whatsapp_reply(phone, welcome)
        return True   # ← onboarding just finished, do NOT run AI after this

    return False


# ─────────────────────────────────────────────
# WhatsApp Webhook — Incoming Messages (POST)
# ─────────────────────────────────────────────

@app.post("/webhook")
async def receive_message(request: Request):
    """
    All farmer messages arrive here from WhatsApp Cloud API.
    Always returns 200 OK — never let exceptions bubble up or
    WhatsApp will retry endlessly and cause more duplicates.
    """
    try:
        body   = await request.json()
        parsed = parse_incoming_message(body)

        if not parsed:
            return {"status": "ok"}

        phone      = parsed["phone"]
        msg_type   = parsed["type"]
        text       = parsed["text"]
        media_id   = parsed["media_id"]
        message_id = parsed["message_id"]

        print(f"\n📩 [{msg_type}] from {phone}: {text or '(media)'}")

        # ── GET OR CREATE FARMER ──────────────────────────────────────────
        # Must load farmer first so deduplication is scoped per farmer.
        # Two different farmers can have the same WhatsApp message ID.
        farmer, is_new = get_or_create_farmer(phone)
        update_last_active(farmer["id"])

        # ── DEDUPLICATION (per farmer) ────────────────────────────────────
        if is_duplicate_message(farmer["id"], message_id):
            print(f"⚠️  Duplicate ignored: {message_id}")
            return {"status": "ok"}

        # ── MARK AS READ (blue ticks) ─────────────────────────────────────
        await mark_as_read(message_id)

        # ── BRAND NEW FARMER — send greeting, ask for name ────────────────
        if is_new:
            save_message(farmer["id"], "user", text or "(media)", whatsapp_message_id=message_id)
            greeting = (
                "નમસ્તે! 🌾 કૃષિ મિત્રમાં આપનું સ્વાગત છે!\n\n"
                "શરૂ કરતાં પહેલાં થોડી માહિતી આપો.\n\n"
                "તમારું નામ શું છે?"
            )
            save_message(farmer["id"], "assistant", greeting)
            await send_whatsapp_reply(phone, greeting)
            return {"status": "ok"}

        # ── ONBOARDING IN PROGRESS ────────────────────────────────────────
        if not is_onboarding_complete(farmer):
            just_finished = await handle_onboarding(farmer, text, phone, message_id)
            # Whether still in progress or just finished — stop here.
            # Never fall through to AI during or right after onboarding.
            return {"status": "ok"}

        # ── NORMAL FLOW — onboarding done ─────────────────────────────────

        # Handle image with no caption
        if msg_type == "image":
            if not text:
                await send_whatsapp_reply(
                    phone,
                    "🌾 ફોટો મળ્યો!\n\nકૃપા કરીને ટેક્સ્ટમાં જણાવો — પાકમાં શી સમસ્યા છે?\n"
                    "દા.ત. 'પાન પીળા થઈ ગયા' અથવા 'જીવડાં દેખાય છે'."
                )
                return {"status": "ok"}

        # Handle voice note
        elif msg_type == "audio" and media_id:
            print("🎤 Downloading voice note...")
            audio_bytes = await download_whatsapp_media(media_id)

            if audio_bytes:
                transcribed = transcribe_audio(audio_bytes)
                if transcribed:
                    text = transcribed
                    print(f"📝 Transcribed: {text}")
                else:
                    await send_whatsapp_reply(
                        phone,
                        "🎤 અવાજ સંદેશ મળ્યો!\n\n"
                        "અત્યારે અવાજ સમજવાની સુવિધા ઉપલબ્ધ નથી.\n"
                        "કૃપા કરીને ટેક્સ્ટ (ટાઇપ) માં સમસ્યા જણાવો."
                    )
                    return {"status": "ok"}
            else:
                await send_whatsapp_reply(phone, "અવાજ સંદેશ ડાઉનલોડ ન થઈ શક્યો. ફરી પ્રયાસ કરો.")
                return {"status": "ok"}

        # Guard: empty text
        if not text or not text.strip():
            await send_whatsapp_reply(
                phone,
                "નમસ્તે! 🌾 તમારી ખેતી સમસ્યા ટેક્સ્ટમાં લખો — હું મદદ કરીશ."
            )
            return {"status": "ok"}

        # ── FETCH WEATHER FOR FARMER'S TALUKA ────────────────────────────
        taluka  = farmer.get("taluka") or farmer.get("village") or "Bharuch"
        weather = await fetch_weather(taluka)

        # If farmer is directly asking about weather — reply and stop
        if is_weather_query(text):
            weather_reply = format_weather_for_farmer(weather)
            save_message(farmer["id"], "user",      text,         whatsapp_message_id=message_id)
            save_message(farmer["id"], "assistant", weather_reply)
            await send_whatsapp_reply(phone, weather_reply)
            return {"status": "ok"}

        # ── LOAD HISTORY + GENERATE AI RESPONSE ──────────────────────────
        history = get_recent_messages(farmer["id"], limit=5)

        # Show typing indicator while AI is thinking
        await send_typing(phone)

        reply = generate_ai_response(
            user_message=text,
            history=history,
            farmer=farmer,
            weather=weather
        )

        # ── SAVE + SEND ───────────────────────────────────────────────────
        save_message(farmer["id"], "user",      text,  whatsapp_message_id=message_id)
        save_message(farmer["id"], "assistant", reply)
        await send_whatsapp_reply(phone, reply)

        return {"status": "ok"}

    except Exception as e:
        print(f"\n❌ WEBHOOK ERROR: {e}\n")
        return {"status": "ok"}


# ─────────────────────────────────────────────
# Voice Transcription via Groq Whisper API
# ─────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes) -> str | None:
    try:
        from groq import Groq
        import tempfile

        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        with open(tmp_path, "rb") as audio_file:
            result = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                language="gu",
                response_format="text"
            )

        os.unlink(tmp_path)

        transcription = result.strip() if isinstance(result, str) else str(result).strip()
        print(f"📝 Groq transcription: {transcription}")
        return transcription or None

    except Exception as e:
        print(f"❌ Groq transcription error: {e}")
        return None


# uvicorn app:app --reload