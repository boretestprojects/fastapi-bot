import os, requests, json
from gapi.sheets import get_services
from utils.helpers import detect_language

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def generate_reply(messages):
    """Генерира отговор чрез OpenAI GPT с динамични услуги от Sheets."""
    services = get_services()
    services_text = "\n".join([
        f"- {k.title()} ({v['price']} NOK / {v['duration']} мин)"
        for k, v in services.items()
    ])

    system_prompt = {
        "role": "system",
        "content": f"""
You are SecretarBOT — a friendly multilingual barber assistant.
You always reply in the same language as the user.
Available services:
{services_text}

Ask for missing info step by step (service, date/time, barber).
When all info is known, confirm the booking clearly and respond with JSON:
{{"action": "create_booking", "service": "Herreklipp", "datetime": "2025-11-09 15:00", "barber": "Ivan", "notes": ""}}
After successful confirmation, tell one fun fact about hair or barbers.
Never save or reuse the fact — it’s just for fun.
"""
    }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": "gpt-4o", "messages": [system_prompt] + messages}

    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    print("🤖 GPT reply:", content)
    return content
