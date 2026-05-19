from services.database_service import supabase
from datetime import datetime, timezone


# ─────────────────────────────────────────────
# Farmer
# ─────────────────────────────────────────────

def get_or_create_farmer(phone: str) -> dict:
    """
    Look up farmer by WhatsApp number.
    Creates a new bare profile if this is their first message.
    """
    result = supabase.table("farmers") \
        .select("*") \
        .eq("whatsapp_number", phone) \
        .execute()

    if result.data:
        return result.data[0]

    # First time this farmer messages — create profile
    inserted = supabase.table("farmers") \
        .insert({"whatsapp_number": phone}) \
        .execute()

    print(f"🌱 New farmer registered: {phone}")
    return inserted.data[0]


def update_last_active(farmer_id: str):
    """Update the farmer's last_active timestamp on every message."""
    supabase.table("farmers") \
        .update({"last_active": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", farmer_id) \
        .execute()


# ─────────────────────────────────────────────
# Messages — with deduplication
# ─────────────────────────────────────────────

def is_duplicate_message(whatsapp_message_id: str) -> bool:
    """
    Check if we've already processed this WhatsApp message ID.

    WhatsApp retries webhook delivery if it doesn't get a fast 200 OK.
    This causes the same message to arrive 2-3 times.
    We block duplicates using the unique whatsapp_message_id field.
    """
    if not whatsapp_message_id:
        return False

    result = supabase.table("messages") \
        .select("id") \
        .eq("whatsapp_message_id", whatsapp_message_id) \
        .execute()

    return len(result.data) > 0


def save_message(farmer_id: str, role: str, content: str, whatsapp_message_id: str = None):
    """
    Save a message to the database.
    Pass whatsapp_message_id for user messages so we can deduplicate future retries.
    """
    row = {
        "farmer_id": farmer_id,
        "role":      role,
        "content":   content,
    }

    # Only store message_id for user messages (assistant messages have no WA ID)
    if whatsapp_message_id:
        row["whatsapp_message_id"] = whatsapp_message_id

    supabase.table("messages").insert(row).execute()

    # Increment total_messages counter on farmer row
    supabase.rpc("increment_farmer_messages", {"farmer_id_input": farmer_id}).execute()


def get_recent_messages(farmer_id: str, limit: int = 5) -> list:
    """
    Fetch the last N messages for this farmer (oldest first).
    Used as conversation history context for the AI.
    """
    result = supabase.table("messages") \
        .select("role, content") \
        .eq("farmer_id", farmer_id) \
        .order("created_at", desc=True) \
        .limit(limit) \
        .execute()

    # Reverse so oldest message is first (correct order for AI context)
    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in reversed(result.data)
    ]


