from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .config import Config
from .gateways import GeminiClient
from .runtime import extract_json_block, extract_json_object, strip_message_delimiter


@dataclass
class RecipeResult:
    content: str
    actions: List[Dict[str, Any]]
    raw_output: str


class RecipeRunner:
    def __init__(self, config: Config, gemini: GeminiClient):
        self.config = config
        self.gemini = gemini

    def run_markdown_recipe(
        self,
        recipe_name: str,
        context: str,
        params: Dict[str, Any],
        model: str,
        approval_mode: str,
        output_file: Path | None = None,
    ) -> RecipeResult:
        result = self.gemini.run_recipe(
            recipe_path=str(self.config.recipe_path(recipe_name)),
            context=context,
            params=params,
            model=model,
            approval_mode=approval_mode,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"Gemini failed for {recipe_name}")

        content, actions = extract_json_block(result.stdout)
        content = strip_message_delimiter(content)
        if output_file is not None and content.strip():
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(content)
        return RecipeResult(content=content, actions=actions, raw_output=result.stdout)

    def run_json_plan(
        self,
        recipe_name: str,
        context: str,
        params: Dict[str, Any],
        model: str,
        approval_mode: str,
    ) -> Dict[str, Any]:
        result = self.gemini.run_recipe(
            recipe_path=str(self.config.recipe_path(recipe_name)),
            context=context,
            params=params,
            model=model,
            approval_mode=approval_mode,
            output_format="json",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or f"Gemini failed for {recipe_name}")
        outer = json.loads(result.stdout)
        response_text = (outer.get("response") or "").strip()
        if not response_text:
            raise ValueError("Gemini returned an empty response field")
        payload = extract_json_object(response_text)
        if payload is None:
            # Gemini returned plain text — wrap it as a minimal valid payload
            payload = {"reply_text": response_text, "actions": []}
        return payload

