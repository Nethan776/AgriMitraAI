import httpx
import os


def parse_incoming_message(body: dict) -> dict | None:
    """
    Extract useful fields from WhatsApp's webhook payload.
    Returns None for status updates, reactions, and non-message events.

    Key addition: returns whatsapp_message_id so we can deduplicate.
    WhatsApp retries webhooks if it doesn't get a fast 200 OK, which
    causes the same message to arrive 2-3 times. We block duplicates
    in memory_service using this ID.
    """
    try:
        entry = body["entry"][0]["changes"][0]["value"]

        # Status webhooks (delivered, read, failed) have no "messages" key
        if "messages" not in entry:
            return None

        message  = entry["messages"][0]
        phone    = message["from"]
        msg_type = message["type"]
        msg_id   = message.get("id")   # unique WhatsApp message ID

        text     = None
        media_id = None

        if msg_type == "text":
            text = message["text"]["body"]

        elif msg_type == "image":
            text     = message.get("image", {}).get("caption", "")
            media_id = message["image"]["id"]

        elif msg_type == "audio":
            text     = ""
            media_id = message["audio"]["id"]

        elif msg_type == "document":
            text     = message.get("document", {}).get("caption", "")
            media_id = message["document"]["id"]

        else:
            # Reactions, stickers, location, etc. — ignore
            return None

        return {
            "phone":      phone,
            "type":       msg_type,
            "text":       text or "",
            "media_id":   media_id,
            "message_id": msg_id       # ← used for deduplication
        }

    except (KeyError, IndexError, TypeError):
        return None


async def send_whatsapp_reply(phone: str, message: str):
    """Send a plain text reply to a farmer on WhatsApp."""

    url = f"https://graph.facebook.com/v19.0/{os.getenv('WHATSAPP_PHONE_ID')}/messages"

    headers = {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
        "Content-Type":  "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to":   phone,
        "type": "text",
        "text": {"body": message[:4096]}   # WhatsApp hard limit
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            print(f"✅ Reply sent to {phone}")
        else:
            print(f"❌ WhatsApp send failed [{response.status_code}]: {response.text}")


async def download_whatsapp_media(media_id: str) -> bytes | None:
    """
    Download a media file (image / audio) from WhatsApp servers.
    Step 1: resolve media_id → download URL
    Step 2: download the file bytes
    """
    headers = {"Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}"}

    async with httpx.AsyncClient() as client:

        # Step 1 — get download URL from media ID
        meta = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers=headers
        )
        if meta.status_code != 200:
            print(f"❌ Could not resolve media ID: {media_id}")
            return None

        media_url = meta.json().get("url")
        if not media_url:
            return None

        # Step 2 — download file
        file_resp = await client.get(media_url, headers=headers)
        if file_resp.status_code == 200:
            return file_resp.content

    return None
