import httpx
import os
import base64

OPENWA_URL     = os.getenv("OPENWA_URL")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY")

_HEADERS = {
    "X-API-Key":    OPENWA_API_KEY,
    "Content-Type": "application/json",
}


# ─────────────────────────────────────────────
# Parse incoming OpenWA webhook payload
#
# OpenWA webhook envelope (confirmed from OpenWA docs):
#   {
#     "event": "message.received",
#     "timestamp": "...",
#     "sessionId": "sess_abc123",
#     "deliveryId": "...",
#     "idempotencyKey": "msg_<id>_<timestamp>",
#     "data": { ... },
#     "signature": "sha256=..."
#   }
#
# data shape for text:
#   { "id": "...", "chatId": "628...@c.us", "from": "628...@c.us",
#     "body": "Hello!", "type": "text", "timestamp": 1705312200 }
#
# data shape for media (image/voice/document):
#   type is engine-neutral: "image", "voice", "document", "contact", "location"
#   { "id": ..., "chatId": ..., "type": "image",
#     "caption": "...", "body": "" (often empty for media),
#     "media": { "url": "https://...", "base64": "...", "mimetype": "image/jpeg",
#                "filename": "photo.jpg" } }
#
# NOTE: Whether OpenWA delivers media as `url` or inline `base64` on the
# *incoming* webhook depends on OpenWA server config (storage backend —
# local disk vs S3 — per their architecture docs). This function handles
# BOTH shapes defensively. If your OpenWA instance only ever sends one
# shape, this still works — the other branch will simply be False.
#
#   NEEDS MANUAL VERIFICATION: confirm against your real webhook logs
#   whether incoming `media` contains `url`, `base64`, or both, and
#   whether `idempotencyKey` is reliably present on every delivery
#   (used below for deduplication fallback).
# ─────────────────────────────────────────────

def parse_incoming_message(payload: dict) -> dict | None:
    """
    Extract useful fields from an OpenWA webhook payload.
    Returns None for non-message events (session.status, message.ack, etc.)
    or malformed payloads.

    Returns a dict shaped identically to the old Meta parser's output,
    so the rest of the app (app.py, memory_service) needs zero changes:
        { phone, type, text, media_id, message_id }

    "media_id" here is NOT a separate lookup ID like Meta's — OpenWA
    gives us the media inline (or a direct URL) in the same payload,
    so media_id is repurposed to carry that info forward without
    requiring a second API round-trip the way Meta did.
    """
    try:
        if payload.get("event") != "message.received":
            return None

        data = payload.get("data", {})
        if not data:
            return None

        chat_id  = data.get("chatId") or data.get("from")
        msg_type = data.get("type", "text")
        body     = data.get("body", "") or ""
        caption  = data.get("caption", "") or ""

        # OpenWA message types are engine-neutral. Map to the same
        # internal type names the rest of the app already expects.
        # "voice" (OpenWA) === "audio" (old Meta naming used in app.py)
        type_map = {
            "voice": "audio",
            "ptt":   "audio",   # some engines call voice notes "ptt"
        }
        normalized_type = type_map.get(msg_type, msg_type)

        media_payload = None
        if normalized_type in ("image", "audio", "document"):
            media_payload = data.get("media")

        # Message ID — prefer data.id (confirmed field name), fall back
        # to idempotencyKey from the envelope if data.id is ever missing.
        message_id = data.get("id") or payload.get("idempotencyKey")

        if not chat_id:
            return None

        return {
            "phone":      chat_id,                              # already has @c.us suffix
            "type":       normalized_type,
            "text":       caption or body,                      # caption wins for media messages
            "media_id":   media_payload,                         # dict: {url, base64, mimetype, filename} or None
            "message_id": message_id,
        }

    except (KeyError, IndexError, TypeError, AttributeError):
        return None


# ─────────────────────────────────────────────
# Send a text reply via OpenWA
# ─────────────────────────────────────────────

async def send_whatsapp_reply(phone: str, message: str, session_id: str = None):
    """
    Send a plain text reply to a farmer via OpenWA.

    phone here is the chatId as received from the webhook (already
    has the correct @c.us / @g.us suffix) — do NOT reformat it.

    session_id: the OpenWA session to send from. If not provided,
    falls back to OPENWA_DEFAULT_SESSION env var. OpenWA supports
    multiple concurrent WhatsApp sessions, so in a multi-session
    setup the reply MUST go out on the same session the message
    arrived on, or it will appear to come from the wrong number.
    """
    session_id = session_id or os.getenv("OPENWA_DEFAULT_SESSION")

    if not session_id:
        print("❌ No OpenWA session_id available — cannot send reply")
        return

    url = f"{OPENWA_URL}/api/sessions/{session_id}/messages/send-text"
    payload = {
        "chatId": phone,
        "text":   message[:4096],   # keep same safety cap as before
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=payload, headers=_HEADERS)
            # OpenWA returns 201 Created on successful send (it's creating
            # a new message resource), not 200 — both are success codes.
            if response.status_code in (200, 201):
                print(f"✅ Reply sent to {phone}")
            else:
                print(f"❌ OpenWA send failed [{response.status_code}]: {response.text}")
        except Exception as e:
            print(f"❌ OpenWA send error: {e}")


# ─────────────────────────────────────────────
# Typing indicator
#
# NEEDS MANUAL VERIFICATION: OpenWA's documented API surface
# (session, messages, group, contact, auth, health modules) does not
# show a dedicated "typing" or "presence" endpoint in the docs pages
# crawled for this migration. whatsapp-web.js (the engine OpenWA runs
# on) DOES support sendPresenceAvailable / chatState, so OpenWA likely
# exposes this — but the exact route name needs to be confirmed
# against your OpenWA server's /api/docs (Swagger UI) before relying
# on this in production. This function fails silently (logs only) so
# it can never break the message flow even if the endpoint is wrong.
# ─────────────────────────────────────────────

async def send_typing(phone: str, session_id: str = None):
    """
    Shows a typing indicator in the farmer's chat, if OpenWA supports it
    on your server version. Safe no-op on failure — never blocks the
    AI response from being generated or sent.
    """
    session_id = session_id or os.getenv("OPENWA_DEFAULT_SESSION")
    if not session_id:
        return

    url = f"{OPENWA_URL}/api/sessions/{session_id}/messages/typing"
    payload = {"chatId": phone}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json=payload, headers=_HEADERS)
        except Exception as e:
            # Never let a missing/incorrect typing endpoint break the flow
            print(f"⚠️  send_typing skipped (non-fatal): {e}")


# ─────────────────────────────────────────────
# Mark as read
#
# NEEDS MANUAL VERIFICATION: same caveat as send_typing — confirm the
# exact route in your OpenWA Swagger docs (/api/docs). Common naming
# across WhatsApp gateways is /messages/{messageId}/read or
# /messages/mark-read. Wired here with a sane guess; non-fatal on error.
# ─────────────────────────────────────────────

async def mark_as_read(message_id: str, session_id: str = None):
    """
    Marks the farmer's message as read (blue ticks), if supported.
    Safe no-op on failure.
    """
    session_id = session_id or os.getenv("OPENWA_DEFAULT_SESSION")
    if not session_id or not message_id:
        return

    url = f"{OPENWA_URL}/api/sessions/{session_id}/messages/{message_id}/read"

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, headers=_HEADERS)
        except Exception as e:
            print(f"⚠️  mark_as_read skipped (non-fatal): {e}")


# ─────────────────────────────────────────────
# Download media (image / audio) referenced in an incoming message
#
# Replaces the old two-step Meta flow (resolve media_id → download URL
# → download bytes) because OpenWA already gives us the media inline
# or via a direct URL in the webhook payload itself — no separate
# "resolve" API call is needed.
# ─────────────────────────────────────────────

async def download_whatsapp_media(media_payload: dict) -> bytes | None:
    """
    Given the `media` dict from an OpenWA webhook payload
    (e.g. {"url": "...", "base64": "...", "mimetype": "image/jpeg"}),
    return the raw file bytes.

    Handles both delivery shapes defensively:
      1. Inline base64  → decode directly, no network call needed.
      2. URL only       → fetch it (with API key header, since OpenWA's
                           own media storage is typically auth-gated).
    """
    if not media_payload:
        return None

    # Case 1: base64 already inline — no download needed
    b64 = (
    media_payload.get("base64")
    or media_payload.get("data")
)
    if b64:
        # Strip data URI prefix if present, e.g. "data:image/jpeg;base64,..."
        if "," in b64 and b64.strip().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            return base64.b64decode(b64)
        except Exception as e:
            print(f"❌ Failed to decode inline base64 media: {e}")
            return None

    # Case 2: URL provided — fetch it
    media_url = media_payload.get("url")
    if media_url:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Try with API key header first (OpenWA's own storage)
                resp = await client.get(media_url, headers={"X-API-Key": OPENWA_API_KEY})
                if resp.status_code == 200:
                    return resp.content

                # Fall back to no-auth fetch (e.g. external/public URL)
                resp = await client.get(media_url)
                if resp.status_code == 200:
                    return resp.content

                print(f"❌ Media download failed [{resp.status_code}]: {media_url}")
            except Exception as e:
                print(f"❌ Media download error: {e}")

    return None


async def download_whatsapp_media_base64(
    media_payload: dict
) -> str | None:

    if not media_payload:
        return None

    b64 = (
        media_payload.get("base64")
        or media_payload.get("data")
    )

    if b64:
        if "," in b64 and b64.strip().startswith("data:"):
            b64 = b64.split(",", 1)[1]

        return b64

    raw = await download_whatsapp_media(media_payload)

    if raw is None:
        return None

    return base64.b64encode(raw).decode("utf-8")