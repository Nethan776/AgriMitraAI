from services.database_service import supabase
from datetime import datetime, timezone


# ─────────────────────────────────────────────
# Farmer
# ─────────────────────────────────────────────

def get_or_create_farmer(phone: str) -> tuple[dict, bool]:
    result = supabase.table("farmers") \
        .select("*") \
        .eq("whatsapp_number", phone) \
        .execute()

    if result.data:
        return result.data[0], False

    inserted = supabase.table("farmers") \
        .insert({
            "whatsapp_number": phone,
            "onboarding_step": "ask_name"
        }) \
        .execute()

    print(f"🌱 New farmer registered: {phone}")
    return inserted.data[0], True


def update_farmer_details(farmer_id: str, fields: dict):
    supabase.table("farmers") \
        .update(fields) \
        .eq("id", farmer_id) \
        .execute()


def update_last_active(farmer_id: str):
    supabase.table("farmers") \
        .update({"last_active": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", farmer_id) \
        .execute()


def is_onboarding_complete(farmer: dict) -> bool:
    return farmer.get("onboarding_step") == "done"


# ─────────────────────────────────────────────
# Messages — deduplication per farmer
# ─────────────────────────────────────────────

def is_duplicate_message(farmer_id: str, whatsapp_message_id: str) -> bool:
    """
    Check if this farmer already has this message ID saved.
    Scoped per farmer — two different farmers can have the same
    message ID without conflict (WhatsApp can reuse IDs across users).
    """
    if not whatsapp_message_id or not farmer_id:
        return False

    result = supabase.table("messages") \
        .select("id") \
        .eq("farmer_id", farmer_id) \
        .eq("whatsapp_message_id", whatsapp_message_id) \
        .execute()

    return len(result.data) > 0


def save_message(farmer_id: str, role: str, content: str, whatsapp_message_id: str = None):
    row = {
        "farmer_id": farmer_id,
        "role":      role,
        "content":   content,
    }

    if whatsapp_message_id:
        row["whatsapp_message_id"] = whatsapp_message_id

    supabase.table("messages").insert(row).execute()
    supabase.rpc("increment_farmer_messages", {"farmer_id_input": farmer_id}).execute()


def get_recent_messages(farmer_id: str, limit: int = 5) -> list:
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