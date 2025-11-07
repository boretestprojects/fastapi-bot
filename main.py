from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import requests
import os

app = FastAPI()

# ===== CONFIG =====
VERIFY_TOKEN = "barberbot_verify_token"  # това ще въведеш в Meta Developer
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ===== WEBHOOK VERIFY =====
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        # Важно: Meta очаква отговор в текстов формат, не като число
        return PlainTextResponse(challenge)
    return {"error": "Invalid verification"}


# ===== WEBHOOK EVENTS =====
@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    print("📩 Incoming message:", data)

    if "entry" in data:
        for entry in data["entry"]:
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event["sender"]["id"]
                if "message" in messaging_event and "text" in messaging_event["message"]:
                    user_message = messaging_event["message"]["text"]

                    # Викаме ChatGPT API
                    reply = chatgpt_reply(user_message)

                    # Пращаме обратно в Messenger
                    send_message(sender_id, reply)

    return {"status": "ok"}


# ===== OPENAI (ChatGPT) =====
def chatgpt_reply(user_message):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a friendly barber shop assistant. Respond in the user's language."},
            {"role": "user", "content": user_message}
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    return data["choices"][0]["message"]["content"]


# ===== FACEBOOK (SEND MESSAGE) =====
def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    response = requests.post(url, json=payload)
    print("📤 Sent message:", response.text)
