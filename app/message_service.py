from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Tuple

from .actions import ActionDispatcher
from .config import Config
from .context import ContextBuilder
from .gateways import BlueBubblesClient
from .recipe_runner import RecipeRunner
from .runtime import GREETING_RE, current_timestamp, sanitize_action_text, sanitize_for_log


def default_log_entry(sender: str, inbound_text: str, reply_text: str) -> str:
    return (
        f"## {datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
        f"- **Inbound ({sender}):** {sanitize_for_log(inbound_text, 240)}\n"
        f"- **Reply:** {sanitize_for_log(reply_text, 240)}"
    )


class MessageService:
    def __init__(
        self,
        config: Config,
        contexts: ContextBuilder,
        recipes: RecipeRunner,
        actions: ActionDispatcher,
        messenger: BlueBubblesClient,
    ):
        self.config = config
        self.contexts = contexts
        self.recipes = recipes
        self.actions = actions
        self.messenger = messenger

    def handle_send(self, token: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        if self.config.enforce_send_auth and self.config.send_api_token and token != self.config.send_api_token:
            return 401, {"status": "error", "reason": "unauthorized"}
        chat_guid = payload.get("chatGuid")
        message = payload.get("message")
        if not chat_guid or not message:
            return 400, {"status": "error", "reason": "missing chatGuid or message"}
        self.messenger.send_message(chat_guid, message, context_label="/send")
        return 200, {"status": "success"}

    def handle_webhook(self, token: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        if token != self.config.webhook_token:
            print(f"[{datetime.now()}] Rejected: missing or invalid webhook token")
            return 401, {"status": "ignored", "reason": "unauthorized"}
        if not payload:
            return 200, {"status": "ignored", "reason": "no_json"}

        event_type = payload.get("event") or payload.get("type")
        if event_type != "new-message":
            return 200, {"status": "received"}

        msg = payload.get("data", {})
        text = msg.get("text", "")
        handle = (msg.get("handle") or {}).get("address", "")
        clean_handle = handle if str(handle).startswith("+") else f"+{handle}"
        chat_guid = ""
        chats = msg.get("chats") or []
        if chats:
            chat_guid = chats[0].get("guid", "")
        if not chat_guid:
            chat_guid = msg.get("chatGuid", "")
        is_from_me = bool(msg.get("isFromMe", False))

        print(f"[{datetime.now()}] Inbound: {clean_handle} -> {sanitize_for_log(text, 240)}")
        if clean_handle in self.config.valid_handles and not is_from_me:
            thread = threading.Thread(target=self.process_and_reply, args=(text, chat_guid, clean_handle), daemon=True)
            thread.start()
        else:
            print(f"[{datetime.now()}] Ignored: unauthorized or self")
        return 200, {"status": "received"}

    def sender_label(self, handle: str) -> str:
        try:
            position = self.config.valid_handles.index(handle) + 1
        except ValueError:
            return "authorized contact"
        return f"authorized contact {position}"

    def process_and_reply(self, text: str, chat_guid: str, handle: str) -> None:
        sender = self.sender_label(handle)
        current_ts = current_timestamp()
        context = self.contexts.build_message_context(current_ts)

        if not GREETING_RE.match(text or ""):
            try:
                self.messenger.send_message(chat_guid, "On it. Checking the records now.", context_label="ack")
            except Exception as exc:
                print(f"[{datetime.now()}] Ack failed: {exc}")

        reply_text = ""
        actions = []
        try:
            payload = self.recipes.run_json_plan(
                "message-handler.yaml",
                context,
                {
                    "message_text": (text or "").replace("\r", "").replace("\n", " ").strip()[:2000],
                    "sender_name": sender,
                    "current_timestamp": current_ts,
                    "vault_path": str(self.config.vault_root),
                },
                model=self.config.model_message,
                approval_mode=self.config.gemini_approval_mode_default,
            )
            reply_text = sanitize_action_text(payload.get("reply_text", ""), 1200)
            actions = payload.get("actions", [])
            if not isinstance(actions, list):
                raise ValueError("actions must be a list")
            if not any(action.get("action") == "session_log_append" for action in actions):
                actions.append({"action": "session_log_append", "content": default_log_entry(sender, text, reply_text)})
            self.actions.execute_message_actions(actions, text)
            if not reply_text:
                raise ValueError("reply_text was empty")
        except Exception as exc:
            print(f"[{datetime.now()}] FATAL EXCEPTION: {exc}")
            reply_text = "I'm terribly sorry, but my systems experienced a flutter. Please try again."
            try:
                self.actions.execute_message_actions(
                    [{"action": "session_log_append", "content": default_log_entry(sender, text, reply_text)}],
                    text,
                )
            except Exception:
                pass

        try:
            self.messenger.send_message(chat_guid, reply_text, context_label="final")
        except Exception as exc:
            print(f"[{datetime.now()}] Egress failed (final): {exc}")
