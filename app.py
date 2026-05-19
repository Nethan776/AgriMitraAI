# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from services.ai_service import generate_ai_response
from services.whatsapp_service import (
    parse_incoming_message,
    send_whatsapp_reply,
    download_whatsapp_media
)
from services.memory_service import (
    get_or_create_farmer,
    get_recent_messages,
    save_message,
    update_last_active,
    is_duplicate_message
)

from dotenv import load_dotenv
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
    """
    Quick local test — bypasses WhatsApp and database entirely.

    curl -X POST http://localhost:8000/chat \
         -H "Content-Type: application/json" \
         -d '{"message": "મારા ટામેટાના પાન પીળા થઈ ગયા છે"}'
    """
    try:
        ai_reply = generate_ai_response(request.message, history=[], farmer=None)
        return {"response": ai_reply}
    except Exception as e:
        print(f"CHAT ERROR: {e}")
        return {"error": str(e)}


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

        # ── DEDUPLICATION ─────────────────────────────────────────────────
        # This is the fix for messages being saved 2-3 times.
        # WhatsApp retries the webhook if it doesn't get a fast 200 OK.
        # We check the unique message_id FIRST, before any DB writes or AI calls.
        if is_duplicate_message(message_id):
            print(f"⚠️  Duplicate ignored: {message_id}")
            return {"status": "ok"}

        print(f"\n📩 [{msg_type}] from {phone}: {text or '(media)'}")

        # ── IMAGE ─────────────────────────────────────────────────────────
        if msg_type == "image":
            if not text:
                await send_whatsapp_reply(
                    phone,
                    "🌾 ફોટો મળ્યો!\n\nકૃપા કરીને ટેક્સ્ટમાં જણાવો — પાકમાં શી સમસ્યા છે?\n"
                    "દા.ત. 'પાન પીળા થઈ ગયા' અથવા 'જીવડાં દેખાય છે'."
                )
                return {"status": "ok"}

        # ── AUDIO / VOICE NOTE ────────────────────────────────────────────
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

        # Guard: empty text — nothing useful to send AI
        if not text or not text.strip():
            await send_whatsapp_reply(
                phone,
                "નમસ્તે! 🌾 તમારી ખેતી સમસ્યા ટેક્સ્ટમાં લખો — હું મદદ કરીશ."
            )
            return {"status": "ok"}

        # ── LOAD FARMER CONTEXT ───────────────────────────────────────────
        farmer  = get_or_create_farmer(phone)
        history = get_recent_messages(farmer["id"], limit=5)
        update_last_active(farmer["id"])

        # ── GENERATE AI RESPONSE ──────────────────────────────────────────
        reply = generate_ai_response(
            user_message=text,
            history=history,
            farmer=farmer
        )

        # ── SAVE TO DATABASE ──────────────────────────────────────────────
        save_message(farmer["id"], "user",      text,  whatsapp_message_id=message_id)
        save_message(farmer["id"], "assistant", reply)

        # ── SEND REPLY ────────────────────────────────────────────────────
        await send_whatsapp_reply(phone, reply)

        return {"status": "ok"}

    except Exception as e:
        print(f"\n❌ WEBHOOK ERROR: {e}\n")
        return {"status": "ok"}   # Always 200 to WhatsApp


# ─────────────────────────────────────────────
# Whisper Voice Transcription (optional)
# ─────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes) -> str | None:
    """
    Requires: pip install openai-whisper + ffmpeg on system.
    Returns None gracefully if not installed.
    """
    try:
        import whisper, tempfile

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        result = whisper.load_model("base").transcribe(tmp_path, language="gu")
        return result.get("text", "").strip() or None

    except ImportError:
        return None
    except Exception as e:
        print(f"❌ Whisper error: {e}")
        return None


# uvicorn app:app --reload
