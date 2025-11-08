from datetime import datetime
import pytz

def generate_reply(conversation):
    from gapi.sheets import get_services
    from utils.date_utils import parse_human_date

    # вземаме текущата дата
    now = datetime.now(pytz.timezone("Europe/Oslo"))
    current_date = now.strftime("%A, %d %B %Y")
    current_time = now.strftime("%H:%M")

    services = get_services()
    services_text = "\n".join([f"- {k.title()} ({v['price']} NOK / {v['duration']} мин)" for k, v in services.items()])

    system_prompt = {
        "role": "system",
        "content": f"""
You are SecretarBOT — a friendly, funny barber assistant.
Current date and time: {current_date}, {current_time}.
Available services:
{services_text}

Your task:
- Talk naturally in the user's language.
- You understand "today", "tomorrow", "Tuesday", etc. using the current date above.
- Ask for service, time/date, and barber.
- When confirmed, respond with a JSON: 
  {{"action":"create_booking","service":"подстригване","datetime":"2025-11-09 15:00","barber":"Миро"}}
- After successful booking, tell one fun fact about hair or beards.
"""
    }

    import requests, os, json
    headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o", "messages": [system_prompt] + conversation}
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return r.json()["choices"][0]["message"]["content"]
