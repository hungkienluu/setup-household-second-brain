from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Set

from .actions import ActionDispatcher
from .briefs import BriefSender
from .config import Config
from .context import ContextBuilder
from .recipe_runner import RecipeRunner
from .runtime import current_timestamp


class AutomationService:
    def __init__(
        self,
        config: Config,
        contexts: ContextBuilder,
        recipes: RecipeRunner,
        actions: ActionDispatcher,
        briefs: BriefSender,
    ):
        self.config = config
        self.contexts = contexts
        self.recipes = recipes
        self.actions = actions
        self.briefs = briefs

    def run(self, command: str, *args: str) -> None:
        if command == "daily-brief":
            self.daily_brief()
        elif command == "checkin":
            self.checkin(args[0] if args else "Midday")
        elif command == "school-assistant":
            self.school_assistant()
        elif command == "evening":
            self.evening()
        elif command == "weekly-review":
            self.weekly_review()
        elif command == "meal-planner":
            self.meal_planner()
        else:
            raise ValueError(f"Unknown command: {command}")

    def daily_brief(self) -> None:
        context, current_date = self.contexts.build_daily_brief()
        output_file = self.config.vault_root / "Briefs" / "daily" / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        result = self.recipes.run_markdown_recipe(
            "daily-brief.yaml",
            context,
            {"vault_path": str(self.config.vault_root), "current_date": current_date},
            model=self.config.model_pro,
            approval_mode=self.config.gemini_approval_mode_safe,
            output_file=output_file,
        )
        self.actions.execute_scheduled_actions(result.actions, {"task", "file_append"})
        self.briefs.send_current_daily_brief()

    def checkin(self, checkin_type: str) -> None:
        result = self.recipes.run_markdown_recipe(
            "imessage-checkin.yaml",
            self.contexts.build_checkin(),
            {
                "checkin_type": checkin_type,
                "current_timestamp": current_timestamp(),
                "vault_path": str(self.config.vault_root),
            },
            model=self.config.model_flash,
            approval_mode=self.config.gemini_approval_mode_safe,
        )
        if not result.content.strip():
            raise RuntimeError("No check-in reply generated")
        self.actions.messenger.send_message(self.config.default_chat_guid, result.content, context_label="checkin")

    def school_assistant(self) -> None:
        email_content = self.contexts.fetch_recent_school_email_content()
        if not email_content.strip():
            print("No new school emails today. Skipping.")
            return
        allowed = {"upcoming_event", "task"}
        if self.config.enable_school_assistant_calendar_events:
            allowed.add("school_calendar_event")
        result = self.recipes.run_markdown_recipe(
            "school-extractor.yaml",
            self.contexts.build_school_context(email_content),
            {"current_timestamp": current_timestamp(), "vault_path": str(self.config.vault_root)},
            model=self.config.model_flash,
            approval_mode=self.config.gemini_approval_mode_safe,
        )
        self.actions.execute_scheduled_actions(result.actions, allowed)

    def evening(self) -> None:
        self.school_assistant()
        self.checkin("Evening")

    def weekly_review(self) -> None:
        context, current_date = self.contexts.build_weekly_review()
        output_file = self.config.vault_root / "Briefs" / "weekly" / f"{datetime.now().strftime('%Y-W%V')}.md"
        result = self.recipes.run_markdown_recipe(
            "weekly-review.yaml",
            context,
            {"vault_path": str(self.config.vault_root), "current_date": current_date},
            model=self.config.model_pro,
            approval_mode=self.config.gemini_approval_mode_safe,
            output_file=output_file,
        )
        self.actions.execute_scheduled_actions(result.actions, {"file_append"})
        self.briefs.send_current_daily_brief()

    def meal_planner(self) -> None:
        context, current_date = self.contexts.build_meal_planner()
        output_file = self.config.vault_root / "Projects" / "Meal Planning.md"
        result = self.recipes.run_markdown_recipe(
            "meal-planner.yaml",
            context,
            {"vault_path": str(self.config.vault_root), "current_date": current_date},
            model=self.config.model_pro,
            approval_mode=self.config.gemini_approval_mode_safe,
            output_file=output_file,
        )
        self.actions.execute_scheduled_actions(result.actions, {"task", "file_append"})

