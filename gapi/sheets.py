import os
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
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


# ===== BARBER SCHEDULE VALIDATION (Improved) =====
def is_barber_available(barber_name: str, dt: datetime, service_name: str):
    """
    Проверява дали даден бръснар работи в съответния ден/час и дали предлага услугата.
    Работи с диапазони от типа "Tue–Sat" и валидира реално време по таймзона.
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Barbers!A2:E"
    ).execute()
    values = result.get("values", [])

    # ден от седмицата (напр. "wed")
    day = dt.strftime("%a").lower()  # mon, tue, wed...
    time_str = dt.strftime("%H:%M")

    # конвертор от текстови диапазони "Tue–Sat"
    def expand_days(days_text):
        days_text = days_text.lower().strip()
        all_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        # ако е отделен ден (напр. "wed")
        if "-" not in days_text and "–" not in days_text:
            return [days_text]

        # ако е диапазон (напр. "tue–sat" или "fri-mon")
        days_text = days_text.replace("–", "-")
        start, end = [x.strip()[:3] for x in days_text.split("-")]
        i1, i2 = all_days.index(start), all_days.index(end)

        if i1 <= i2:
            return all_days[i1:i2 + 1]
        else:
            # ако диапазонът минава през неделя, напр. Fri–Mon
            return all_days[i1:] + all_days[:i2 + 1]

    for row in values:
        if len(row) < 4:
            continue

        name, work_days, start, end = row[:4]
        restricted = row[4] if len(row) > 4 else ""

        # съвпадение по име
        if barber_name.lower() in name.lower():
            valid_days = expand_days(work_days)

            # ден от седмицата
            if day not in valid_days:
                print(f"⚠️ {barber_name} не работи в {day}. Работни дни: {work_days}")
                return False

            # работен час
            if not (start <= time_str <= end):
                print(f"⚠️ {barber_name} не е на работа в {time_str}. Работи {start}-{end}")
                return False

            # ограничения за услуги
            if service_name and service_name.lower() in restricted.lower():
                print(f"⚠️ {barber_name} не предлага {service_name}")
                return False

            return True

    print(f"⚠️ {barber_name} не е намерен в списъка.")
    return False
