from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
import os, json, traceback, re
from datetime import datetime
from ai.chat import generate_reply
from gapi.sheets import get_services, update_clients, append_history, is_barber_available
from gapi.calendar import create_event
from utils.helpers import send_message, get_user_name, random_fun_fact
from utils.date_utils import parse_human_date

app = FastAPI()

VERIFY_TOKEN = "barberbot_verify_token"
conversations = {}

@app.get("/")
async def home():
    return {"status": "ok", "message": "SecretarBOT v9 – Stable Booking Edition"}

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
                    user_text = msg["message"]["text"].strip()

                    # 🧠 Запис в разговорната памет
                    if psid not in conversations:
                        conversations[psid] = []
                    conversations[psid].append({"role": "user", "content": user_text})

                    # 🤖 Генерираме AI отговор
                    reply = generate_reply(conversations[psid])
                    conversations[psid].append({"role": "assistant", "content": reply})

                    # 🔍 Проверка за JSON структура в отговора
                    match = re.search(r'\{[^{}]*"action"\s*:\s*"create_booking"[^{}]*\}', reply)
                    if match:
                        try:
                            parsed = json.loads(match.group(0))
                        except Exception:
                            send_message(psid, "Имаше нещо неясно в резервацията. Може ли да я повториш?")
                            continue

                        service = parsed.get("service")
                        dt_raw = parsed.get("datetime")
                        barber = parsed.get("barber")
                        notes = parsed.get("notes", "")

                        # 🧾 Проверяваме дали има нужните данни
                        if not all([service, dt_raw, barber]):
                            send_message(psid, "Хмм... липсва информация (услуга, дата или бръснар). Може ли пак?")
                            continue

                        # 📅 Валидираме и конвертираме дата
                        dt = parse_human_date(dt_raw)
                        if not dt:
                            send_message(psid, "Не съм сигурен коя дата имаш предвид. Може ли точен ден и час?")
                            continue

                        # 🧭 Проверка дали бръснарят е на работа
                        if not is_barber_available(barber, dt, service):
                            send_message(psid, f"⚠️ {barber} не е на работа по това време. Избери друг ден или бръснар 🙂")
                            continue

                        # ✅ Потвърждение преди запис
                        confirm_msg = (
                            f"Да потвърдя ли: {service} при {barber} на {dt.strftime('%A, %d %B %Y %H:%M')}? "
                            f"Отговори с „да“, „ок“ или „yes“ за потвърждение. 💈"
                        )
                        send_message(psid, confirm_msg)

                        # 💾 Запазваме pending резервация (datetime като текст)
                        conversations[psid].append({
                            "role": "system",
                            "pending_booking": {
                                "service": service,
                                "barber": barber,
                                "datetime": dt.isoformat(),  # ✅ сериализирано безопасно
                                "notes": notes
                            }
                        })
                        continue

                    # 💬 Потвърждение от потребителя
                    if user_text.lower() in ["да", "yes", "ok", "ок", "potvurdavam", "confirm"]:
                        for item in reversed(conversations[psid]):
                            if isinstance(item, dict) and "pending_booking" in item:
                                b = item["pending_booking"]
                                from datetime import datetime
                                dt = datetime.fromisoformat(b["datetime"])  # ✅ обратно към datetime
                                service = b["service"]
                                barber = b["barber"]
                                notes = b.get("notes", "")
                                user_name = get_user_name(psid)

                                # 🗓️ Създаване на събитие в Google Calendar
                                event_link = create_event(service, dt, 30, user_name, barber, notes)
                                if not event_link:
                                    send_message(psid, f"⚠️ {barber} не е на работа тогава. Опитай друг ден.")
                                    break

                                # 📋 Запис в Google Sheets
                                update_clients(psid, user_name, service, barber, dt, notes)
                                append_history(user_name, service, barber, dt, notes, psid)

                                # 🎉 Потвърждение + забавен факт
                                fact = random_fun_fact()
                                send_message(psid, (
                                    f"✅ Записах те за {service} при {barber} на {dt.strftime('%A, %d %B %Y %H:%M')}!\n"
                                    f"Благодарим, {user_name}! 💈✂️\n\n{fact}"
                                ))
                                break
                        continue

                    # ако няма JSON → просто изпращаме отговора
                    send_message(psid, reply)

        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR:", e)
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/debug/conversations")
async def debug_conversations():
    """Преглед на активните разговори"""
    return conversations
