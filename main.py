from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
import os, json, traceback, re
from datetime import datetime
from ai.chat import generate_reply
from gapi.sheets import get_services, update_clients, append_history
from gapi.calendar import create_event
from utils.helpers import send_message, get_user_name, random_fun_fact
from utils.date_utils import parse_human_date

app = FastAPI()

VERIFY_TOKEN = "barberbot_verify_token"
conversations = {}

# ===== ROOT =====
@app.get("/")
async def home():
    return {"status": "ok", "message": "SecretarBOT v8 – Barber_Data Edition"}

# ===== VERIFY WEBHOOK =====
@app.get("/webhook")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return {"error": "Invalid verification"}

# ===== MAIN WEBHOOK =====
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

                    # 🧠 AI отговор
                    reply = generate_reply(conversations[psid])
                    conversations[psid].append({"role": "assistant", "content": reply})

                    # 🔍 търсим JSON за резервация дори ако има текст преди/след
                    try:
                        match = re.search(r'\{[^{}]*"action"\s*:\s*"create_booking"[^{}]*\}', reply)
                        if match:
                            parsed = json.loads(match.group(0))

                            service = parsed.get("service")
                            dt_raw = parsed.get("datetime")
                            barber = parsed.get("barber")
                            notes = parsed.get("notes", "")

                            # 🔢 валидираме дата/час
                            dt = parse_human_date(dt_raw)
                            if not dt:
                                send_message(psid, "Хмм... не съм сигурен кога точно искаш. Може ли да ми кажеш точния ден и час? 🙂")
                                continue

                            # 🧾 данни за услугата
                            services = get_services()
                            duration = int(services.get(service.lower(), {}).get("duration", 30))

                            # 🧑‍🦱 клиентско име
                            user_name = get_user_name(psid)

                            # 🗓️ Създаваме събитие в Google Calendar
                            event_link = create_event(service, dt, duration, user_name, barber, notes)

                            if not event_link:
                                send_message(psid, f"⚠️ {barber} не е на смяна тогава. Избери друг ден или бръснар 🙂")
                                continue

                            # 🧾 Запис в Sheets (Clients + History)
                            update_clients(psid, user_name, service, barber, dt, notes)
                            append_history(user_name, service, barber, dt, notes, psid)

                            # 🎉 Потвърждение + забавен факт
                            fact = random_fun_fact()
                            confirmation = (
                                f"✅ Записах те за {service} при {barber} на {dt.strftime('%A, %d %B %Y %H:%M')}.\n"
                                f"Ще се радваме да те видим, {user_name}! 💈✂️\n\n"
                                f"{fact}"
                            )
                            send_message(psid, confirmation)
                            continue

                    except Exception:
                        pass

                    # ако не е JSON → просто изпращаме отговора
                    send_message(psid, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR:", e)
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)

# ===== DEBUG ENDPOINT =====
@app.get("/debug/conversations")
async def debug_conversations():
    """Виж последните разговори в реално време"""
    return conversations
