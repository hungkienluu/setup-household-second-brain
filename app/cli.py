from __future__ import annotations

import argparse
import sys

from .actions import ActionDispatcher
from .automations import AutomationService
from .briefs import BriefSender
from .config import Config
from .context import ContextBuilder
from .gateways import BlueBubblesClient, GWSClient, GeminiClient
from .message_service import MessageService
from .recipe_runner import RecipeRunner
from .server import serve


def build_services(config: Config):
    gws = GWSClient(config)
    messenger = BlueBubblesClient(config)
    gemini = GeminiClient(config)
    contexts = ContextBuilder(config, gws)
    recipes = RecipeRunner(config, gemini)
    actions = ActionDispatcher(config, gws, messenger)
    briefs = BriefSender(config, gws, messenger)
    automations = AutomationService(config, contexts, recipes, actions, briefs)
    messages = MessageService(config, contexts, recipes, actions, messenger)
    return automations, briefs, messenger, messages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="household-app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    automation = subparsers.add_parser("automation")
    automation.add_argument("name")
    automation.add_argument("args", nargs="*")

    notify = subparsers.add_parser("notify")
    notify.add_argument("message")
    notify.add_argument("chat_guid", nargs="?")

    subparsers.add_parser("send-briefs")

    server = subparsers.add_parser("server")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", default=5005, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.load()
    automations, briefs, messenger, messages = build_services(config)

    if args.command == "automation":
        automations.run(args.name, *args.args)
        return 0
    if args.command == "notify":
        messenger.send_message(args.chat_guid or config.default_chat_guid, args.message, context_label="notify-cli")
        return 0
    if args.command == "send-briefs":
        briefs.send_current_daily_brief()
        return 0
    if args.command == "server":
        serve(config, messages, host=args.host, port=args.port)
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

