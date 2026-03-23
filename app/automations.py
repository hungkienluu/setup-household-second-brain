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
            {"current_date": current_date},
            model=self.config.model_pro,
            approval_mode=self.config.gemini_approval_mode_safe,
            output_file=output_file,
        )
        self.briefs.send_current_daily_brief()

    def checkin(self, checkin_type: str) -> None:
        recipe = "midday-checkin.yaml" if checkin_type == "Midday" else "evening-checkin.yaml"
        result = self.recipes.run_markdown_recipe(
            recipe,
            self.contexts.build_checkin(),
            {"current_timestamp": current_timestamp()},
            model=self.config.model_flash,
            approval_mode=self.config.gemini_approval_mode_safe,
        )
        if not result.content.strip():
            raise RuntimeError("No check-in reply generated")
        print(f"[{checkin_type} Check-in] {result.content}")
        self.actions.messenger.send_message(self.config.default_chat_guid, result.content, context_label="checkin")

    def school_assistant(self) -> None:
        email_content = self.contexts.fetch_recent_school_email_content()
        if not email_content.strip():
            print("No new school emails today. Skipping.")
            return
        # Call 1: analyze emails → free-form text
        result = self.recipes.run_markdown_recipe(
            "school-extractor.yaml",
            self.contexts.build_school_context(email_content),
            {"current_timestamp": current_timestamp()},
            model=self.config.model_flash,
            approval_mode=self.config.gemini_approval_mode_safe,
        )
        analysis = result.content.strip()
        if not analysis or "no actionable" in analysis.lower():
            return
        # Call 2: convert analysis → JSON array (no vault context, no tools)
        allowed = {"upcoming_event", "task"}
        if self.config.enable_school_assistant_calendar_events:
            allowed.add("school_calendar_event")
        actions = self.recipes.run_school_extraction(analysis, self.config.model_flash)
        self.actions.execute_scheduled_actions(actions, allowed)

    def evening(self) -> None:
        self.school_assistant()
        self.checkin("Evening")

    def weekly_review(self) -> None:
        context, current_date = self.contexts.build_weekly_review()
        output_file = self.config.vault_root / "Briefs" / "weekly" / f"{datetime.now().strftime('%Y-W%V')}.md"
        result = self.recipes.run_markdown_recipe(
            "weekly-review.yaml",
            context,
            {"current_date": current_date},
            model=self.config.model_pro,
            approval_mode=self.config.gemini_approval_mode_safe,
            output_file=output_file,
        )
        self.actions.execute_scheduled_actions(result.actions, {"task", "file_append"})
        self.briefs.send_current_weekly_review()

    def meal_planner(self) -> None:
        context, current_date = self.contexts.build_meal_planner()
        output_file = self.config.vault_root / "Projects" / "Meal Planning.md"
        result = self.recipes.run_markdown_recipe(
            "meal-planner.yaml",
            context,
            {"current_date": current_date},
            model=self.config.model_pro,
            approval_mode=self.config.gemini_approval_mode_safe,
            output_file=output_file,
        )
        self.actions.execute_scheduled_actions(result.actions, {"task", "file_append"})

