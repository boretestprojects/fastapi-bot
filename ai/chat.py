import os, json, requests
from gapi.sheets import get_services

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def generate_reply(history):
    services = get_services()
    service_text = "\n".join([f"- {k.title()} ({v['price']} NOK / {v['duration']} мин)" for k, v in services.items()])
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

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        data = r.json()

        # 🧩 Проверяваме дали има валидно съдържание
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]

        # ⚠️ Ако API върне грешка
        elif "error" in data:
            err_msg = data["error"].get("message", "Unknown error")
            print(f"⚠️ OpenAI API Error: {err_msg}")
            return "Извинявай, имам малък проблем с връзката към AI сървъра. Опитай пак след малко 🙂"

        # 🪫 Неочакван отговор
        else:
            print(f"⚠️ Unexpected API response: {data}")
            return "Хмм... нещо не се получи с отговора. Може ли да повториш?"

    except Exception as e:
        print("❌ OpenAI Request Error:", e)
        return "Имаше временен проблем с връзката към AI услугата. Опитай пак след малко!"
