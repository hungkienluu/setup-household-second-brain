from __future__ import annotations

import re

from .config import Config
from .gateways import BlueBubblesClient, GWSClient


class BriefSender:
    def __init__(self, config: Config, gws: GWSClient, messenger: BlueBubblesClient):
        self.config = config
        self.gws = gws
        self.messenger = messenger

    def send_current_daily_brief(self) -> None:
        date_stamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        file_path = self.config.vault_root / "Briefs" / "daily" / f"{date_stamp}.md"
        if not file_path.exists():
            print(f"No daily brief found at {file_path}")
            return
        raw_content = file_path.read_text()
        imessage_content = self._extract_imessage_brief(raw_content)
        if imessage_content.strip():
            self.messenger.send_message(self.config.default_chat_guid, imessage_content, context_label="daily-brief")
        html_content = self._convert_md_to_html(raw_content)
        for recipient in self.config.daily_brief_recipients:
            self._send_raw_email(recipient, f"Household Daily Brief: {date_stamp}", html_content)

    def _send_raw_email(self, to_addr: str, subject: str, html_body: str) -> None:
        raw_msg = (
            f"To: {to_addr}\n"
            f"Subject: {subject}\n"
            "MIME-Version: 1.0\n"
            "Content-Type: text/html; charset=utf-8\n\n"
            f"<html><body style=\"font-family: sans-serif; line-height: 1.2;\">\n{html_body}\n</body></html>"
        )
        self.gws.send_raw_gmail(raw_msg)

    @staticmethod
    def _convert_md_to_html(content: str) -> str:
        escaped = (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"^### (.*)$", r"<h3>\1</h3>", escaped, flags=re.MULTILINE)
        escaped = re.sub(r"^## (.*)$", r"<h2>\1</h2>", escaped, flags=re.MULTILINE)
        escaped = re.sub(r"^# (.*)$", r"<h1>\1</h1>", escaped, flags=re.MULTILINE)
        lines = []
        for raw_line in escaped.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("<h"):
                lines.append(line)
            elif line.startswith("- "):
                lines.append(f"<li>{line[2:]}</li>")
            else:
                lines.append(f"{line}<br>")
        return "\n".join(lines)

    @staticmethod
    def _extract_imessage_brief(raw_content: str) -> str:
        section_map = {
            "## 1. Strategic Pulse": "MORNING PULSE",
            "## 2. Pickups Today": "\nPICKUPS TODAY",
            "## 3. Dinner Today": "\nDINNER",
            "## 4. Meal Plan Status": "\nMEALS",
            "## 7. Risks or Conflicts": "\nRISKS",
            "## 8. Decisions Needed": "\nDECISIONS",
        }
        output = []
        printing = False
        for line in raw_content.splitlines():
            stripped = line.strip()
            if stripped in section_map:
                printing = True
                output.append(section_map[stripped])
                continue
            if stripped.startswith("## "):
                printing = False
            if printing and stripped:
                output.append(stripped.replace("**", ""))
        return "\n".join(output).strip()

