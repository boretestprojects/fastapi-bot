import re
from datetime import datetime, timedelta
import pytz
from dateutil import parser as dateparser

OSLO = pytz.timezone("Europe/Oslo")

_BG_DAYS = {
    "понеделник":"mon","вторник":"tue","сряда":"wed",
    "четвъртък":"thu","петък":"fri","събота":"sat","неделя":"sun"
}
_NO_DAYS = {
    "mandag":"mon","tirsdag":"tue","onsdag":"wed","torsdag":"thu",
    "fredag":"fri","lørdag":"sat","søndag":"sun"
}
_ALL = ["mon","tue","wed","thu","fri","sat","sun"]

def _next_weekday(base, target3):
    idx = _ALL.index(target3)
    cur = base.weekday()
    delta = (idx - cur) % 7
    if delta == 0: delta = 7
    return base + timedelta(days=delta)

def parse_human_date(text: str):
    t = text.lower().strip()
    now = datetime.now(OSLO)

    # утре / i morgen
    if "утре" in t or "i morgen" in t or "imorgen" in t:
        m = re.search(r"(\d{1,2})([:\.](\d{2}))?", t)
        hh, mm = (int(m.group(1)), int(m.group(3) or 0)) if m else (12,0)
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=1)

    # след X часа/минути
    m = re.search(r"след\s+(\d{1,2})\s*час", t)
    if m:
        h = int(m.group(1))
        m2 = re.search(r"и\s*(\d{1,2})\s*мин", t)
        mins = int(m2.group(1)) if m2 else 0
        return now + timedelta(hours=h, minutes=mins)

    # дни от седмицата
    for full, abbr in {**_BG_DAYS, **_NO_DAYS}.items():
        if full in t:
            m = re.search(r"(\d{1,2})([:\.](\d{2}))?", t)
            hh, mm = (int(m.group(1)), int(m.group(3) or 0)) if m else (12,0)
            target = _next_weekday(now, abbr)
            return target.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # fallback към dateutil
    try:
        dt = dateparser.parse(t, dayfirst=True, fuzzy=True)
        if not dt:
            return None
        dt = OSLO.localize(dt) if dt.tzinfo is None else dt.astimezone(OSLO)
        return dt
    except Exception:
        return None
