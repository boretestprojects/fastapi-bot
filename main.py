from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import requests, os, re, json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz
from dateutil import parser as dateparser

# ===== CONFIG =====
VERIFY_TOKEN = "barberbot_verify_token"
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
TIMEZONE = pytz.timezone("Europe/Oslo")

app = FastAPI()

# ===== GOOGLE AUTH =====
creds_data = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = service_account.Credentials.from_service_account_info(
    creds_data,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/calendar",
    ],
)
sheets_service = build("sheets", "v4", credentials=creds)
calendar_service = build("calendar", "v3", credentials=creds)

# ===== MEMORY =====
conversations = {}

# ===== HELPERS =====
def send_message(psid, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": psid}, "message": {"text": text}}
    requests.post(url, json=payload)

def get_user_name(psid):
    url = f"https://graph.facebook.com/{psid}"
    params = {"fields": "first_name,last_name", "access_token": PAGE_ACCESS_TOKEN}
    try:
        r = requests.get(url, params=params).json()
        return f"{r.get('first_name','')} {r.get('last_name','')}".strip()
    except:
        return "Messenger клиент"

def get_sheet_range(tab):
    return sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab}!A2:Z"
    ).execute().get("values", [])

def get_services():
    rows = get_sheet_range("Services")
    services = {}
    for r in rows:
        if len(r) >= 3:
            services[r[0].strip().lower()] = {
                "price": r[1],
                "duration": int(r[2]) if r[2].isdigit() else 30,
            }
    return services

def update_clients(psid, name, service, barber, dt, notes):
    sheet = sheets_service.spreadsheets()
    values = get_sheet_range("Clients")
    found = False
    for i, row in enumerate(values, start=2):
        if len(row) > 0 and row[0] == psid:
            found = True
            sheet.values().update(
                spreadsheetId=SHEET_ID,
                range=f"Clients!A{i}:F{i}",
                valueInputOption="RAW",
                body={"values": [[psid, name, service, barber, dt, notes]]},
            ).execute()
            break
    if not found:
        sheet.values().append(
            spreadsheetId=SHEET_ID,
            range="Clients!A:F",
            valueInputOption="RAW",
            body={"values": [[psid, name, service, barber, dt, notes]]},
        ).execute()
    print("🧾 Saved client:", name, service, barber, dt)

def append_history(name, service, barber, dt, notes, psid):
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="History!A:F",
        valueInputOption="RAW",
        body={"values": [[dt, name, service, barber, notes, psid]]},
    ).execute()
    print("📜 History appended:", name, dt)

def create_event(name, service, barber, dt_obj, duration, notes):
    if not dt_obj:
        return None
    end_dt = dt_obj + timedelta(minutes=duration)
    event = {
        "summary": f"{name} – {service} ({barber})",
        "description": f"Notes: {notes}",
        "start": {"dateTime": dt_obj.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }
    calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    print("📅 Calendar event created:", dt_obj)
    return True

def parse_date_from_text(text):
    try:
        dt = dateparser.parse(text, fuzzy=True)
        if dt:
            dt = TIMEZONE.localize(dt)
            if dt < datetime.now(TIMEZONE):
                dt += timedelta(days=7)
            return dt
    except:
        return None

def extract_info(text, services):
    text_low = text.lower()
    service = next((s for s in services if s in text_low), None)
    dt_obj = parse_date_from_text(text)
    barber = "Ivan" if "ivan" in text_low else "Bore" if "bore" in text_low else ""
    return service, barber, dt_obj

def ask_gpt(messages, services_text):
    system_prompt = {
        "role": "system",
        "content": f"""You are SecretarBOT 💈 — a friendly barber assistant.
Talk naturally, ask questions, make jokes, and help users book appointments.
Don't output JSON, just confirm and chat.
Available services:
{services_text}""",
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
    ).json()
    return r["choices"][0]["message"]["content"]

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
    return {"status": "ok", "message": "SecretarBOT v6.5 Smart Parse Edition active"}

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
                    user_name = get_user_name(psid)

                    if psid not in conversations:
                        conversations[psid] = []
                    conversations[psid].append({"role": "user", "content": user_text})

                    services = get_services()
                    services_text = "\n".join(
                        [f"- {k.title()} ({v['price']} NOK, {v['duration']} min)" for k, v in services.items()]
                    )

                    # 1️⃣ GPT отговаря естествено
                    reply = ask_gpt(conversations[psid], services_text)
                    send_message(psid, reply)

                    # 2️⃣ Проверяваме и двете посоки (твоето + GPT)
                    service, barber, dt_obj = extract_info(user_text, services)
                    if not service or not dt_obj:
                        service, barber, dt_obj = extract_info(reply, services)

                    # 3️⃣ Ако имаме всичко → запис
                    if service and dt_obj:
                        duration = services[service]["duration"]
                        update_clients(psid, user_name, service, barber, dt_obj.strftime("%A, %d %B %Y %H:%M"), "")
                        append_history(user_name, service, barber, dt_obj.strftime("%A, %d %B %Y %H:%M"), "", psid)
                        create_event(user_name, service, barber, dt_obj, duration, "")
                        confirm = (
                            f"✅ Записах те за {service.title()} при {barber or 'свободен майстор'} "
                            f"на {dt_obj.strftime('%A, %d %B %Y %H:%M')} 💈\n"
                            "Благодаря, че избра нашия салон! 🙏"
                        )
                        send_message(psid, confirm)
                        conversations.pop(psid, None)
                        continue

    except Exception as e:
        print("❌ Error:", e)
    return {"status": "ok"}

