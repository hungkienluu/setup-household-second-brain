from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import Config


PROMPT_INJECTION_RE = re.compile(
    r"(ignore[ ].*(instruction|previous|above|prior|prompt)|"
    r"disregard[ ].*(previous|above|prior|instruction)|"
    r"override[ ].*(prompt|instruction|system)|"
    r"^SYSTEM:|<<[A-Z]|```|<script|<iframe)",
    re.IGNORECASE,
)
SHELL_INJECTION_RE = re.compile(
    r"(curl [a-z]|wget [a-z]|/bin/|/usr/bin/|chmod [0-9+]|sudo |bash -|sh -c|zsh -c|\beval )"
)
MESSAGE_DELIMITER = "[MESSAGE]"
CALENDAR_RE = re.compile(r"\b(calendar|event|invite|appointment|schedule|remind|reminder)\b", re.IGNORECASE)
GREETING_RE = re.compile(r"^\s*(hi|hello|hey|good morning|good afternoon|good evening)\b[!. ]*$", re.IGNORECASE)


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")


def current_date_label() -> str:
    return datetime.now().strftime("%A, %B %d, %Y")


def sanitize_field(value: str, max_len: int = 200) -> str:
    text = (value or "")[:max_len]
    text = text.translate({ord(c): None for c in ';|&`$(){}\\'})
    if PROMPT_INJECTION_RE.search(text):
        return "[SANITIZED - injection pattern detected]"
    if SHELL_INJECTION_RE.search(text):
        return "[SANITIZED - shell pattern detected]"
    return text


def sanitize_action_text(value: str, max_len: int = 500) -> str:
    text = (value or "").replace("\r", " ")
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
    return text.strip()[:max_len]


def sanitize_for_log(value: str, max_len: int = 200) -> str:
    return sanitize_action_text(value, max_len=max_len).replace("\n", " ")


def escape_prompt_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def ensure_inside_vault(config: Config, file_path: str | Path) -> Path:
    full_path = Path(file_path)
    if not full_path.is_absolute():
        full_path = config.vault_root / full_path
    resolved = full_path.resolve()
    vault_root = config.vault_root.resolve()
    try:
        resolved.relative_to(vault_root)
    except ValueError:
        raise PermissionError(f"{file_path} resolves outside vault root")
    return resolved


def read_vault_text(config: Config, relative_path: str, fallback: str = "Unavailable") -> str:
    try:
        return ensure_inside_vault(config, relative_path).read_text()
    except FileNotFoundError:
        return fallback
    except Exception as exc:
        return f"{fallback} ({exc})"


def write_markdown_file(config: Config, relative_path: str, content: str, mode: str) -> None:
    target = ensure_inside_vault(config, relative_path)
    if target.suffix != ".md":
        raise PermissionError(f"Only markdown files are writable: {relative_path}")
    if target.name == "_AI_CONTEXT.md":
        raise PermissionError("_AI_CONTEXT.md cannot be modified via automation")
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "write":
        target.write_text(content)
    elif mode == "append":
        existing = target.read_text() if target.exists() else ""
        target.write_text(existing + ("\n" if existing else "") + content)
    else:
        raise ValueError(f"Unsupported write mode: {mode}")


def extract_json_block(raw_output: str) -> Tuple[str, List[Dict[str, Any]]]:
    match = re.search(r"```json\s*(.*?)\s*```", raw_output, re.DOTALL)
    if not match:
        content = raw_output.strip()
        if content:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return "", parsed
        return content, []

    payload = match.group(1).strip()
    try:
        actions = json.loads(payload)
    except json.JSONDecodeError:
        actions = []

    content = raw_output[: match.start()].rstrip()
    return content, actions if isinstance(actions, list) else []


def extract_json_object(text: str) -> Dict[str, Any] | None:
    """Extract the first JSON object from text, handling markdown code fences."""
    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Try stripping markdown code fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    # Try finding any {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


_MESSAGE_DELIMITER_RE = re.compile(r"^\s*\[?MESSAGE\]?:?\s*(.*)$", re.IGNORECASE)


def strip_message_delimiter(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return content.strip()
    for i, line in enumerate(lines):
        match = _MESSAGE_DELIMITER_RE.match(line)
        if match:
            remainder = match.group(1).strip()
            kept_lines = []
            if remainder:
                kept_lines.append(remainder)
            kept_lines.extend(lines[i + 1:])
            return "\n".join(kept_lines).strip()
    return content.strip()


def append_upcoming_event_row(config: Config, row: str) -> None:
    target = ensure_inside_vault(config, "Projects/Pickups.md")
    lines = target.read_text().splitlines()
    in_section = False
    insert_at = None
    for index, line in enumerate(lines):
        if line.strip() == "## Upcoming Events":
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            if line.startswith("|"):
                insert_at = index + 1
    if insert_at is None:
        raise RuntimeError("Could not locate Upcoming Events table in Projects/Pickups.md")
    lines.insert(insert_at, row)
    target.write_text("\n".join(lines) + "\n")
