---
name: rewindo
description: Timeline and revert tool for Claude Code. Track prompts and revert to checkpoints. Use when the user says "rewindo list", "show my timeline", "rewindo revert", "undo last change", "show checkpoint", "rewindo doctor", or wants to inspect or revert code changes.
---

Rewindo tracks a timeline of prompts and git checkpoints as Claude makes changes. Use the `rewindo` CLI to inspect and revert them.

The CLI binary is at `${CLAUDE_PLUGIN_ROOT}/bin/rewindo`. Run all commands as:

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" <command> [args]

## Commands

**list** — Show all timeline entries
- Triggers: "rewindo list", "show my timeline", "what checkpoints do I have"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" list`

**show <id>** — Show details of a specific checkpoint
- Triggers: "rewindo show 5", "show checkpoint 3", "what's in checkpoint #2"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" show <id>`

**revert <id>** — Revert to a previous checkpoint
- Triggers: "rewindo revert 5", "go back to checkpoint 3", "restore to #2"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" revert <id>`

**undo** — Undo the last checkpoint
- Triggers: "rewindo undo", "undo last change"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" undo`

**search <query>** — Search prompts by text
- Triggers: "rewindo search authentication", "search for api"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" search <query>`

**label <id> <label>** — Add a label to a checkpoint
- Triggers: "rewindo label 5 working", "mark checkpoint 2 as working"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" label <id> <label>`

**doctor** — Check Rewindo health and timeline integrity
- Triggers: "rewindo doctor", "check rewindo health"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" doctor`

**init** — Set up Rewindo hooks for current project
- Triggers: "rewindo init", "enable rewindo", "set up rewindo"
- Run: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/rewindo" init`
