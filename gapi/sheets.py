import os
import json
from datetime import datetime   # 👈 това е важното
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz
# ===== BARBER SCHEDULE VALIDATION (Final Stable) =====
def is_barber_available(barber_name: str, dt: datetime, service_name: str):
    """
    Проверява дали даден бръснар работи в съответния ден/час и дали предлага услугата.
    Работи стабилно с формати "Tue–Sat", "Mon-Sun" и реален час по таймзона Europe/Oslo.
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Barbers!A2:E"
    ).execute()
    values = result.get("values", [])

    # Взимаме реално време по норвежка зона
    tz = pytz.timezone("Europe/Oslo")
    local_dt = dt.astimezone(tz)

    day = local_dt.strftime("%a").lower()[:3]  # напр. "wed"
    time_str = local_dt.strftime("%H:%M")

    # ---- вътрешна функция за нормализация на диапазони
    def expand_days(days_text):
        all_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        days_text = days_text.lower().replace("–", "-").strip()

        # единичен ден
        if "-" not in days_text:
            return [days_text[:3]]

        # диапазон, напр. "tue-sat"
        start, end = [x.strip()[:3] for x in days_text.split("-")]
        if start not in all_days or end not in all_days:
            return all_days  # ако не може да разчете — приема целата седмица

        i1, i2 = all_days.index(start), all_days.index(end)
        return all_days[i1:i2 + 1] if i1 <= i2 else all_days[i1:] + all_days[:i2 + 1]

    # ---- основна логика
    for row in values:
        if len(row) < 4:
            continue

        name, work_days, start, end = row[:4]
        restricted = row[4] if len(row) > 4 else ""

        if barber_name.lower() in name.lower():
            valid_days = expand_days(work_days)
            # Проверка по ден
            if day not in valid_days:
                print(f"⚠️ {barber_name} не работи в {day.upper()} (Работи: {work_days})")
                return False

            # Проверка по час
            if not (start <= time_str <= end):
                print(f"⚠️ {barber_name} не е на работа в {time_str} (Работи {start}-{end})")
                return False

            # Проверка за ограничения по услуги
            if service_name and restricted and service_name.lower() in restricted.lower():
                print(f"⚠️ {barber_name} не предлага {service_name}")
                return False

            return True

    print(f"⚠️ {barber_name} не е намерен в Barbers листа.")
    return False
