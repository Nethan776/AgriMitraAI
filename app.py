from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dotenv import load_dotenv

from services.ai_service import generate_ai_response
from services.message_processor import process_farmer_message

import os
import requests

load_dotenv()

OPENWA_URL = os.getenv("OPENWA_URL")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY")

app = FastAPI()


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/")
async def health_check():
    return {
        "status": "running",
        "app": "AgriMitra"
    }


# --------------------------------------------------
# Local Testing
# --------------------------------------------------

class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(request: ChatRequest):

    reply = generate_ai_response(
        request.message,
        history=[],
        farmer=None
    )

    return {"response": reply}


# --------------------------------------------------
# OpenWA Sender
# --------------------------------------------------

def send_openwa_reply(
    session_id: str,
    chat_id: str,
    text: str
):
    try:

        url = (
            f"{OPENWA_URL}"
            f"/api/sessions/{session_id}/messages/send-text"
        )

        response = requests.post(
            url,
            headers={
                "X-API-Key": OPENWA_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "chatId": chat_id,
                "text": text
            },
            timeout=30
        )

        print(
            f"OpenWA Send: "
            f"{response.status_code}"
        )

    except Exception as e:

        print(
            f"OpenWA Send Error: {e}"
        )


# --------------------------------------------------
# Background Worker
# --------------------------------------------------

async def process_openwa_message(
    session_id: str,
    chat_id: str,
    user_message: str,
    message_id: str,
):

    try:

        reply = await process_farmer_message(
            phone=chat_id,
            text=user_message,
            message_id=message_id
        )

        if not reply:
            return

        send_openwa_reply(
            session_id=session_id,
            chat_id=chat_id,
            text=reply
        )

    except Exception as e:

        print(
            f"PROCESS ERROR: {e}"
        )


# --------------------------------------------------
# OpenWA Webhook
# --------------------------------------------------

@app.post("/openwa-webhook")
async def openwa_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):

    try:

        payload = await request.json()

        print(
            "OPENWA PAYLOAD:",
            payload
        )

        if payload.get("event") != "message.received":
            return {"status": "ignored"}

        data = payload.get("data", {})

        if data.get("fromMe"):
            return {"status": "ignored"}

        if data.get("isGroup"):
            return {"status": "ignored"}

        session_id = payload["sessionId"]

        chat_id = data["chatId"]

        message_id = data["id"]

        user_message = data.get(
            "body",
            ""
        )

        background_tasks.add_task(
            process_openwa_message,
            session_id,
            chat_id,
            user_message,
            message_id
        )

        return {"status": "ok"}

    except Exception as e:

        print(
            f"WEBHOOK ERROR: {e}"
        )

        return {"status": "ok"}


# --------------------------------------------------
# Privacy
# --------------------------------------------------

@app.get("/privacy")
async def privacy():

    return HTMLResponse(
        """
        <h1>Privacy Policy</h1>

        <p>
        AgriMitra AI stores WhatsApp messages
        and farmer information solely for
        agricultural assistance.
        </p>
        """
    )