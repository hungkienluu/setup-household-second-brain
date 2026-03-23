from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_flag(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class Config:
    vault_root: Path
    gemini_bin: str
    gws_bin: str
    model_pro: str
    model_flash: str
    model_message: str
    enforce_send_auth: bool
    internal_send_token: str
    gemini_approval_mode_safe: str
    gemini_approval_mode_default: str
    enable_daily_brief_gmail_context: bool
    enable_school_assistant_calendar_events: bool
    default_calendar_timezone: str
    school_event_default_duration_minutes: int
    bb_password: str
    webhook_token: str
    send_api_token: str
    tasklist_id: str
    daily_brief_recipients: Tuple[str, ...]
    default_chat_guid: str
    valid_handles: Tuple[str, ...]
    runtime_home: str
    runtime_user: str

    @property
    def scripts_dir(self) -> Path:
        return self.vault_root / "scripts"

    @property
    def recipes_dir(self) -> Path:
        return self.vault_root / "recipes"

    @property
    def log_file(self) -> Path:
        return self.vault_root / "HOUSEHOLD_AI.log"

    @property
    def bluebubbles_url(self) -> str:
        return "http://127.0.0.1:1234/api/v1/message/text"

    def recipe_path(self, name: str) -> Path:
        return self.recipes_dir / name

    @classmethod
    def load(cls, environ: Dict[str, str] | None = None) -> "Config":
        base_env = dict(os.environ if environ is None else environ)
        default_root = Path(__file__).resolve().parents[1]
        home_dir = Path(base_env.get("HOME") or Path.home())
        file_env = _read_env_file(home_dir / ".household.env")
        merged = dict(file_env)
        merged.update(base_env)

        vault_root = Path(merged.get("VAULT_ROOT", str(default_root)))
        send_token = merged.get("SEND_API_TOKEN") or merged.get("WEBHOOK_TOKEN", "")
        recipients = tuple(
            item.strip()
            for item in merged.get("DAILY_BRIEF_RECIPIENTS", "").split(",")
            if item.strip()
        )
        valid_handles = tuple(
            item.strip()
            for item in merged.get("VALID_IMESSAGE_HANDLES", "").split(",")
            if item.strip()
        )

        return cls(
            vault_root=vault_root,
            gemini_bin=merged.get("GEMINI", "gemini"),
            gws_bin=merged.get("GWS", "gws"),
            model_pro=merged.get("MODEL_PRO", "gemini-2.5-pro"),
            model_flash=merged.get("MODEL_FLASH", "gemini-2.5-flash"),
            model_message=merged.get("MODEL_MESSAGE", "gemini-2.5-flash"),
            enforce_send_auth=_env_flag(merged.get("ENFORCE_SEND_AUTH"), True),
            internal_send_token=merged.get("INTERNAL_SEND_TOKEN", send_token),
            gemini_approval_mode_safe=merged.get("GEMINI_APPROVAL_MODE_SAFE", "yolo"),
            gemini_approval_mode_default=merged.get("GEMINI_APPROVAL_MODE_DEFAULT", "yolo"),
            enable_daily_brief_gmail_context=_env_flag(merged.get("ENABLE_DAILY_BRIEF_GMAIL_CONTEXT"), False),
            enable_school_assistant_calendar_events=_env_flag(merged.get("ENABLE_SCHOOL_ASSISTANT_CALENDAR_EVENTS"), True),
            default_calendar_timezone=merged.get("DEFAULT_CALENDAR_TIMEZONE", "UTC"),
            school_event_default_duration_minutes=int(merged.get("SCHOOL_EVENT_DEFAULT_DURATION_MINUTES", "60")),
            bb_password=merged.get("BB_PASSWORD", ""),
            webhook_token=merged.get("WEBHOOK_TOKEN", ""),
            send_api_token=send_token,
            tasklist_id=merged.get("TASKLIST_ID", ""),
            daily_brief_recipients=recipients,
            default_chat_guid=merged.get("DEFAULT_CHAT_GUID", ""),
            valid_handles=valid_handles,
            runtime_home=merged.get("RUNTIME_HOME", str(home_dir)),
            runtime_user=merged.get("RUNTIME_USER", merged.get("USER", home_dir.name)),
        )

    def runtime_env(self, extra: Dict[str, str] | None = None) -> Dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "PATH": f"/usr/local/bin:/opt/homebrew/bin:{Path(self.gemini_bin).parent}:{env.get('PATH', '/bin:/usr/bin')}",
                "HOME": self.runtime_home,
                "USER": self.runtime_user,
                "VAULT_ROOT": str(self.vault_root),
                "GEMINI": self.gemini_bin,
                "GWS": self.gws_bin,
                "MODEL_PRO": self.model_pro,
                "MODEL_FLASH": self.model_flash,
            }
        )
        if extra:
            env.update(extra)
        return env


def iter_shell_exports(config: Config) -> Iterable[str]:
    yield f"export VAULT_ROOT={config.vault_root}"
    yield f"export GEMINI={config.gemini_bin}"
    yield f"export GWS={config.gws_bin}"

