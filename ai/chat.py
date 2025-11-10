import os, json, requests
from gapi.sheets import get_services

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def generate_reply(history):
    services = get_services()
    service_text = "\n".join([f"- {k.title()} ({v['price']} NOK / {v['duration']} мин)" for k,v in services.items()])
    barbers = ["Ivan", "Bore"]

    system_prompt = {
        "role": "system",
        "content": f"""
You are SecretarBOT — a friendly but logical AI barber assistant.
Speak in the same language the user writes in.
You know only these barbers: {", ".join(barbers)}.
Available services:
{service_text}

Ask for missing info step by step (service → date/time → barber).
When all info is known, respond ONLY with valid JSON:
{{"action": "create_booking", "service": "...", "datetime": "...", "barber": "...", "notes": "..."}}
Do not include any text before or after JSON.
Never invent new barbers or dates. If user says "утре" or "сряда", use that text as datetime.
If unsure, ask short, polite question to clarify.
"""
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [system_prompt] + history,
        "temperature": 0.4,
    }

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return r.json()["choices"][0]["message"]["content"]
