from datetime import datetime, timedelta
from dateutil import parser as dateparser
import pytz

TIMEZONE = pytz.timezone("Europe/Oslo")

def parse_human_date(text: str) -> str:
    """
    Разпознава естествени изрази за дати (напр. 'утре в 15:00', 'Monday 13:30', '9 November 2025')
    и връща ISO формат (стринг).
    """
    try:
        dt = dateparser.parse(
            text,
            languages=["bg", "en", "no"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": datetime.now(TIMEZONE),
                "TIMEZONE": "Europe/Oslo",
                "RETURN_AS_TIMEZONE_AWARE": True,
            },
        )
        if dt and dt < datetime.now(TIMEZONE):
            dt += timedelta(days=7)
        return dt.isoformat()
    except Exception as e:
        print("❌ Date parse error:", e)
        fallback = datetime.now(TIMEZONE) + timedelta(days=1)
        fallback = fallback.replace(hour=13, minute=0, second=0, microsecond=0)
        return fallback.isoformat()
