from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Sequence, Set

from .config import Config
from .gateways import BlueBubblesClient, GWSClient
from .runtime import (
    CALENDAR_RE,
    append_upcoming_event_row,
    sanitize_action_text,
    sanitize_field,
    write_markdown_file,
)


class ActionDispatcher:
    def __init__(self, config: Config, gws: GWSClient, messenger: BlueBubblesClient):
        self.config = config
        self.gws = gws
        self.messenger = messenger

    def build_school_calendar_payload(
        self,
        date: str,
        title: str,
        notes: str,
        start_time: str = "",
        end_time: str = "",
    ) -> Dict[str, Any]:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
            raise ValueError("invalid school event date")
        summary = f"School: {title}"
        if not start_time and not end_time:
            return {
                "summary": summary,
                "description": notes,
                "start": {"date": date},
                "end": {"date": date},
            }

        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time or ""):
            raise ValueError("invalid school event start_time")
        start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")

        if end_time:
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end_time):
                raise ValueError("invalid school event end_time")
            end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        else:
            end_dt = start_dt + timedelta(minutes=self.config.school_event_default_duration_minutes)

        if end_dt <= start_dt:
            raise ValueError("school event end_time must be after start_time")

        return {
            "summary": summary,
            "description": notes,
            "start": {
                "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": self.config.default_calendar_timezone,
            },
            "end": {
                "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": self.config.default_calendar_timezone,
            },
        }

    def execute_scheduled_actions(self, actions: Sequence[Dict[str, Any]], allowed_actions: Set[str]) -> None:
        for item in actions:
            action = item.get("action", "")
            if action not in allowed_actions:
                print(f"[SECURITY BLOCKED] action '{action}' is not permitted for this automation.")
                continue
            try:
                if action == "task":
                    self._create_task(item)
                elif action == "calendar_event":
                    self._create_calendar_event(item)
                elif action == "school_calendar_event":
                    self._create_school_calendar_event(item)
                elif action == "file_append":
                    self._append_file(item)
                elif action == "notify":
                    self._notify(item)
                elif action == "upcoming_event":
                    self._upcoming_event(item)
                else:
                    print(f"[SECURITY BLOCKED] unknown scheduled action '{action}'")
            except Exception as exc:
                print(f"[SECURITY BLOCKED] action '{action}' failed validation: {exc}")

    def execute_message_actions(self, actions: Sequence[Dict[str, Any]], raw_text: str) -> None:
        allowed = {"task", "calendar_event", "availability_append", "meal_plan_write", "session_log_append"}
        for item in actions:
            action = item.get("action", "")
            if action not in allowed:
                print(f"[SECURITY BLOCKED] unsupported message action '{action}'")
                continue
            if action == "task":
                self._create_task(item)
            elif action == "calendar_event":
                if not CALENDAR_RE.search(raw_text or ""):
                    print("[SECURITY BLOCKED] calendar_event omitted without explicit calendar language")
                    continue
                self._create_calendar_event(item)
            elif action == "availability_append":
                self._append_markdown("Projects/Availability.md", sanitize_action_text(item.get("content", ""), 1000))
            elif action == "meal_plan_write":
                content = (item.get("content", "") or "").replace("\x00", "")
                if not content.strip():
                    raise RuntimeError("meal_plan_write content was empty")
                write_markdown_file(self.config, "Projects/Meal Planning.md", content, "write")
            elif action == "session_log_append":
                self._append_markdown("Briefs/Session Log.md", sanitize_action_text(item.get("content", ""), 1200))

    def _create_task(self, item: Dict[str, Any]) -> None:
        title = sanitize_field(str(item.get("title", "")), 200)
        due = str(item.get("due", "") or "")
        notes = sanitize_field(str(item.get("notes", "")), 500)
        payload: Dict[str, Any] = {"title": title, "notes": notes}
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            payload["due"] = f"{due}T12:00:00Z"
        self.gws.insert_task(payload)

    def _create_calendar_event(self, item: Dict[str, Any]) -> None:
        summary = sanitize_field(str(item.get("summary") or item.get("title", "")), 200)
        date = str(item.get("date", "") or "")
        description = sanitize_field(str(item.get("description") or item.get("notes", "")), 500)
        self.gws.insert_calendar_payload(
            {
                "summary": summary,
                "description": description,
                "start": {"date": date},
                "end": {"date": date},
            }
        )

    def _create_school_calendar_event(self, item: Dict[str, Any]) -> None:
        payload = self.build_school_calendar_payload(
            date=str(item.get("date", "") or ""),
            title=sanitize_field(str(item.get("title") or item.get("summary", "")), 200),
            notes=sanitize_field(str(item.get("notes") or item.get("description", "")), 400),
            start_time=str(item.get("start_time", "") or ""),
            end_time=str(item.get("end_time", "") or ""),
        )
        self.gws.insert_calendar_payload(payload)

    def _append_file(self, item: Dict[str, Any]) -> None:
        file_path = str(item.get("path", "") or "")
        blocked = ("_AI_CONTEXT.md", "Context/", "recipes/", "scripts/")
        if any(part in file_path for part in blocked) or file_path.endswith((".sh", ".py", ".c", ".env")):
            raise PermissionError(f"file_append not allowed for: {file_path}")
        content = sanitize_field(str(item.get("content", "")), 1000)
        self._append_markdown(file_path, content)

    def _notify(self, item: Dict[str, Any]) -> None:
        self.messenger.send_message(
            self.config.default_chat_guid,
            sanitize_field(str(item.get("message", "")), 500),
            context_label="notify",
        )

    def _upcoming_event(self, item: Dict[str, Any]) -> None:
        date = str(item.get("date", "") or "")
        title = sanitize_field(str(item.get("title", "")), 200)
        kid = sanitize_field(str(item.get("kid", "—")), 20)
        notes = sanitize_field(str(item.get("notes", "")), 300)
        append_upcoming_event_row(self.config, f"| {date} | {kid} | {title} | {notes} |")

    def _append_markdown(self, relative_path: str, content: str) -> None:
        write_markdown_file(self.config, relative_path, content, "append")
