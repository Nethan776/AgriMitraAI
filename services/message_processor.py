from services.memory_service import (
    get_or_create_farmer,
    get_recent_messages,
    save_message,
    update_last_active,
    update_farmer_details,
    is_duplicate_message,
    is_onboarding_complete,
)

from services.weather_service import (
    fetch_weather,
    format_weather_for_farmer,
    is_weather_query,
)

from services.ai_service import generate_ai_response


async def process_farmer_message(
    phone: str,
    text: str,
    message_id: str,
):
    """
    Pure business logic.

    No WhatsApp calls.
    No OpenWA calls.
    No Meta calls.

    Returns:
        str | None
    """

    # --------------------------------------------------
    # Farmer
    # --------------------------------------------------

    farmer, is_new = get_or_create_farmer(phone)

    update_last_active(farmer["id"])

    # --------------------------------------------------
    # Deduplication
    # --------------------------------------------------

    if is_duplicate_message(
        farmer["id"],
        message_id
    ):
        return None

    # --------------------------------------------------
    # New Farmer
    # --------------------------------------------------

    if is_new:

        save_message(
            farmer["id"],
            "user",
            text or "(media)",
            whatsapp_message_id=message_id
        )

        greeting = (
            "નમસ્તે! 🌾 કૃષિ મિત્રમાં આપનું સ્વાગત છે!\n\n"
            "શરૂ કરતાં પહેલાં થોડી માહિતી આપો.\n\n"
            "તમારું નામ શું છે?"
        )

        save_message(
            farmer["id"],
            "assistant",
            greeting
        )

        return greeting

    # --------------------------------------------------
    # Onboarding
    # --------------------------------------------------

    if not is_onboarding_complete(farmer):

        step = farmer.get(
            "onboarding_step",
            "ask_name"
        )

        text = text.strip()

        if step == "ask_name":

            update_farmer_details(
                farmer["id"],
                {
                    "name": text,
                    "onboarding_step": "ask_village"
                }
            )

            save_message(
                farmer["id"],
                "user",
                text,
                whatsapp_message_id=message_id
            )

            reply = "તમારું ગામ કયું છે?"

            save_message(
                farmer["id"],
                "assistant",
                reply
            )

            return reply

        elif step == "ask_village":

            update_farmer_details(
                farmer["id"],
                {
                    "village": text,
                    "onboarding_step": "ask_taluka"
                }
            )

            save_message(
                farmer["id"],
                "user",
                text,
                whatsapp_message_id=message_id
            )

            reply = "તમારો તાલુકો કયો છે?"

            save_message(
                farmer["id"],
                "assistant",
                reply
            )

            return reply

        elif step == "ask_taluka":

            update_farmer_details(
                farmer["id"],
                {
                    "taluka": text,
                    "onboarding_step": "done"
                }
            )

            save_message(
                farmer["id"],
                "user",
                text,
                whatsapp_message_id=message_id
            )

            name = farmer.get(
                "name",
                "ખેડૂત"
            )

            reply = (
                f"આવકારો, {name}ભાઈ! 🌾\n\n"
                "હું કૃષિ મિત્ર છું — તમારો AI ખેતી સહાયક.\n\n"
                "હવે તમારી ખેતી સમસ્યા જણાવો — હું મદદ કરીશ! 🙏"
            )

            save_message(
                farmer["id"],
                "assistant",
                reply
            )

            return reply

    # --------------------------------------------------
    # Empty Message
    # --------------------------------------------------

    if not text or not text.strip():

        return (
            "નમસ્તે! 🌾 તમારી ખેતી સમસ્યા "
            "ટેક્સ્ટમાં લખો — હું મદદ કરીશ."
        )

    # --------------------------------------------------
    # Weather
    # --------------------------------------------------

    taluka = (
        farmer.get("taluka")
        or farmer.get("village")
        or "Bharuch"
    )

    weather = await fetch_weather(taluka)

    if is_weather_query(text):

        reply = format_weather_for_farmer(
            weather
        )

        save_message(
            farmer["id"],
            "user",
            text,
            whatsapp_message_id=message_id
        )

        save_message(
            farmer["id"],
            "assistant",
            reply
        )

        return reply

    # --------------------------------------------------
    # AI Response
    # --------------------------------------------------

    history = get_recent_messages(
        farmer["id"],
        limit=5
    )

    reply = generate_ai_response(
        user_message=text,
        history=history,
        farmer=farmer,
        weather=weather
    )

    save_message(
        farmer["id"],
        "user",
        text,
        whatsapp_message_id=message_id
    )

    save_message(
        farmer["id"],
        "assistant",
        reply
    )

    return reply