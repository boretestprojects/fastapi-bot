import requests, os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def ask_gpt(messages, services_text):
    system_prompt = {
        "role": "system",
        "content": f"""You are SecretarBOT 💈 — a friendly and witty virtual barber assistant.
You help users book barber services naturally (haircuts, beard trims, washing, etc.).
You're warm, humorous, and professional. 
Keep replies short, personal, and helpful — no JSON.
Always respond in the same language the user uses.
Available services:
{services_text}
""",
    }

    payload = {
        "model": "gpt-4o",
        "messages": [system_prompt] + messages,
        "temperature": 0.8,
    }

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    return r.json()["choices"][0]["message"]["content"]
