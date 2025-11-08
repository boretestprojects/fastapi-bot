import os, json
from datetime import timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

creds_data = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = service_account.Credentials.from_service_account_info(
    creds_data,
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=creds)

def create_event(name, service, barber, dt_obj, duration, notes):
    end = dt_obj + timedelta(minutes=duration)
    event = {
        "summary": f"{name} – {service} ({barber})",
        "description": notes,
        "start": {"dateTime": dt_obj.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    print("📅 Calendar event created:", dt_obj)
