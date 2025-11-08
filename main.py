from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
import os, json, traceback
from datetime import datetime
from ai.chat import generate_reply
from gapi.sheets import get_services, update_clients, append_history
from gapi.calendar import create_event
from utils.helpers import send_message, get_user_name, random_fun_fact
from utils.date_utils import parse_human_date

app = FastAPI()

VERIFY_TOKEN = "barberbot_verify_token"
conversations = {}

@app.get("/")
async def home():
    return {"status": "ok", "message": "SecretarBOT v8 – Barber_Data Edition"}

@app.get("/webhook")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return {"error": "Invalid verification"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        for entry in data.get("entry", []):
            for msg in entry.get("messaging", []):
                if "message" in msg and "text" in msg["message"]:
                    psid = msg["sender"]["id"]
                    user_text = msg["message"]["text"]

                    if psid not in conversations:
                        conversations[psid] = []
                    conversations[psid].append({"role": "user", "content": user_text})

                    reply = generate_reply(conversations[psid])
                    conversations[psid].append({"role": "assistant", "content": reply})

                    try:
                        parsed = json.loads(reply)
                        if isinstance(parsed, dict) and parsed.get("action") == "create_booking":
                            service = parsed.get("service")
                            dt_raw = parsed.get("datetime")
                            barber = parsed.get("barber")
                            notes = parsed.get("notes", "")

                            dt = parse_human_date(dt_raw)
                            if not dt:
                                send_message(psid, "Може ли да уточните точния ден и час? 🙂")
                                continue

                            services = get_services()
                            duration = int(services.get(service.lower(), {}).get("duration", 30))
                            user_name = get_user_name(psid)

                            event_link = create_event(service, dt, duration, user_name, barber, notes)
                            update_clients(psid, user_name, service, barber, dt, notes)
                            append_history(user_name, service, barber, dt, notes, psid)

                            confirmation = (
                                f"✅ Записах ви за {service} при {barber} на {dt.strftime('%A, %d %B %Y %H:%M')}.\n"
                                f"Благодаря, че избрахте нашия салон, {user_name}! 💈✂️\n\n"
                                f"{random_fun_fact()}"
                            )
                            send_message(psid, confirmation)
                            conversations.pop(psid, None)
                            continue
                    except json.JSONDecodeError:
                        pass

                    send_message(psid, reply)

        return {"status": "ok"}
    except Exception as e:
        print("❌ ERROR:", e)
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)
