# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from services.ai_service import generate_ai_response
from services.whatsapp_service import (
    parse_incoming_message,
    send_whatsapp_reply
)
from services.memory_service import (
    get_or_create_farmer,
    get_recent_messages,
    save_message
)
from dotenv import load_dotenv
import traceback
import os
import json

load_dotenv()

app = FastAPI()


# =========================
# Request Schema
# =========================

class ChatRequest(BaseModel):
    message: str


# =========================
# Normal Chat Endpoint
# =========================

@app.post("/chat")
async def chat(request: ChatRequest):

    try:

        ai_reply = generate_ai_response(
            request.message,
            []
        )

        return {
            "response": ai_reply
        }

    except Exception as e:

        print("\nCHAT ERROR:\n")
        print(str(e))

        return {
            "error": str(e)
        }


# =========================
# WhatsApp Webhook Verify
# =========================

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token")
):

    if hub_verify_token == os.getenv("WEBHOOK_VERIFY_TOKEN"):

        print("\nWEBHOOK VERIFIED\n")

        return PlainTextResponse(hub_challenge)

    return PlainTextResponse(
        "Forbidden",
        status_code=403
    )


# =========================
# WhatsApp Message Receiver
# =========================
@app.post("/webhook")
async def receive_message(request: Request):

    try:

        body = await request.json()

        parsed = parse_incoming_message(body)

        if not parsed:
            return {"status": "ok"}

        phone = parsed["phone"]

        # Get/Create farmer
        farmer = get_or_create_farmer(phone)

        # Load memory
        history = get_recent_messages(
            farmer["id"],
            limit=5
        )

        # Generate AI response
        reply = generate_ai_response(
            user_message=parsed["text"],
            history=history,
            farmer=farmer
        )

        # Save user message
        save_message(
            farmer["id"],
            "user",
            parsed["text"]
        )

        # Save AI reply
        save_message(
            farmer["id"],
            "assistant",
            reply
        )

        # Send WhatsApp reply
        await send_whatsapp_reply(
            phone,
            reply
        )

        return {"status": "ok"}

    except Exception as e:
        print("\nWEBHOOK ERROR:\n")
        traceback.print_exc()