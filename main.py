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

# ===== GOOGLE AUTH (чете от ENV, не от файл) =====
creds_data = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = service_account.Credentials.from_service_account_info(
    creds_data,
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

def get_barbers():
    sheet = sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Barbers!A2:C"
    ).execute()
    values = sheet.get("values", [])
    return [{"name": r[0], "days": r[1].lower(), "specialty": r[2]} for r in values if len(r) >= 3]

def is_barber_available(barber_name):
    barbers = get_barbers()
    today_day = datetime.utcnow().strftime("%a").lower()  # Mon, Tue...
    for b in barbers:
        if barber_name.lower() in b["name"].lower():
            if today_day[:3] in b["days"].lower():
                return True
    return False

def create_event(service_name, start_time, duration=30, user_name="Messenger клиент", barber=None):
    try:
        start = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
        # ако GPT върне минала дата → премести я утре в 13:00
        if start < datetime.utcnow():
            start = datetime.utcnow() + timedelta(days=1)
            start = start.replace(hour=13, minute=0, second=0, microsecond=0)

        # проверка дали бръснарят е на работа днес
        if barber and not is_barber_available(barber):
            print(f"⚠️ {barber} не е по график днес.")
            return None

        end = start + timedelta(minutes=duration)
        summary = f"{user_name} – {service_name}"
        if barber:
            summary += f" ({barber})"

        event = {
            "summary": summary,
            "start": {"dateTime": start.isoformat() + "Z"},
            "end": {"dateTime": end.isoformat() + "Z"},
        }

        result = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print(f"✅ Google Calendar event created: {result.get('htmlLink')}")
        return result.get("htmlLink")

    except Exception as e:
        print(f"❌ Calendar error: {e}")
        return None

def ask_gpt(messages):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    services = get_services()
    barbers = get_barbers()

    services_text = "\n".join([
        f"- {k.title()} ({v['price']} лв / {v['duration']} мин)"
        for k, v in services.items()
    ])
    barbers_text = "\n".join([
        f"- {b['name']} (дни: {b['days']}, специалност: {b['specialty']})"
        for b in barbers
    ])

    system_prompt = {
        "role": "system",
        "content": f"""You are SecretarBOT — a friendly and funny barber assistant.
Available services:
{services_text}

Available barbers:
{barbers_text}

Always prefer upcoming future times, never suggest past dates.
Ask for missing info step by step (service, date/time, barber).
When all info is known, confirm the booking clearly,
then tell a funny or interesting fact related to hair, beards, or humans.
Never record or save the fact anywhere — just say it.
If the user confirms the booking, respond in JSON like:
{{"action": "create_booking", "service": "подстригване", "datetime": "2025-11-09 15:00", "barber": "Миро"}}
"""
    }

    payload = {"model": "gpt-4o", "messages": [system_prompt] + messages}
    r = requests.post(url, headers=headers, json=payload)
    result = r.json()["choices"][0]["message"]["content"]
    print(f"🤖 GPT replied: {result}")
    return result

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
    return {"status": "ok", "message": "SecretarBOT v6.3 — dynamic version (auto dates + schedule check)"}

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

                    try:
                        parsed = json.loads(reply)
                        if isinstance(parsed, dict) and parsed.get("action") == "create_booking":
                            service = parsed["service"]
                            dt = parsed["datetime"]
                            barber = parsed.get("barber")
                            services = get_services()
                            duration = int(services.get(service.lower(), {}).get("duration", 30))
                            link = create_event(service, dt, duration, barber=barber)
                            if link:
                                send_message(psid, f"✅ Записах те за {service} при {barber} ({dt}). Виж събитието тук: {link}")
                            else:
                                send_message(psid, f"⚠️ {barber} не е по график в този ден. Избери друг ден или друг бръснар 🙂")
                            continue
                    except Exception:
                        pass

                    send_message(psid, reply)
    except Exception as e:
        print("❌ Error:", e)
    return {"status": "ok"}
