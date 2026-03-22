# Household Automation Guide

This document explains the "under the hood" wiring of the Household Second Brain automations.

## 1. The Daily Rhythm (Scheduled Automations)

All scheduled automations are orchestrated via a universal runner script that selects the appropriate AI model based on the complexity of the task.

| Time | Automation | Role | Model | Command |
| :--- | :--- | :--- | :--- | :--- |
| **7:00 AM** | **Daily Brief** | Morning strategy — pickups, dinner, risks, tasks | `gemini-2.5-pro` | `run-automation.sh daily-brief` |
| **11:45 AM** | **Midday Nudge** | Afternoon assignments check | `gemini-2.5-flash` | `run-automation.sh checkin Midday` |
| **8:00 PM** | **Evening Run** | School email scan → evening nudge (combined) | `gemini-2.5-flash` | `run-automation.sh evening` |
| **SUN 4 PM** | **Meal Planner** | Drafts the upcoming week's meals | `gemini-2.5-pro` | `run-automation.sh meal-planner` |
| **SUN 6 PM** | **Weekly Review** | System evaluation & Sunday reset | `gemini-2.5-pro` | `run-automation.sh weekly-review` |

**Why the evening run is combined:** The school assistant and evening check-in share the same data (calendar, tasks, availability, pickups). Running them together saves redundant API calls and — more importantly — means the evening nudge sees any schedule changes the school assistant just found in email.

**Why Sunday automations are staggered:** The meal planner writes `Meal Planning.md` at 4 PM. The weekly review reads it at 6 PM. The gap ensures the review always sees the freshly updated plan.

## 2. System Architecture

### Core Pattern

Every automation now follows the same three-layer pattern:

```
LaunchAgent (schedule)
      ↓
shell wrapper (`scripts/run-automation.sh` / `scripts/webhook_listener.py`)
      ↓
Python app (`app/`) — pre-fetches data, assembles context, calls Gemini, enforces policy
      ↓
Gemini recipe      — AI reasoning: reads context, returns structured output
      ↓
ActionDispatcher   — Python dispatcher: GWS calls, file writes, notifications
```

**The key design principle: Gemini reads, the app acts.** The AI never executes commands directly. It returns structured JSON; the Python action layer executes each action using validated, hardcoded operations.

### Universal Runner & Central Config
- **Single Source of Truth:** Automation logic now lives in the `app/` package. The shell scripts remain as thin compatibility wrappers so existing LaunchAgents do not need to change immediately.
- **Central Configuration:** Common variables (`VAULT_ROOT`, binary paths, model assignments) are defined once in `scripts/config.sh` and sourced by all other scripts. Security flags also live there:
  - `ENFORCE_SEND_AUTH=1` protects the local `/send` endpoint
  - `GEMINI_APPROVAL_MODE_SAFE=plan` forces read-only Gemini runs for scheduled automations
  - `ENABLE_DAILY_BRIEF_GMAIL_CONTEXT=0` keeps raw Gmail out of the auto-sent daily brief by default
  - `ENABLE_SCHOOL_ASSISTANT_CALENDAR_EVENTS=1` enables school-email events on the family calendar by default; these are created without attendees or outbound invites, and they become timed events only when the extractor returns a strict validated `HH:MM` time
  - `DEFAULT_CALENDAR_TIMEZONE` and `SCHOOL_EVENT_DEFAULT_DURATION_MINUTES` control the timezone and fallback duration for timed school markers that have a start time but no explicit end time
- **LaunchAgents:** Background tasks live in `LaunchAgents/`. To update, copy `.plist` files to `~/Library/LaunchAgents/` and reload via `launchctl`.

### File Write Architecture
All file writes from any automation go through the Python action layer in `app/actions.py`, which enforces: the resolved path must be inside the vault root, must be a `.md` file, and must not be `_AI_CONTEXT.md` (read-only via automation).

### Secrets
Credentials live in `~/.household.env` (owner-readable only, never committed). The webhook listener loads this file at startup and exits if it is missing. Required keys: `BB_PASSWORD` and `WEBHOOK_TOKEN`.

## 3. Security Hardening (The Runner)

The `household-runner` is a compiled C wrapper that acts as the exclusive gateway for all background automations.

- Resolves its own location to find the `scripts/` directory.
- Validates script filenames to prevent path traversal (no `..` or `/` allowed).
- Automatically selects the correct interpreter based on file extension (`.sh` or `.py`).

**Maintenance:** If you modify `scripts/household-runner.c`, recompile:
```bash
cd scripts/
cc -O2 -Wall -Wextra -o household-runner household-runner.c
```
New scripts in `scripts/` can be executed via the runner immediately without further changes.

## 4. Real-time Communication (iMessage Handler)

- **Ingress:** BlueBubbles webhook → Port 5005. The webhook URL must include `?token=` (from `~/.household.env`) for the listener to accept it.
- **Switchboard:** `scripts/webhook_listener.py` is now a thin launcher for the Python HTTP server in `app/server.py`.
- **Message Service:** `app/message_service.py` validates inbound webhooks, pre-fetches household context, calls Gemini in read-only planning mode, and executes only a narrow validated action set.
- **API Gateway:** Also exposes a `/send` endpoint so all other scripts can send iMessages through a single channel (`notify.sh`). `/send` now requires an internal auth token header.
- **Message Handler:** `recipes/message-handler.yaml` is now a planning-only recipe. It returns JSON with `reply_text` plus typed requested actions; it has no live tools.
- **Model:** Real-time replies use **Gemini 3 Flash** for near-instant response times.
- **Persona:** Centrally managed in `Context/_AI_CONTEXT.md`.

## 5. Recipe Output Conventions

| Recipe | Output format | Notes |
|--------|--------------|-------|
| `daily-brief.yaml` | Markdown + JSON actions block | Saved to `Briefs/daily/` |
| `weekly-review.yaml` | Markdown + JSON actions block | Saved to `Briefs/weekly/` |
| `imessage-checkin.yaml` | `[MESSAGE]` delimiter + plain text | Script extracts only content after `[MESSAGE]` to strip any AI preamble |
| `school-extractor.yaml` | JSON array only | No tools — shell executes only allowlisted actions, including a dedicated no-attendees school calendar event path with strict optional time validation |
| `message-handler.yaml` | JSON object only | Returns `reply_text` plus typed action requests; the listener validates and executes them |
| `meal-planner.yaml` | Markdown + JSON actions block | Overwrites `Projects/Meal Planning.md` |

## 6. Pickups.md Sections

`Projects/Pickups.md` has two distinct sections with different ownership:

- **`## Recurring Schedule`** — standing weekly patterns. **Never modified by automation.**
- **`## Upcoming Events`** — one-time events, early dismissals, deadlines. Populated by the school assistant via the `upcoming_event` action type. Cleared by the weekly review.

## 7. Systems of Record
- **Calendar:** Family, Food & Exercise (Primary Shared Family Calendar).
- **Tasks:** Google Tasks (shopping list and household tasks).
- **Vault:** All durable rules, project logs, and archived briefs live in this folder.

## 8. Logs
Each LaunchAgent writes to dedicated log files in `logs/`:
- `com.household.*.stdout.log` — script output and action confirmations
- `com.household.*.stderr.log` — errors only
- `brain-listener.log` — iMessage handler activity
- `Briefs/Session Log.md` — AI decision log (material decisions and interaction summaries)

## 9. Testing
- Quick smoke suite: `zsh scripts/smoke-tests.sh`
- Full test suite: `python3 -m unittest discover -s tests -v`
- Syntax checks:
  - `python3 -m py_compile app/*.py tests/*.py scripts/webhook_listener.py`
  - `zsh -n scripts/run-automation.sh scripts/send-briefs.sh scripts/notify.sh scripts/smoke-tests.sh`

---
*Last Updated: March 20, 2026*
