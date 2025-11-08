from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import requests, os, json, re
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz

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

# ===== CONVERSATION MEMORY =====
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
        return "Messenger client"

def get_sheet_range(tab):
    return sheets_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=f"{tab}!A2:Z").execute().get("values", [])

def get_services():
    rows = get_sheet_range("Services")
    services = {}
    for r in rows:
        if len(r) >= 3:
            services[r[0].strip().lower()] = {
                "price": r[1],
                "duration": r[2],
                "allowed": {h.lower(): v for h, v in zip(rows[0][3:], r[3:])}
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
                "restricted": r[4] if len(r) > 4 else ""
            }
    return barbers

def update_clients(psid, name, service, barber, dt, notes):
    values = get_sheet_range("Clients")
    sheet = sheets_service.spreadsheets()
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

def append_history(name, service, barber, dt, notes, psid):
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="History!A:F",
        valueInputOption="RAW",
        body={"values": [[dt, name, service, barber, notes, psid]]},
    ).execute()

def create_event(name, service, barber, dt_str, notes):
    start_dt = datetime.strptime(dt_str, "%A, %d %B %Y at %H:%M")
    start_dt = TIMEZONE.localize(start_dt)
    end_dt = start_dt + timedelta(minutes=30)
    event = {
        "summary": f"{name} – {service} ({barber})",
        "description": f"Notes: {notes}",
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }
    calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()

def extract_notes(text):
    m = re.findall(r"(?:може|ще|навярно|вероятно).{0,30}", text, re.IGNORECASE)
    return m[0] if m else ""

def ask_gpt(messages, services_text, barbers_text):
    system_prompt = {
        "role": "system",
        "content": f"""You are SecretarBOT — a funny and friendly barber assistant 💈😄
You help clients book services step by step (service, date/time, barber).
When all info is ready, confirm booking clearly, then end with a fun fact about hair or humans.
Always stay cheerful, casual, and a bit humorous.
Available services:
{services_text}

Available barbers:
{barbers_text}

If the user confirms booking, respond in JSON:
{{"action": "create_booking", "service": "...", "datetime": "...", "barber": "...", "notes": "..."}}"""
    }
    payload = {"model": "gpt-4o", "messages": [system_prompt] + messages}
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                               "Content-Type": "application/json"},
                      json=payload).json()
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
    return {"status": "ok", "message": "SecretarBOT v6.4 PRO Friendly Edition active"}

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

                    services_text = "\n".join([f"- {k.title()} ({v['price']} NOK, {v['duration']} min)" for k, v in services.items()])
                    barbers_text = "\n".join([f"- {k.title()} ({v['days']} {v['start']}-{v['end']})" for k, v in barbers.items()])

                    reply = ask_gpt(conversations[psid], services_text, barbers_text)

                    try:
                        parsed = json.loads(reply)
                        if parsed.get("action") == "create_booking":
                            service = parsed["service"]
                            dt = parsed["datetime"]
                            barber = parsed["barber"]
                            notes = parsed.get("notes", "") or extract_notes(user_text)

                            # Record client + history + calendar
                            update_clients(psid, user_name, service, barber, dt, notes)
                            append_history(user_name, service, barber, dt, notes, psid)
                            create_event(user_name, service, barber, dt, notes)

                            confirm = (f"✅ Резервацията е потвърдена, {user_name}! 💈\n"
                                       f"{dt} при {barber.title()} за {service.title()} ✂️\n"
                                       f"Бележка: {notes if notes else 'няма'}\n"
                                       f"Благодарим, че избра нашия салон! 🙏\n\n"
                                       f"Знаеше ли, че човешката коса може да издържи до 100 грама тежест? 😄")
                            send_message(psid, confirm)
                            conversations.pop(psid, None)
                            continue
                    except Exception:
                        pass

                    send_message(psid, reply)
    except Exception as e:
        print("❌ Error:", e)
    return {"status": "ok"}
