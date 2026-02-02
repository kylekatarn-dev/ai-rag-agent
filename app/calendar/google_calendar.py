"""Google Calendar API integration using Service Account."""

import json
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from app.config import (
    GOOGLE_CALENDAR_ENABLED,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_CALENDAR_ID,
    BROKER_NAME,
    BROKER_EMAIL,
)


# Singleton instance
_calendar_service: Optional["GoogleCalendarService"] = None


def get_calendar_service() -> "GoogleCalendarService":
    """Get or create the calendar service singleton."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = GoogleCalendarService()
    return _calendar_service


class GoogleCalendarService:
    """
    Google Calendar service for checking availability and booking meetings.

    Uses a service account to access the broker's calendar without
    requiring client authorization.
    """

    def __init__(self):
        self.enabled = GOOGLE_CALENDAR_ENABLED
        self.calendar_id = GOOGLE_CALENDAR_ID
        self.service = None

        if self.enabled:
            self._initialize_service()

    def _initialize_service(self):
        """Initialize the Google Calendar API service."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            service_account_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)

            if not service_account_path.exists():
                print(f"Warning: Service account file not found: {service_account_path}")
                self.enabled = False
                return

            SCOPES = ['https://www.googleapis.com/auth/calendar']

            credentials = service_account.Credentials.from_service_account_file(
                str(service_account_path),
                scopes=SCOPES
            )

            self.service = build('calendar', 'v3', credentials=credentials)
            print("Google Calendar service initialized successfully")

        except ImportError:
            print("Warning: google-api-python-client not installed. Run: pip install google-api-python-client google-auth")
            self.enabled = False
        except Exception as e:
            print(f"Warning: Failed to initialize Google Calendar: {e}")
            self.enabled = False

    def is_available(self) -> bool:
        """Check if the calendar service is available and working."""
        return self.enabled and self.service is not None

    def get_available_slots(
        self,
        days_ahead: int = 7,
        slot_duration_minutes: int = 30,
        working_hours_start: int = 9,
        working_hours_end: int = 17,
    ) -> list[dict]:
        """
        Get available time slots for the next N days.

        Args:
            days_ahead: Number of days to look ahead
            slot_duration_minutes: Duration of each slot (15, 30, or 60)
            working_hours_start: Start of working hours (9 = 9:00)
            working_hours_end: End of working hours (17 = 17:00)

        Returns:
            List of available slots with start/end times
        """
        if not self.is_available():
            return self._get_simulated_slots(days_ahead, slot_duration_minutes)

        try:
            # Define time range
            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'

            # Get busy times using freebusy query
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": self.calendar_id}]
            }

            freebusy = self.service.freebusy().query(body=body).execute()
            busy_times = freebusy.get('calendars', {}).get(self.calendar_id, {}).get('busy', [])

            # Generate all possible slots
            available_slots = []
            current_date = now.date()

            for day_offset in range(days_ahead):
                check_date = current_date + timedelta(days=day_offset)

                # Skip weekends
                if check_date.weekday() >= 5:
                    continue

                # Generate slots for this day
                for hour in range(working_hours_start, working_hours_end):
                    for minute in [0, 30] if slot_duration_minutes == 30 else [0]:
                        slot_start = datetime.combine(
                            check_date,
                            datetime.min.time().replace(hour=hour, minute=minute)
                        )
                        slot_end = slot_start + timedelta(minutes=slot_duration_minutes)

                        # Skip if slot is in the past
                        if slot_start <= now:
                            continue

                        # Skip if slot ends after working hours
                        if slot_end.hour >= working_hours_end and slot_end.minute > 0:
                            continue

                        # Check if slot conflicts with busy times
                        is_free = True
                        for busy in busy_times:
                            busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00')).replace(tzinfo=None)
                            busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00')).replace(tzinfo=None)

                            if slot_start < busy_end and slot_end > busy_start:
                                is_free = False
                                break

                        if is_free:
                            available_slots.append({
                                "start": slot_start,
                                "end": slot_end,
                                "display": self._format_slot(slot_start, slot_end),
                            })

            return available_slots[:20]  # Limit to 20 slots

        except Exception as e:
            print(f"Error fetching calendar availability: {e}")
            return self._get_simulated_slots(days_ahead, slot_duration_minutes)

    def _get_simulated_slots(
        self,
        days_ahead: int = 7,
        slot_duration_minutes: int = 30,
    ) -> list[dict]:
        """Generate simulated available slots when calendar is not available."""
        slots = []
        now = datetime.now()
        current_date = now.date()

        # Generate some realistic-looking slots
        for day_offset in range(1, days_ahead + 1):
            check_date = current_date + timedelta(days=day_offset)

            # Skip weekends
            if check_date.weekday() >= 5:
                continue

            # Add 2-3 slots per day
            for hour in [9, 11, 14, 16]:
                if len(slots) >= 12:
                    break

                slot_start = datetime.combine(
                    check_date,
                    datetime.min.time().replace(hour=hour, minute=0)
                )
                slot_end = slot_start + timedelta(minutes=slot_duration_minutes)

                slots.append({
                    "start": slot_start,
                    "end": slot_end,
                    "display": self._format_slot(slot_start, slot_end),
                })

        return slots

    def _format_slot(self, start: datetime, end: datetime) -> str:
        """Format a time slot for display."""
        day_names = {
            0: "Pondělí", 1: "Úterý", 2: "Středa",
            3: "Čtvrtek", 4: "Pátek", 5: "Sobota", 6: "Neděle"
        }
        day_name = day_names[start.weekday()]
        date_str = start.strftime("%d.%m.")
        time_str = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

        return f"{day_name} {date_str} {time_str}"

    def create_meeting(
        self,
        start_time: datetime,
        duration_minutes: int = 30,
        client_email: str = None,
        client_name: str = None,
        meeting_type: str = "call",
        notes: str = None,
    ) -> dict:
        """
        Create a calendar event for a meeting.

        Args:
            start_time: Meeting start time
            duration_minutes: Meeting duration
            client_email: Client's email (for invite)
            client_name: Client's name
            meeting_type: "call", "video", or "meeting"
            notes: Additional notes

        Returns:
            Dict with event details or error
        """
        end_time = start_time + timedelta(minutes=duration_minutes)

        meeting_titles = {
            "call": f"Telefonát: {client_name or 'Klient'}",
            "video": f"Videohovor: {client_name or 'Klient'}",
            "meeting": f"Schůzka: {client_name or 'Klient'}",
        }

        title = meeting_titles.get(meeting_type, f"Schůzka: {client_name or 'Klient'}")

        if not self.is_available():
            # Return simulated response
            return {
                "success": True,
                "simulated": True,
                "event_id": "simulated_123",
                "title": title,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "display": self._format_slot(start_time, end_time),
                "message": f"Schůzka naplánována na {self._format_slot(start_time, end_time)}",
            }

        try:
            event = {
                'summary': title,
                'description': f"""
Klient: {client_name or 'Neuvedeno'}
Email: {client_email or 'Neuvedeno'}
Typ: {meeting_type}
Poznámky: {notes or 'Žádné'}

Vytvořeno automaticky AI asistentem.
                """.strip(),
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'Europe/Prague',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'Europe/Prague',
                },
            }

            # Add client as attendee if email provided
            if client_email:
                event['attendees'] = [
                    {'email': client_email, 'displayName': client_name or client_email}
                ]
                # Send email notification
                event['sendUpdates'] = 'all'

            # Add video conference for video meetings
            if meeting_type == "video":
                event['conferenceData'] = {
                    'createRequest': {
                        'requestId': f"meet_{start_time.timestamp()}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                }

            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event,
                conferenceDataVersion=1 if meeting_type == "video" else 0,
                sendUpdates='all' if client_email else 'none',
            ).execute()

            # Extract meet link if video call
            meet_link = None
            if meeting_type == "video" and 'conferenceData' in created_event:
                entry_points = created_event['conferenceData'].get('entryPoints', [])
                for ep in entry_points:
                    if ep.get('entryPointType') == 'video':
                        meet_link = ep.get('uri')
                        break

            return {
                "success": True,
                "simulated": False,
                "event_id": created_event.get('id'),
                "title": title,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "display": self._format_slot(start_time, end_time),
                "html_link": created_event.get('htmlLink'),
                "meet_link": meet_link,
                "message": f"Schůzka vytvořena: {self._format_slot(start_time, end_time)}",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Nepodařilo se vytvořit schůzku: {e}",
            }

    def format_available_slots_for_display(
        self,
        slots: list[dict],
        max_display: int = 6,
    ) -> str:
        """Format available slots for chat display."""
        if not slots:
            return "Momentálně nemám dostupné žádné termíny. Zkuste prosím kontaktovat makléře přímo."

        lines = ["**Dostupné termíny:**\n"]

        # Group by date
        current_date = None
        displayed = 0

        for slot in slots:
            if displayed >= max_display:
                remaining = len(slots) - displayed
                if remaining > 0:
                    lines.append(f"\n... a dalších {remaining} termínů")
                break

            slot_date = slot["start"].date()
            if slot_date != current_date:
                current_date = slot_date
                day_names = {0: "Po", 1: "Út", 2: "St", 3: "Čt", 4: "Pá"}
                day_name = day_names.get(slot_date.weekday(), "")
                lines.append(f"\n**{day_name} {slot_date.strftime('%d.%m.')}:**")

            time_str = f"{slot['start'].strftime('%H:%M')}"
            lines.append(f"  - {time_str}")
            displayed += 1

        return "\n".join(lines)
