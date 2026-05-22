from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

SYSTEM_PROMPT = """
You are AgriMitra AI, a practical Gujarati agricultural assistant for Indian farmers.

Guidelines:
- Reply only in simple, natural Gujarati.
- Focus on the MOST likely cause based on symptoms.
- Give short, practical, farmer-friendly advice.
- Use the provided agricultural reference context carefully.
- Prefer safe and verified guidance over confident guesses.
- Never invent pesticide names, fertilizer dosages, chemical mixtures, or spray quantities.
- Only mention exact treatments if clearly present in trusted agricultural references.
- Do not mention unrelated pests or diseases just to sound knowledgeable.
- Ask at most ONE follow-up question if diagnosis is unclear.
- Avoid robotic, academic, or government-style language.
- Sound like an experienced local farming advisor.
- If uncertain, recommend checking with a local agricultural expert.
- Keep the responce under 70 words

Response style:
- Start with the likely issue.
- Then give 2-3 practical actions.
- Keep answers concise and easy for farmers to understand.
"""


def build_system_prompt(farmer: dict = None, rag_context: str = "") -> str:
    prompt = SYSTEM_PROMPT

    # Inject farmer profile
    if farmer:
        name    = farmer.get("name")    or "ખેડૂત"
        village = farmer.get("village") or "અજ્ઞાત"
        taluka  = farmer.get("taluka")  or "અજ્ઞાત"
        prompt += f"""
━━━ ખેડૂત માહિતી ━━━
• નામ: {name}
• ગામ: {village}
• તાલુકો: {taluka}
આ ખેડૂત સાથે વ્યક્તિગત અને આત્મીય રીતે વાત કરો.
"""

    # Inject RAG context if available
    if rag_context:
        prompt += rag_context

    return prompt


def generate_ai_response(user_message: str, history: list = None, farmer: dict = None) -> str:
    # Get relevant knowledge from PDF
    try:
        from services.rag_service import get_rag_context
        rag_context = get_rag_context(user_message, history)
    except Exception as e:
        print(f"⚠️  RAG error: {e}")
        rag_context = ""

    messages = [{"role": "system", "content": build_system_prompt(farmer, rag_context)}]

    if history:
        for msg in history:
            messages.append({
                "role":    msg["role"],
                "content": msg["content"]
            })

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b:free",
        messages=messages,
        temperature=0.3,
        max_tokens=500,
    )

    return response.choices[0].message.content.strip()