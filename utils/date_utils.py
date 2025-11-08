from datetime import datetime, timedelta
import re
from dateutil import parser
import pytz

# Норвежка часова зона (можеш да смениш ако искаш)
LOCAL_TZ = pytz.timezone("Europe/Oslo")

def parse_human_date(text: str):
    """Парсва човешки израз за време като 'утре в 11', 'в сряда 14:00', '18 ноември 10:30'"""
    text = text.lower().strip()

    now = datetime.now(LOCAL_TZ)

    # --- думи за дни ---
    days_map = {
        "понеделник": 0, "вторник": 1, "сряда": 2, "четвъртък": 3,
        "петък": 4, "събота": 5, "неделя": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    # --- относителни думи ---
    if "утре" in text:
        base = now + timedelta(days=1)
    elif "вдругиден" in text:
        base = now + timedelta(days=2)
    elif "днес" in text:
        base = now
    else:
        base = now

    # --- проверка за конкретен ден от седмицата ---
    for day_name, weekday in days_map.items():
        if day_name in text:
            diff = (weekday - base.weekday() + 7) % 7
            if diff == 0:
                diff = 7  # следващия същия ден
            base = base + timedelta(days=diff)
            break

    # --- час ---
    hour, minute = 10, 0  # по подразбиране
    time_match = re.search(r"(\d{1,2})([:.](\d{2}))?", text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(3)) if time_match.group(3) else 0

    # корекция: ако е само "11" без AM/PM → 11 сутринта
    if "вечер" in text or "pm" in text and hour < 12:
        hour += 12
    if "сутрин" in text or "am" in text and hour >= 12:
        hour -= 12

    final_dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return final_dt

