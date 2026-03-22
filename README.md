# Household Second Brain

A shared Google Drive folder that becomes working memory for your family — read through Obsidian, driven by any CLI-based AI agent, and accessible in your family iMessage group chat.

One-time setup is usually about 45-90 minutes if your accounts and integrations are already ready. If you are setting up the dedicated macOS account, `gws`, Gemini CLI, and BlueBubbles for the first time, expect a few hours. After setup, you get six automated workflows running on a schedule: a daily brief, midday and evening check-ins, school logistics extraction, weekly reviews, and meal planning. Everything delivers to Gmail, iMessage, and your vault.

---

## Why this exists

Most family coordination runs on mental RAM. Someone remembers the school pickup, someone else remembers the dentist, and when those two people are both busy on a Tuesday, things fall through. Group chats fill with "wait, who's handling pickup today?" and "did we ever figure out dinner?"

The problem isn't information — it's that the information is scattered across calendars, texts, emails, and heads, with no single place that can answer a question or notice a conflict.

This system gives the household a shared memory that an AI agent can read, update, and act on. It won't replace coordination, but it stops the cheap failures: the pickup that got dropped, the email that got buried, the week that started without anyone knowing what was for dinner.

Real scenarios it handles: kid pickup confusion, mid-day schedule changes, buried school emails with action items, "what's for dinner?" in iMessage, meal plan gaps, overdue household tasks, and trip prep stress.

---

## Two ways to interact

**iMessage** is the family interface. A bot named Barney lives in your family group chat. He answers questions, flags conflicts, sends the daily brief, and handles day-to-day coordination. He has a Mary Poppins personality by default — warm, direct, "practically perfect" energy — because household ops shouldn't feel like a standup. His name, tone, and persona are configurable in `Context/_AI_CONTEXT.md`.

**CLI** is the power-user interface. Open the vault in any AI agent (Gemini CLI, Claude Code, Codex) for deeper work: updating routines, debugging automations, planning trips, or refining context. The vault has instruction files for all of them.

---

## What to expect

This can be a solid weekend project if you already have:
- a Mac that can stay on
- a separate macOS account on that Mac just for the household runtime
- a Google account for the household
- an Apple ID for the household iMessage identity

The codebase is already here. The work is mostly wiring up the external systems correctly, then running the guided setup interview.

The parts that need a bit of care are:

**macOS LaunchAgents + Full Disk Access.** Scheduled automations run as background LaunchAgents, which don't inherit your shell environment. They need their own `HOME`, `PATH`, and secrets. This repo ships a compiled C security wrapper (`household-runner`) that is the only binary you should grant Full Disk Access to.

**Gemini CLI auth.** The Gemini CLI uses OAuth. If the account you're using has auth or eligibility issues, setup will stall before the automations ever run.

**BlueBubbles + iMessage wiring.** The iMessage bot depends on a working BlueBubbles server, a webhook pointed at the local listener, and a household group chat GUID.

**Google Workspace access via `gws`.** The setup flow expects `gws` to work before you begin. It uses Google Contacts, Calendar, Gmail, and Tasks to prefill the vault and drive the automations.

**The setup is an interview, not a static config file.** `setup.yml` guides an AI agent through the household-specific context that cannot be hardcoded: roster, routines, meals, rules, and permissions.

---

## What it does

### The daily rhythm

| Time | Automation | What it does |
|---|---|---|
| 7:00 AM | Daily Brief | Full household snapshot: pickups, meals, tasks, risks. Sent by email and iMessage. |
| 11:45 AM | Midday Nudge | Afternoon pickup assignments and dinner plan. Max 4 lines. |
| 8:00 PM | Evening Check-in | Today's recap + tomorrow's preview. Also runs school email extraction. |
| Sun 4 PM | Meal Planner | Drafts next week's meals, alternates cook assignments, requests a grocery task. |
| Sun 6 PM | Weekly Review | Next week's pickup risks, meal gaps, overdue tasks, and top priorities. |

Plus one always-on iMessage listener (Barney).

### Architecture

```
LaunchAgents → household-runner → scripts/ wrappers → app/cli.py
                                                          ├── app/automations.py
                                                          ├── app/message_service.py
                                                          └── app/briefs.py
                                                                    ↓
                                                          app/recipe_runner.py
                                                                    ↓
                                                          Gemini CLI (reads + plans)
                                                                    ↓
                                                          app/actions.py (executes)
                                                                    ↓
                                             GWS (Calendar/Tasks/Gmail) + BlueBubbles (iMessage)
```

The core design principle:

> Gemini reads and plans. The Python action layer executes validated side effects.

Recipes are prompt contracts — they return structured output. The model never directly runs `gws`, sends messages, or writes files. `app/actions.py` decides what is actually allowed to happen, per automation.

### Security model

Seven layers of prompt injection defense:

1. **Untrusted content wrapping** — Gmail and external data is passed into recipes as labelled untrusted context. The model treats it as data, not instructions.
2. **Two-stage architecture** — School email extraction and iMessage handling are planning-only. The model never has both untrusted content and live tool access at the same time.
3. **Python action allowlists** — `app/actions.py` enforces per-automation allowlists before any side effect executes.
4. **Output sanitization** — Model-generated text fields are truncated, stripped of shell metacharacters, and checked for injection patterns before use.
5. **File write restrictions** — The action layer blocks writes outside the vault, to non-markdown files, and to `_AI_CONTEXT.md`.
6. **School event validation** — Date and time fields from school emails are strictly validated before calendar insertion.
7. **Phone allowlist + send auth** — The message service only processes iMessages from whitelisted handles. The `/send` endpoint requires an internal token.

---

## Prerequisites

Before running setup, you need five things:

1. **A Mac that can stay on** — This is the machine that runs LaunchAgents, the local webhook listener, and the iMessage bridge.
2. **A separate macOS user account for the assistant** — Do not run this under your normal daily-use account. Use a dedicated standard account so household automation stays isolated from your personal shell, files, and app state.
3. **A Google account for the household** — This account owns the shared calendar, tasks, and email the assistant reads and writes to.
4. **An Apple ID for iMessage** — The assistant needs its own iMessage identity to live in your family group chat.
5. **Gemini CLI installed and authenticated:**
   ```bash
   brew install gemini-cli
   gemini auth login
   ```
   Make sure your Google account has age verified at myaccount.google.com before authenticating.

### Set Up `gws` First

`gws` is not an optional extra in this template. The setup flow uses it immediately to pull:
- contacts
- calendar events
- Gmail messages
- Google Tasks lists

Install and authenticate it before you start:

```bash
brew install gws
gws auth
```

Quick sanity checks:

```bash
gws contacts list
gws calendar list --days 7
gws gmail list --label inbox --limit 5
gws tasks list --all-lists
```

If those commands do not work, fix `gws` before you run `setup.yml`.

### Set Up BlueBubbles For iMessage

If you want the iMessage bot to work, BlueBubbles needs to be running inside the dedicated macOS account that will host the automation runtime.

Minimum checklist:

1. Install BlueBubbles from `bluebubbles.app`.
2. Sign the Messages app into the household Apple ID on that Mac.
3. Start the BlueBubbles server and confirm it can send messages normally.
4. Create `~/.household.env` with at least:

```bash
BB_PASSWORD="your-bluebubbles-password"
WEBHOOK_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
chmod 600 ~/.household.env
```

5. In BlueBubbles webhook settings, point it at:

```text
http://127.0.0.1:5005/webhook?token=YOUR_WEBHOOK_TOKEN
```

Replace `YOUR_WEBHOOK_TOKEN` with the value from `~/.household.env`.

6. Make sure the household group chat exists already. The setup flow will store the chat GUID in the vault so scheduled briefs and replies know where to go.

---

## Setup

Recommended order:

1. Get Gemini CLI working.
2. Get `gws` working.
3. Get BlueBubbles working.
4. Clone this repo into the vault directory.
5. Run the guided setup interview.

Then open Gemini CLI in the vault directory and run:

```
Read setup.yml and set up a new Household Second Brain vault here.
```

The agent will:
- Pull in your Google Workspace data (contacts, calendar, tasks, Gmail) to pre-fill context
- Interview you section by section: household charter, pickup schedule, cast of characters, meal rules, communication style, permissions
- Generate your personalized `Context/_AI_CONTEXT.md` and operating files
- Configure LaunchAgents, compile the security wrapper, and install everything

Guided interview and repo install: about 30 minutes once the dedicated runtime account, Gemini CLI, `gws`, and BlueBubbles are already working.

---

## Repo structure

```
app/                  Python automation core (config, context, gateways, actions, etc.)
recipes/              Prompt contracts for each automation
scripts/              Shell wrappers + household-runner C source
tests/                Unit and smoke tests
LaunchAgents/         LaunchAgent plist templates
Context/              Your household memory (generated during setup, not in this repo)
Projects/             Active working surface (generated during setup, not in this repo)
Briefs/               AI-generated daily and weekly briefs (generated at runtime)
setup.yml             The setup recipe — run this once per household
```

---

## After setup

- Edit `Context/_AI_CONTEXT.md` any time to update household context. Open your AI agent and say "update my household context" — or use voice dictation (Wispr Flow works well for the freeform sections).
- Barney's personality, name, and tone live in `Context/_AI_CONTEXT.md`. Change them there.
- To run an automation manually: `cd vault && zsh scripts/run-automation.sh daily-brief`
- To test the full suite: `python3 -m unittest discover -s tests -v`

---

## Contributing

PRs welcome. Keep changes generic and household-agnostic — no personal data, no hardcoded names or phone numbers. The vault content (Context/, Projects/) is generated per household and is never part of this repo.

Before pushing, run a local secret scan:

```bash
brew install gitleaks
gitleaks dir . --config gitleaks.toml
```

The repo also includes a GitHub Actions workflow that runs Gitleaks on every push and pull request.
