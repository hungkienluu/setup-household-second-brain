from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from .config import Config
from .runtime import escape_prompt_value


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class GWSClient:
    def __init__(self, config: Config):
        self.config = config

    def _run(self, args: Iterable[str], check: bool = False) -> CommandResult:
        result = subprocess.run(
            [self.config.gws_bin] + list(args),
            cwd=self.config.vault_root,
            env=self.config.runtime_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
        return CommandResult(result.returncode, result.stdout.strip(), result.stderr.strip())

    def _warn(self, label: str, result: "CommandResult") -> None:
        import sys
        print(f"[GWS:{label}] failed (rc={result.returncode}): {result.stderr[:200]}", file=sys.stderr)

    def calendar_agenda(self, days: int, fallback: str = "Error fetching calendar") -> str:
        result = self._run(["calendar", "+agenda", "--days", str(days)])
        if result.returncode != 0:
            self._warn("calendar_agenda", result)
            return fallback
        return result.stdout or fallback

    def list_tasks(self, fallback: str = "Error fetching tasks") -> str:
        result = self._run(
            [
                "tasks",
                "tasks",
                "list",
                "--params",
                json.dumps({"tasklist": self.config.tasklist_id}),
                "--format",
                "table",
            ]
        )
        if result.returncode != 0:
            self._warn("list_tasks", result)
            return fallback
        return result.stdout or fallback

    def list_gmail(self, query: str, max_results: int, fmt: str, fallback: str = "Error fetching mail") -> str:
        result = self._run(
            [
                "gmail",
                "users",
                "messages",
                "list",
                "--params",
                json.dumps({"userId": "me", "q": query, "maxResults": max_results}),
                "--format",
                fmt,
            ]
        )
        if result.returncode != 0:
            self._warn("list_gmail", result)
            return fallback
        return result.stdout or fallback

    def get_gmail_message_json(self, message_id: str) -> str:
        result = self._run(
            [
                "gmail",
                "users",
                "messages",
                "get",
                "--params",
                json.dumps({"userId": "me", "id": message_id}),
                "--format",
                "json",
            ],
            check=True,
        )
        return result.stdout

    def insert_task(self, payload: Dict[str, Any]) -> None:
        self._run(
            [
                "tasks",
                "tasks",
                "insert",
                "--params",
                json.dumps({"tasklist": self.config.tasklist_id}),
                "--json",
                json.dumps(payload),
            ],
            check=True,
        )

    def insert_calendar_payload(self, payload: Dict[str, Any]) -> None:
        self._run(
            [
                "calendar",
                "events",
                "insert",
                "--params",
                json.dumps({"calendarId": "primary"}),
                "--json",
                json.dumps(payload),
            ],
            check=True,
        )

    def send_raw_gmail(self, raw_message: str) -> None:
        encoded = base64.urlsafe_b64encode(raw_message.encode()).decode().rstrip("=")
        self._run(
            [
                "gmail",
                "users",
                "messages",
                "send",
                "--params",
                json.dumps({"userId": "me"}),
                "--json",
                json.dumps({"raw": encoded}),
            ],
            check=True,
        )


class GeminiClient:
    def __init__(self, config: Config):
        self.config = config

    def run_recipe(
        self,
        recipe_path: str,
        context: str,
        params: Dict[str, Any],
        model: str,
        approval_mode: str,
        output_format: Optional[str] = None,
    ) -> CommandResult:
        prompt_parts = [f'@"{recipe_path}"']
        for key, value in params.items():
            prompt_parts.append(f'{key}="{escape_prompt_value(value)}"')
        command = [
            self.config.gemini_bin,
            "--approval-mode",
            approval_mode,
            "-m",
            model,
        ]
        if output_format:
            command.extend(["--output-format", output_format])
        command.extend(["-p", " ".join(prompt_parts)])
        result = subprocess.run(
            command,
            cwd=self.config.vault_root,
            env=self.config.runtime_env(),
            input=context,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(result.returncode, result.stdout, result.stderr)


class BlueBubblesClient:
    def __init__(self, config: Config):
        self.config = config

    def send_message(self, chat_guid: str, message: str, context_label: str = "send") -> None:
        import urllib.parse
        url = self.config.bluebubbles_url + "?" + urllib.parse.urlencode({"password": self.config.bb_password})
        payload = json.dumps(
            {"chatGuid": chat_guid, "message": message, "tempGuid": f"temp-{int(time.time())}"}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as response:
            response.read()
        print(f"[BlueBubbles:{context_label}] sent message to {chat_guid}")
