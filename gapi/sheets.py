import os, json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

creds_data = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = service_account.Credentials.from_service_account_info(
    creds_data,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets_service = build("sheets", "v4", credentials=creds)

def get_services():
    data = sheets_service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="Services!A2:C"
    ).execute().get("values", [])
    return {r[0].lower(): {"price": r[1], "duration": int(r[2]) if len(r) > 2 else 30} for r in data}

def update_clients(psid, name, service, barber, dt, notes):
    body = {"values": [[psid, name, service, barber, dt, notes]]}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="Clients!A:F",
        valueInputOption="RAW",
        body=body
    ).execute()

def append_history(name, service, barber, dt, notes, psid):
    body = {"values": [[dt, name, service, barber, notes, psid]]}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="History!A:F",
        valueInputOption="RAW",
        body=body
    ).execute()
