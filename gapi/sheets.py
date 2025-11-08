import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
import pytz

# ===== AUTH CONFIG =====
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
creds_data = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = service_account.Credentials.from_service_account_info(
    creds_data,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
service = build("sheets", "v4", credentials=creds)

# ===== SERVICES =====
def get_services():
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Services!A2:C"
    ).execute()
    values = result.get("values", [])
    return {r[0].lower(): {"price": r[1], "duration": r[2]} for r in values if len(r) >= 3}

# ===== CLIENTS =====
def update_clients(psid, name, service_name, barber, date, notes):
    body = {"values": [[psid, name, service_name, barber, date.strftime("%Y-%m-%d %H:%M"), notes]]}
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range="Clients!A2",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

# ===== HISTORY =====
def append_history(name, service_name, barber, date, notes, psid):
    body = {"values": [[date.strftime("%Y-%m-%d %H:%M"), name, service_name, barber, notes, psid]]}
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range="History!A2",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

# ===== BARBER SCHEDULE VALIDATION =====
def is_barber_available(barber_name: str, dt: datetime, service_name: str):
    """Проверява дали даден бръснар работи в съответния ден/час и дали предлага услугата."""
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Barbers!A2:E"
    ).execute()
    values = result.get("values", [])

    day = dt.strftime("%a")  # Mon, Tue, Wed...
    time_str = dt.strftime("%H:%M")

    for row in values:
        if len(row) < 4:
            continue
        name, work_days, start, end = row[:4]
        restricted = row[4] if len(row) > 4 else ""

        # 🧩 проверка на име, ден, час и ограничения
        if barber_name.lower() in name.lower():
            if day[:3].lower() not in work_days.lower():
                return False
            if not (start <= time_str <= end):
                return False
            if service_name.lower() in restricted.lower():
                return False
            return True
    return False
