from services.database_service import supabase
from datetime import datetime, timezone


# ─────────────────────────────────────────────
# Farmer
# ─────────────────────────────────────────────

def get_or_create_farmer(phone: str) -> tuple[dict, bool]:
    """
    Look up farmer by WhatsApp number.
    Returns (farmer_dict, is_new) so the caller knows if this is
    their first message and needs to collect their details.
    """
    result = supabase.table("farmers") \
        .select("*") \
        .eq("whatsapp_number", phone) \
        .execute()

    if result.data:
        return result.data[0], False

    # First time — create bare profile with just phone number
    inserted = supabase.table("farmers") \
        .insert({
            "whatsapp_number": phone,
            "onboarding_step": "ask_name"   # tracks where they are in setup
        }) \
        .execute()

    print(f"🌱 New farmer registered: {phone}")
    return inserted.data[0], True


def update_farmer_details(farmer_id: str, fields: dict):
    """Update any farmer profile fields."""
    supabase.table("farmers") \
        .update(fields) \
        .eq("id", farmer_id) \
        .execute()


def update_last_active(farmer_id: str):
    """Update the farmer's last_active timestamp on every message."""
    supabase.table("farmers") \
        .update({"last_active": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", farmer_id) \
        .execute()


def is_onboarding_complete(farmer: dict) -> bool:
    """Returns True only when all onboarding steps are fully done."""
    return farmer.get("onboarding_step") == "done"


# ─────────────────────────────────────────────
# Messages — with deduplication
# ─────────────────────────────────────────────

def is_duplicate_message(whatsapp_message_id: str) -> bool:
    """
    Check if we've already processed this WhatsApp message ID.
    WhatsApp retries webhooks if it doesn't get a fast 200 OK,
    causing the same message to arrive 2-3 times.
    """
    if not whatsapp_message_id:
        return False

    result = supabase.table("messages") \
        .select("id") \
        .eq("whatsapp_message_id", whatsapp_message_id) \
        .execute()

    return len(result.data) > 0


def save_message(farmer_id: str, role: str, content: str, whatsapp_message_id: str = None):
    """Save a message (user or assistant) to the database."""
    row = {
        "farmer_id": farmer_id,
        "role":      role,
        "content":   content,
    }

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

    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in reversed(result.data)
    ]