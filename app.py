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
# Health Check
# ─────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {
        "status": "running",
        "app":    "Gujarati Farm AI Assistant 🌾"
    }


@app.get("/privacy")
async def privacy():
    return HTMLResponse("""
    <h1>Privacy Policy</h1>
    <p>AgriMitra AI collects WhatsApp messages and phone numbers solely to provide agricultural assistance. User data is not sold or shared with third parties. Conversation data may be stored to improve response quality and provide conversational context.</p>
    <p>For questions, contact: your@email.com</p>
    """)


# ─────────────────────────────────────────────
# OpenWA Webhook — the ONLY message entry point
#
# WhatsApp → OpenWA → POST /openwa-webhook → process_farmer_message()
#                                          → generate_ai_response()
#                                          → send_whatsapp_reply()
#                                          → WhatsApp
#
# This single route now carries everything that used to be split
# between the old Meta /webhook (which had all the real logic) and
# the old /openwa-webhook stub (which had none of it). Onboarding has
# been intentionally removed per product decision — every farmer is
# usable immediately on first message.
#
# Always returns 200 OK — never let exceptions bubble up, or OpenWA's
# webhook retry logic (max 3x per its own docs) will redeliver the
# same message and cause duplicates upstream of our own dedup check.
# ─────────────────────────────────────────────

@app.post("/openwa-webhook")
async def openwa_webhook(request: Request):
    try:
        payload = await request.json()
        parsed  = parse_incoming_message(payload)

        if not parsed:
            return {"status": "ok"}

        phone       = parsed["phone"]
        msg_type    = parsed["type"]
        text        = parsed["text"]
        media       = parsed["media_id"]      # dict {url, base64, mimetype} or None, for image/audio/document
        message_id  = parsed["message_id"]
        session_id  = payload.get("sessionId")

        print(f"\n📩 [{msg_type}] from {phone}: {text or '(media)'}")

        # ── GET OR CREATE FARMER ──────────────────────────────────────────
        # Must load farmer first so deduplication is scoped per farmer.
        # Two different farmers can have the same message ID.
        farmer, is_new = get_or_create_farmer(phone)
        update_last_active(farmer["id"])

        # ── DEDUPLICATION (per farmer) ────────────────────────────────────
        if is_duplicate_message(farmer["id"], message_id):
            print(f"⚠️  Duplicate ignored: {message_id}")
            return {"status": "ok"}

        # ── MARK AS READ (blue ticks, best-effort) ────────────────────────
        await mark_as_read(message_id, session_id=session_id)

        # ── BRAND NEW FARMER — short welcome, no onboarding questions ─────
        if is_new:
            greeting = (
                "નમસ્તે! 🌾 કૃષિ મિત્રમાં આપનું સ્વાગત છે!\n\n"
                "તમારી ખેતી સમસ્યા જણાવો, ફોટો મોકલો, અથવા અવાજ સંદેશ મોકલો — "
                "હું મદદ કરીશ! 🙏"
            )
            save_message(farmer["id"], "user",      text or "(media)", whatsapp_message_id=message_id)
            save_message(farmer["id"], "assistant", greeting)
            await send_whatsapp_reply(phone, greeting, session_id=session_id)
            return {"status": "ok"}

        # ── IMAGE — send to vision model for diagnosis ─────────────────────
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
                    "🌾 ફોટો ડાઉનલોડ ન થઈ શક્યો. કૃપા કરીને ફરી મોકલો અથવા "
                    "સમસ્યા ટેક્સ્ટમાં લખો.",
                    session_id=session_id
                )
                return {"status": "ok"}

            await send_typing(phone, session_id=session_id)

            diagnosis = generate_image_diagnosis(
                image_base64=image_base64,
                caption=text,
                farmer=farmer
            )

            save_message(farmer["id"], "user",      text or "(ફોટો મોકલ્યો)", whatsapp_message_id=message_id)
            save_message(farmer["id"], "assistant", diagnosis)
            await send_whatsapp_reply(phone, diagnosis, session_id=session_id)
            return {"status": "ok"}

        # ── VOICE NOTE — transcribe then fall through to normal AI flow ───
        elif msg_type == "audio" and media:
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
                        "અત્યારે અવાજ સમજવાની સુવિધા ઉપલબ્ધ નથી.\n"
                        "કૃપા કરીને ટેક્સ્ટ (ટાઇપ) માં સમસ્યા જણાવો.",
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

        # ── GUARD: empty text (e.g. sticker, reaction with no body) ───────
        if not text or not text.strip():
            await send_whatsapp_reply(
                phone,
                "નમસ્તે! 🌾 તમારી ખેતી સમસ્યા ટેક્સ્ટમાં લખો — હું મદદ કરીશ.",
                session_id=session_id
            )
            return {"status": "ok"}

        # ── WEATHER ────────────────────────────────────────────────────────
        taluka  = farmer.get("taluka") or farmer.get("village") or "Bharuch"
        weather = await fetch_weather(taluka)

        # If farmer is directly asking about weather — reply and stop
        if is_weather_query(text):
            weather_reply = format_weather_for_farmer(weather)
            save_message(farmer["id"], "user",      text,          whatsapp_message_id=message_id)
            save_message(farmer["id"], "assistant", weather_reply)
            await send_whatsapp_reply(phone, weather_reply, session_id=session_id)
            return {"status": "ok"}

        # ── LOAD HISTORY + GENERATE AI RESPONSE ───────────────────────────
        history = get_recent_messages(farmer["id"], limit=5)

        await send_typing(phone, session_id=session_id)

        reply = generate_ai_response(
            user_message=text,
            history=history,
            farmer=farmer,
            weather=weather
        )

        # ── SAVE + SEND ──────────────────────────────────────────────────
        save_message(farmer["id"], "user",      text,  whatsapp_message_id=message_id)
        save_message(farmer["id"], "assistant", reply)
        await send_whatsapp_reply(phone, reply, session_id=session_id)

        return {"status": "ok"}

    except Exception as e:
        print(f"\n❌ OPENWA WEBHOOK ERROR: {e}\n")
        return {"status": "ok"}


# uvicorn app:app --reload