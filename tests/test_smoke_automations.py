from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from app.actions import ActionDispatcher
from app.automations import AutomationService
from app.briefs import BriefSender
from app.context import ContextBuilder
from app.recipe_runner import RecipeRunner

from tests.helpers import FakeGemini, FakeGWS, FakeMessenger, make_config, seed_vault


class AutomationSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        seed_vault(self.root)
        self.config = make_config(self.root)

    def tearDown(self):
        self.tempdir.cleanup()

    def make_service(self, gemini_output, *, gws=None, messenger=None):
        gws = gws or FakeGWS(agenda="Fri 9am Appointment\nFri 3pm Pickup", tasks_table="NeedsAction | Parent A: admin forms")
        messenger = messenger or FakeMessenger()
        contexts = ContextBuilder(self.config, gws)
        recipes = RecipeRunner(self.config, FakeGemini(gemini_output))
        actions = ActionDispatcher(self.config, gws, messenger)
        briefs = BriefSender(self.config, gws, messenger)
        return AutomationService(self.config, contexts, recipes, actions, briefs), gws, messenger

    def test_daily_brief_smoke(self):
        service, gws, messenger = self.make_service(
            """## 1. Strategic Pulse
Today looks steady. Pickups and dinner are assigned.

## 2. Drop-offs Today
- Child A: Parent A (8:00 AM / School A)
- Child B: Parent B (8:30 AM / School B)

## 3. Pickups Today
- 3:00 PM: Parent B gets Child A from School A
- 5:00 PM: Parent A gets Child B from Activity Center

## 4. Dinner Today
Pasta — Parent B (start by 5:15 PM)
Grocery Run (if needed): Parent A — neighborhood market — produce

## 5. Meal Plan Status
Pasta tonight. Soup tomorrow.

## 6. Pickups Next 2 Days
- Saturday: Parent A handles Child A, Parent B handles Child B.
- Sunday: Parent B handles Child A, Parent A handles Child B.

## 7. Shopping List Status
- Lemons

## 8. Risks or Conflicts
No major conflicts.

## 9. Decisions Needed
1. Confirm Sunday dinner.

## 10. Top Tasks
- Parent A: Buy produce

## 11. Appendix
Calendar and tasks loaded successfully.

```json
[{"action": "task", "title": "Parent A: Buy produce", "due": "2026-03-20", "notes": "neighborhood market"}, {"action": "file_append", "path": "Briefs/Session Log.md", "content": "Daily brief generated cleanly."}]
```"""
        )

        service.daily_brief()

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        brief_path = self.root / "Briefs" / "daily" / f"{today}.md"
        self.assertTrue(brief_path.exists())
        self.assertIn("Strategic Pulse", brief_path.read_text())
        self.assertEqual(1, len(gws.tasks))
        self.assertEqual(2, len(gws.sent_mail))
        self.assertEqual(1, len(messenger.messages))
        self.assertIn("Daily brief generated cleanly.", (self.root / "Briefs" / "Session Log.md").read_text())

    def test_checkin_smoke(self):
        service, gws, messenger = self.make_service(
            """[MESSAGE]
Parent B: Child A pickup at 3. Parent A: Child B pickup at 5.
Dinner: Pasta — Parent B, start by 5:15.
All set, spit-spot.

```json
[]
```"""
        )

        service.checkin("Midday")

        self.assertEqual(1, len(messenger.messages))
        self.assertIn("Dinner: Pasta", messenger.messages[0][1])
        self.assertEqual(0, len(gws.tasks))

    def test_school_assistant_smoke(self):
        gmail_listing = json.dumps({"messages": [{"id": "msg-1"}]})
        gws = FakeGWS(
            agenda="school calendar",
            tasks_table="task table",
            gmail_listing=gmail_listing,
            gmail_messages={"msg-1": '{"id":"msg-1","snippet":"Spring concert Friday at 18:00"}'},
        )
        service, gws, messenger = self.make_service(
            """[
  {"action": "school_calendar_event", "title": "Spring Concert", "date": "2026-03-22", "start_time": "18:00", "end_time": "19:00", "notes": "Gym"},
  {"action": "upcoming_event", "title": "Early dismissal", "date": "2026-03-21", "kid": "Child A", "notes": "Minimum day"},
  {"action": "task", "title": "Parent A: Pack event supplies", "due": "2026-03-21", "notes": "By Thursday night"}
]""",
            gws=gws,
        )

        service.school_assistant()

        self.assertEqual(1, len(gws.calendar))
        self.assertEqual("School: Spring Concert", gws.calendar[0]["summary"])
        self.assertEqual(1, len(gws.tasks))
        pickups = (self.root / "Projects" / "Pickups.md").read_text()
        self.assertIn("Early dismissal", pickups)
        self.assertEqual(0, len(messenger.messages))

    def test_evening_smoke(self):
        gmail_listing = json.dumps({"messages": [{"id": "msg-1"}]})
        gws = FakeGWS(
            agenda="agenda",
            tasks_table="tasks",
            gmail_listing=gmail_listing,
            gmail_messages={"msg-1": '{"id":"msg-1","snippet":"Spirit day tomorrow"}'},
        )
        gemini_output = [
            """[
  {"action": "upcoming_event", "title": "Spirit Day", "date": "2026-03-21", "kid": "Both", "notes": "Wear blue"}
]""",
            """[MESSAGE]
Today was smooth sailing.
Parent A: Child A pickup tomorrow.
Parent B: Dinner is soup — start by 5:00.

```json
[]
```""",
        ]
        service, gws, messenger = self.make_service(gemini_output, gws=gws)

        service.evening()

        pickups = (self.root / "Projects" / "Pickups.md").read_text()
        self.assertIn("Spirit Day", pickups)
        self.assertEqual(1, len(messenger.messages))
        self.assertIn("smooth sailing", messenger.messages[0][1])

    def test_weekly_review_smoke(self):
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        (self.root / "Briefs" / "daily" / f"{today}.md").write_text("## 1. Strategic Pulse\nWeekly sender still has a brief to send.\n")
        service, gws, messenger = self.make_service(
            """## 1. Weekly Pulse
Steady week overall.

## 2. System & Agent Evaluation
Healthy.

## 3. What Worked
- Pickups stayed coordinated.

## 4. What Slipped
- Nothing major.

## 5. Pickup Risks Next Week
- Thursday is tight.

## 6. Meal Plan and Shopping Gaps
- Need Sunday dinner.

## 7. Overdue Tasks
- Parent A: follow up paperwork.

## 8. Travel and School Prep
- Pack event supplies.

## 9. Top 3 Priorities for Next Week
- Lock pickups.

## 10. Appendix
All good.

```json
[{"action": "file_append", "path": "Briefs/Session Log.md", "content": "Weekly review generated."}]
```"""
        )

        service.weekly_review()

        week_path = self.root / "Briefs" / "weekly" / f"{datetime.datetime.now().strftime('%Y-W%V')}.md"
        self.assertTrue(week_path.exists())
        self.assertIn("Weekly Pulse", week_path.read_text())
        self.assertIn("Weekly review generated.", (self.root / "Briefs" / "Session Log.md").read_text())
        self.assertEqual(2, len(gws.sent_mail))
        self.assertEqual(1, len(messenger.messages))

    def test_meal_planner_smoke(self):
        service, gws, messenger = self.make_service(
            """# Meal Planning

## Current Week Plan
- Monday: Pasta — Parent B
- Tuesday: Soup — Parent A

## Grocery Assignment
Parent A: neighborhood market run on Thursday.

```json
[{"action": "task", "title": "Parent A: Grocery Run — neighborhood market", "due": "2026-03-22", "notes": "produce, bread"}, {"action": "file_append", "path": "Briefs/Session Log.md", "content": "Meal plan refreshed."}]
```"""
        )

        service.meal_planner()

        meal_plan = (self.root / "Projects" / "Meal Planning.md").read_text()
        self.assertIn("Current Week Plan", meal_plan)
        self.assertEqual(1, len(gws.tasks))
        self.assertIn("Meal plan refreshed.", (self.root / "Briefs" / "Session Log.md").read_text())
        self.assertEqual(0, len(messenger.messages))


if __name__ == "__main__":
    unittest.main()
