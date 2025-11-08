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
service = build("calendar", "v3", credentials=creds)

def create_event(service_name, start_dt, duration, user_name, barber, notes):
    event = {
        "summary": f"{user_name} – {service_name} ({barber})",
        "description": notes,
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": (start_dt + timedelta(minutes=duration)).isoformat()},
    }
    result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return result.get("htmlLink", "")
