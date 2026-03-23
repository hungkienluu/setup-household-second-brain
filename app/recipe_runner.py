from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import Config
from .gateways import GeminiClient
from .runtime import extract_json_block, extract_json_object, strip_message_delimiter


@dataclass
class RecipeResult:
    content: str
    actions: List[Dict[str, Any]]
    raw_output: str


def _parse_recipe(path: Path) -> Tuple[str, str]:
    """Extract instructions and prompt from a recipe YAML without pyyaml."""
    text = path.read_text()
    instructions = ""
    prompt = ""

    # Extract instructions (multiline block after "instructions: |")
    instr_match = re.search(r'^instructions:\s*\|\n((?:\n|[ \t]+.*\n)*)', text, re.MULTILINE)
    if instr_match:
        raw = instr_match.group(1)
        # Dedent: find the indentation of the first non-empty line and strip it
        lines = raw.splitlines(True)
        indent = 0
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                break
        instructions = "".join(line[indent:] if len(line) > indent else line for line in lines).rstrip()

    # Extract prompt (quoted string after "prompt:")
    prompt_match = re.search(r'^prompt:\s*"((?:[^"\\]|\\.)*)"', text, re.MULTILINE)
    if prompt_match:
        prompt = prompt_match.group(1).replace('\\"', '"').replace('\\\\', '\\')

    return instructions, prompt


class RecipeRunner:
    def __init__(self, config: Config, gemini: GeminiClient):
        self.config = config
        self.gemini = gemini

    def _assemble_prompt(self, recipe_name: str, params: Dict[str, Any]) -> str:
        """Load recipe YAML, substitute params, and return assembled prompt."""
        instructions, prompt_template = _parse_recipe(self.config.recipe_path(recipe_name))
        # Substitute {{ param }} placeholders in both instructions and prompt
        for key, value in params.items():
            placeholder = "{{ " + key + " }}"
            instructions = instructions.replace(placeholder, str(value))
            prompt_template = prompt_template.replace(placeholder, str(value))
        return f"{instructions}\n\n{prompt_template}"

    def run_markdown_recipe(
        self,
        recipe_name: str,
        context: str,
        params: Dict[str, Any],
        model: str,
        approval_mode: str,
        output_file: Path | None = None,
    ) -> RecipeResult:
        assembled = self._assemble_prompt(recipe_name, params)
        result = self.gemini.run_assembled(
            prompt=assembled,
            context=context,
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

    def run_school_extraction(self, analysis: str, model: str) -> List[Dict[str, Any]]:
        """Call 2: convert free-form school email analysis into a JSON action array."""
        schema = (
            '[{"action":"school_calendar_event|task|upcoming_event",'
            '"title":"string","date":"YYYY-MM-DD",'
            '"notes":"string (optional)","start_time":"HH:MM (optional)",'
            '"end_time":"HH:MM (optional)","kid":"Child A|Child B|Both (optional)",'
            '"change_type":"string (optional)","new_time":"string (optional)",'
            '"link":"string (optional)"}]'
        )
        prompt = (
            "Convert the following school email analysis into a JSON array.\n"
            "Output ONLY a valid JSON array — no prose, no explanation, no markdown fences.\n"
            f"Use this schema: {schema}\n"
            "Supported action values: school_calendar_event, task, upcoming_event\n"
            "Only include start_time/end_time when an explicit clock time was in the email.\n"
            "If nothing is actionable, output: []\n\n"
            f"Analysis:\n{analysis}"
        )
        result = self.gemini.run_prompt(prompt, model, "yolo")
        if result.returncode != 0:
            return []
        try:
            outer = json.loads(result.stdout)
            response_text = (outer.get("response") or "").strip()
        except json.JSONDecodeError:
            response_text = result.stdout.strip()
        # Try direct parse
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        # Fallback: find any [...] block
        import re
        match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return []

    def run_json_plan(
        self,
        recipe_name: str,
        context: str,
        params: Dict[str, Any],
        model: str,
        approval_mode: str,
    ) -> Dict[str, Any]:
        assembled = self._assemble_prompt(recipe_name, params)
        result = self.gemini.run_assembled(
            prompt=assembled,
            context=context,
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

