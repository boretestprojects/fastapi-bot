from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import requests, os, json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ===== CONFIG =====
VERIFY_TOKEN = "barberbot_verify_token"
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

app = FastAPI()

# ===== GOOGLE AUTH =====
creds = service_account.Credentials.from_service_account_file(
    "credentials.json",
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/calendar"
    ]
)
sheets_service = build("sheets", "v4", credentials=creds)
calendar_service = build("calendar", "v3", credentials=creds)

# ===== CONVERSATION MEMORY =====
conversations = {}

# ===== HELPERS =====
def send_message(psid, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": psid}, "message": {"text": text}}
    requests.post(url, json=payload)

def get_services():
    sheet = sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Services!A2:C"
    ).execute()
    values = sheet.get("values", [])
    return {r[0].lower(): {"price": r[1], "duration": r[2]} for r in values if len(r) >= 3}

def create_event(service_name, start_time, duration=30, user_name="Messenger клиент"):
    start = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
    end = start + timedelta(minutes=duration)
    event = {
        "summary": f"{user_name} – {service_name}",
        "start": {"dateTime": start.isoformat() + "Z"},
        "end": {"dateTime": end.isoformat() + "Z"},
    }
    result = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return result.get("htmlLink")

def ask_gpt(messages):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    # динамично зареждане на услугите
    services = get_services()
    services_text = "\n".join([
        f"- {k.title()} ({v['price']} лв / {v['duration']} мин)"
        for k, v in services.items()
    ])

    system_prompt = {
        "role": "system",
        "content": f"""You are SecretarBOT — a funny, friendly barber assistant.
You help users book barber services based on the list below.
Available services:
{services_text}

Ask for missing info step by step (service, time/date, barber).
When all info is known, confirm the booking clearly, then tell a fun or curious fact related to hair, beards, or humans.
Never record or save the fact anywhere — just say it.
Always sound cheerful, confident and humorous.
If the user confirms the booking, respond with a JSON object like:
{{"action": "create_booking", "service": "подстригване", "datetime": "2025-11-09 15:00"}}"""
    }

    payload = {"model": "gpt-4o", "messages": [system_prompt] + messages}
    r = requests.post(url, headers=headers, json=payload)
    return r.json()["choices"][0]["message"]["content"]

# ===== WEBHOOK VERIFY =====
@app.get("/webhook")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return {"error": "Invalid verification"}

@app.get("/")
async def home():
    return {"status": "ok", "message": "SecretarBOT v6.1 dynamic version active"}

# ===== MAIN WEBHOOK =====
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        for entry in data.get("entry", []):
            for msg in entry.get("messaging", []):
                if "message" in msg and "text" in msg["message"]:
                    psid = msg["sender"]["id"]
                    user_text = msg["message"]["text"]

                    if psid not in conversations:
                        conversations[psid] = []
                    conversations[psid].append({"role": "user", "content": user_text})

                    reply = ask_gpt(conversations[psid])
                    conversations[psid].append({"role": "assistant", "content": reply})

                    # Проверка дали GPT е върнал JSON за резервация
                    try:
                        parsed = json.loads(reply)
                        if isinstance(parsed, dict) and parsed.get("action") == "create_booking":
                            service = parsed["service"]
                            dt = parsed["datetime"]
                            services = get_services()
                            duration = int(services.get(service.lower(), {}).get("duration", 30))
                            link = create_event(service, dt, duration)
                            send_message(psid, f"✅ Записах те за {service} ({dt}). Виж събитието тук: {link}")
                            continue
                    except Exception:
                        pass

                    send_message(psid, reply)
    except Exception as e:
        print("❌ Error:", e)
    return {"status": "ok"}
