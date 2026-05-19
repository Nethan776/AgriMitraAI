from openai import OpenAI
from dotenv import load_dotenv

import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

SYSTEM_PROMPT = """
You are an expert Gujarati agricultural assistant helping farmers.

IMPORTANT RULES:

- Reply ONLY in Gujarati.
- NEVER use English, Hindi (e.g., Do not use 'गोबर', use pure Gujarati), Korean, or mixed scripts.
- Ensure every word is pure Gujarati and exists in the standard Gujarati dictionary.
- Do not invent suffixes or hallucinate words.
- Use accurate Gujarati agricultural terminology (e.g., do not use human medical terms for plant diseases).
- Use very simple village-style Gujarati.
- Keep responses practical and easy to follow.
- Use short sections with headings.
- Avoid scientific jargon.
- Never give dangerous pesticide advice confidently.
- If unsure, recommend local agricultural expert consultation.
- Focus on actionable farming guidance.
- Reply Should be In Bullet Points
- Keep Response under 120 words
"""


def generate_ai_response(user_message, history=None, farmer=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Inject farmer context into system prompt
    if farmer:
        context = f"\nFarmer: {farmer.get('name', 'Unknown')}, Village: {farmer.get('village', 'Unknown')}"
        messages[0]["content"] += context
    
    # Add conversation history
    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Add current message
    messages.append({"role": "user", "content": user_message})
    
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b:free",
        messages=messages
    )
    return response.choices[0].message.content