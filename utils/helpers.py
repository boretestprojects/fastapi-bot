import requests, os

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

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
