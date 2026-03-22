from __future__ import annotations

import tempfile
from pathlib import Path

from app.config import Config
from app.gateways import CommandResult


def make_config(root: Path) -> Config:
    return Config(
        vault_root=root,
        gemini_bin="/usr/bin/false",
        gws_bin="/usr/bin/false",
        model_pro="pro",
        model_flash="flash",
        model_message="message",
        enforce_send_auth=True,
        internal_send_token="secret",
        gemini_approval_mode_safe="plan",
        gemini_approval_mode_default="plan",
        enable_daily_brief_gmail_context=False,
        enable_school_assistant_calendar_events=True,
        default_calendar_timezone="UTC",
        school_event_default_duration_minutes=60,
        bb_password="password",
        webhook_token="webhook-token",
        send_api_token="send-token",
        tasklist_id="tasklist",
        daily_brief_recipients=("a@example.com", "b@example.com"),
        default_chat_guid="family-chat",
        valid_handles=("contact-a", "contact-b"),
        runtime_home=str(root),
        runtime_user="tester",
    )


def seed_vault(root: Path) -> None:
    (root / "Projects").mkdir(parents=True, exist_ok=True)
    (root / "Briefs" / "daily").mkdir(parents=True, exist_ok=True)
    (root / "Briefs" / "weekly").mkdir(parents=True, exist_ok=True)
    (root / "Context").mkdir(parents=True, exist_ok=True)
    (root / "Projects" / "Pickups.md").write_text(
        "# Pickups\n\n## Upcoming Events\n| Date | Kid | Event | Notes |\n| --- | --- | --- | --- |\n"
    )
    (root / "Projects" / "Availability.md").write_text("# Availability\n")
    (root / "Projects" / "Meal Planning.md").write_text("# Meals\n")
    (root / "Projects" / "Tasks.md").write_text("# Tasks\n")
    (root / "Briefs" / "Session Log.md").write_text("# Session Log\n")
    (root / "Context" / "_AI_CONTEXT.md").write_text("# AI Context\n")


class FakeGWS:
    def __init__(self, agenda="agenda", tasks_table="tasks", gmail_listing="", gmail_messages=None):
        self.tasks = []
        self.calendar = []
        self.sent_mail = []
        self.agenda = agenda
        self.tasks_table = tasks_table
        self.gmail_listing = gmail_listing
        self.gmail_messages = gmail_messages or {}
        self.calls = []

    def insert_task(self, payload):
        self.calls.append(("insert_task", payload))
        self.tasks.append(payload)

    def insert_calendar_payload(self, payload):
        self.calls.append(("insert_calendar_payload", payload))
        self.calendar.append(payload)

    def send_raw_gmail(self, raw_message):
        self.calls.append(("send_raw_gmail", raw_message))
        self.sent_mail.append(raw_message)

    def calendar_agenda(self, days, fallback=""):
        self.calls.append(("calendar_agenda", days))
        return self.agenda or fallback

    def list_tasks(self, fallback=""):
        self.calls.append(("list_tasks", None))
        return self.tasks_table or fallback

    def list_gmail(self, query, max_results, fmt, fallback=""):
        self.calls.append(("list_gmail", query, max_results, fmt))
        return self.gmail_listing or fallback

    def get_gmail_message_json(self, message_id):
        self.calls.append(("get_gmail_message_json", message_id))
        return self.gmail_messages.get(message_id, f'{{"id": "{message_id}"}}')


class FakeMessenger:
    def __init__(self):
        self.messages = []

    def send_message(self, chat_guid, message, context_label="send"):
        self.messages.append((chat_guid, message, context_label))


class FakeGemini:
    def __init__(self, stdout, returncode: int = 0, stderr: str = ""):
        if isinstance(stdout, list):
            self.responses = list(stdout)
        else:
            self.responses = [stdout]
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def run_recipe(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("FakeGemini received more calls than configured responses")
        stdout = self.responses.pop(0)
        return CommandResult(self.returncode, stdout, self.stderr)
