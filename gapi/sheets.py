import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
creds_data = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = service_account.Credentials.from_service_account_info(
    creds_data,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
service = build("sheets", "v4", credentials=creds)

def get_services():
    result = service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="Services!A2:C").execute()
    values = result.get("values", [])
    return {r[0].lower(): {"price": r[1], "duration": r[2]} for r in values if len(r) >= 3}

def update_clients(psid, name, service_name, barber, date, notes):
    body = {"values": [[psid, name, service_name, barber, date.strftime("%Y-%m-%d %H:%M"), notes]]}
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range="Clients!A2",
        valueInputOption="USER_ENTERED", body=body).execute()

def append_history(name, service_name, barber, date, notes, psid):
    body = {"values": [[date.strftime("%Y-%m-%d %H:%M"), name, service_name, barber, notes, psid]]}
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range="History!A2",
        valueInputOption="USER_ENTERED", body=body).execute()
