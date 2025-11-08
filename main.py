from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import requests, os, json, re
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

def get_barbers():
    rows = get_sheet_range("Barbers")
    barbers = {}
    for r in rows:
        if len(r) >= 4:
            barbers[r[0].strip().lower()] = {
                "days": r[1],
                "start": r[2],
                "end": r[3],
                "restricted": r[4] if len(r) > 4 else "",
            }
    return barbers

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
    print("🧾 Client saved to sheet:", name, service, barber, dt)

def append_history(name, service, barber, dt, notes, psid):
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="History!A:F",
        valueInputOption="RAW",
        body={"values": [[dt, name, service, barber, notes, psid]]},
    ).execute()
    print("📜 History appended:", name, dt)

def parse_date(dt_str):
    try:
        dt = dateparser.parse(dt_str)
        if not dt:
            return None
        dt = TIMEZONE.localize(dt)
        if dt < datetime.now(TIMEZONE):
            dt += timedelta(days=7)
        print("🟢 Parsed date:", dt)
        return dt
    except Exception as e:
        print("❌ Date parse failed:", e)
        return None

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

def ask_gpt(messages, services_text, barbers_text):
    system_prompt = {
        "role": "system",
        "content": f"""You are SecretarBOT — a friendly barber assistant 💈
Help users book hair & beard services.
Ask step by step: service, date/time, barber, notes.
When all info is ready, reply **only with pure JSON**, nothing else.
Always produce future dates (never past).
Available services:
{services_text}
Available barbers:
{barbers_text}
Format example:
{{"action":"create_booking","service":"Herreklipp","datetime":"2025-11-09T15:00:00Z","barber":"Ivan","notes":"може да закъснея с 5 мин"}}"""
    }
    payload = {
        "model": "gpt-4o",
        "messages": [system_prompt] + messages,
        "temperature": 0.3,
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
    return {"status": "ok", "message": "SecretarBOT v6.4.2 PRO (Safe JSON + Date Fix) active"}

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
                    barbers = get_barbers()

                    services_text = "\n".join(
                        [f"- {k.title()} ({v['price']} NOK, {v['duration']} min)" for k, v in services.items()]
                    )
                    barbers_text = "\n".join(
                        [f"- {k.title()} ({v['days']} {v['start']}-{v['end']})" for k, v in barbers.items()]
                    )

                    reply = ask_gpt(conversations[psid], services_text, barbers_text)
                    print("🤖 GPT replied:", reply)

                    try:
                        parsed = json.loads(reply)
                        if parsed.get("action") == "create_booking":
                            service = parsed["service"].lower()
                            dt_str = parsed["datetime"]
                            barber = parsed["barber"]
                            notes = parsed.get("notes", "") or ""
                            dt_obj = parse_date(dt_str)

                            if not dt_obj:
                                send_message(psid, "🤔 Не разбрах точно датата — можеш ли да я потвърдиш? Например: 'следващия петък 15:00'")
                                continue

                            duration = services.get(service, {}).get("duration", 30)
                            update_clients(psid, user_name, service, barber, dt_obj.strftime("%A, %d %B %Y %H:%M"), notes)
                            append_history(user_name, service, barber, dt_obj.strftime("%A, %d %B %Y %H:%M"), notes, psid)
                            create_event(user_name, service, barber, dt_obj, duration, notes)

                            confirm = (
                                f"✅ Резервацията е потвърдена, {user_name}! 💈\n"
                                f"{dt_obj.strftime('%A, %d %B %Y %H:%M')} при {barber.title()} за {service.title()} ✂️\n"
                                f"Бележка: {notes if notes else 'няма'}\n"
                                f"Благодарим, че избра нашия салон! 🙏\n\n"
                                f"Знаеше ли, че брадата на човек расте средно с около 14 см на година? 😄"
                            )
                            send_message(psid, confirm)
                            conversations.pop(psid, None)
                            continue
                    except Exception as err:
                        print("⚠️ JSON parse error:", err)
                        send_message(psid, "Изглежда нещо не беше разбрано — можеш ли да повториш по-просто? 🙂")
                        continue

                    send_message(psid, reply)
    except Exception as e:
        print("❌ Error:", e)
    return {"status": "ok"}
