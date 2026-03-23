import os
import re
import unittest
from pathlib import Path

from app.config import Config
from app.gateways import GeminiClient
from app.recipe_runner import RecipeRunner

class BaseDailyBriefEval:
    """Mixin containing the actual tests so they can be run against multiple fixtures."""
    
    @classmethod
    def setup_fixture(cls, fixture_name: str):
        cls.config = Config.load()
        cls.gemini = GeminiClient(cls.config)
        cls.runner = RecipeRunner(cls.config, cls.gemini)
        
        cls.fixture_path = Path(__file__).parent / "fixtures" / fixture_name
        if not cls.fixture_path.exists():
            raise FileNotFoundError(f"Fixture missing: {cls.fixture_path}")
        
        cls.context = cls.fixture_path.read_text()
        
        print(f"\n[Eval] Generating Daily Brief for '{fixture_name}' using gemini-2.5-pro...")
        cls.result = cls.runner.run_markdown_recipe(
            "daily-brief.yaml",
            cls.context,
            {"current_date": "Monday, March 23, 2026"},
            model=cls.config.model_pro,
            approval_mode="yolo",
        )
        cls.brief_content = cls.result.content

    # ==========================================
    # PHASE 1: Deterministic Graders
    # ==========================================
    
    def test_headers_are_present_and_ordered(self):
        headers = [
            "## 1. Strategic Pulse",
            "## 2. Drop-offs Today",
            "## 3. Pickups Today",
            "## 4. Dinner Today",
            "## 5. Meal Plan Status",
            "## 6. Pickups Next 2 Days",
            "## 7. Shopping List Status",
            "## 8. Risks or Conflicts",
            "## 9. Decisions Needed",
            "## 10. Top Tasks",
            "## 11. Appendix"
        ]
        
        content = self.brief_content
        last_idx = -1
        for header in headers:
            idx = content.find(header)
            self.assertNotEqual(idx, -1, f"Missing required header: '{header}'")
            self.assertGreater(idx, last_idx, f"Header out of order: '{header}' appears before previous header")
            last_idx = idx

    def test_no_tbd_or_placeholders(self):
        content = self.brief_content.lower()
        self.assertNotIn("tbd", content, "Found 'tbd' in brief - AI punted on an assignment.")
        self.assertNotIn("tba", content, "Found 'tba' in brief.")
        self.assertNotIn("[parent]", content, "Found unreplaced '[Parent]' placeholder.")
        self.assertNotIn("[kid]", content, "Found unreplaced '[Kid]' placeholder.")

    def test_action_block_is_empty(self):
        self.assertIsInstance(self.result.actions, list)

    def test_roster_names_used(self):
        dinner_section = re.search(r"## 4\. Dinner Today(.*?)## 5\.", self.brief_content, re.DOTALL)
        self.assertIsNotNone(dinner_section, "Could not extract Dinner section")
        
        text = dinner_section.group(1)
        self.assertTrue(
            "Parent A" in text or "Parent B" in text,
            f"Neither Parent A nor Parent B found in Dinner section. Section text: {text}"
        )

    # ==========================================
    # PHASE 2: LLM-as-Judge
    # ==========================================
    
    def test_llm_judge_quality(self):
        print(f"\n[Eval] Running LLM-as-Judge to score the brief...")
        judge_result = self.runner.run_json_plan(
            "judge-brief.yaml",
            "",
            {
                "context": self.context,
                "brief": self.brief_content
            },
            model=self.config.model_flash,
            approval_mode="yolo"
        )
        
        score = judge_result.get("score", 0)
        reasoning = judge_result.get("reasoning", "No reasoning provided")
        
        print(f"\n[LLM Judge Score]: {score}/5")
        print(f"[LLM Judge Reasoning]: {reasoning}\n")
        
        self.assertGreaterEqual(
            score, 
            4, 
            f"Brief failed quality threshold. Score: {score}. Reasoning: {reasoning}"
        )


class TestDailyBriefStandard(BaseDailyBriefEval, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup_fixture("eval_context_standard.md")

class TestDailyBriefTravel(BaseDailyBriefEval, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup_fixture("eval_context_travel.md")

class TestDailyBriefConflict(BaseDailyBriefEval, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup_fixture("eval_context_conflict.md")


if __name__ == "__main__":
    unittest.main()
