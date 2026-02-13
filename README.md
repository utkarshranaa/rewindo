# Rewindo

> Prompt-to-code timeline with one-command revert for Claude Code.

Rewindo automatically records every prompt you give to Claude Code and the changes that result, creating checkpoints you can instantly revert to.

**Problem solved:** Claude breaks something that was working, and you can't remember exactly which prompt had the "good" state. With Rewindo, just list your timeline and revert to any checkpoint.

## Features

- **Automatic timeline recording** - No manual intervention needed
- **One-command revert** - Roll back to any previous state instantly
- **Search & labels** - Find checkpoints by prompt text or add custom labels
- **Git-based checkpoints** - Uses refs (not commits), so your `git log` stays clean
- **Token-efficient** - CLI designed to minimize LLM context usage
- **Works offline** - Everything runs locally in your repo

## Installation

### Prerequisites

- Python 3.9+
- Git
- Claude Code

### Install the Plugin

Inside any Claude Code session, run these two commands:

```
/plugin marketplace add utkarshranaa/rewindo
/plugin install rewindo@rewindo-marketplace
```

That's it. The hooks activate automatically — every prompt is captured and every response creates a checkpoint.

### Install the CLI (optional)

The plugin handles recording automatically, but to use commands like `rewindo list` and `rewindo revert` from your terminal:

```bash
git clone https://github.com/utkarshranaa/rewindo.git
cd rewindo
pip install -e .
```

This puts the `rewindo` command on your PATH.

### Verify Installation

Inside Claude Code, type `/hooks` to confirm the rewindo hooks are active. You should see:
- **UserPromptSubmit** hook (captures prompts)
- **Stop** hook (creates checkpoints)

### Understanding the Timeline

Rewindo tracks two types of changes:

| Actor | Symbol | Meaning |
|-------|--------|---------|
| Assistant | A | Changes made by Claude in response to a prompt |
| User | U | Manual edits you made between prompts |

When you view your timeline with `rewindo list`, you'll see both types of steps:

```
ID   A  Date/Time            Files                                  Description
---- -  -------------------  -------------------------------------  ------------------------------
#5   A  2026-02-01 14:30     +filter.ts (+35/-8)                    "Add filtering"
#4   U  2026-02-01 14:28     +footer.tsx (+3/-0)                    "Add footer"
#3   A  2026-02-01 14:15     +button.tsx (+28/-5)                   "Create login component"
#2   U  2026-02-01 14:10     +styles.css (+2/-1)                    "Fix navbar CSS"
#1   A  2026-02-01 12:00     +app.tsx (+120/-0)                    "Setup project"
```

In this example:
- Steps #1, #3, #5 are Claude's responses to prompts
- Steps #2, #4 are manual edits you made between prompts

This helps you track exactly what changed, whether it was from a prompt or your own edits.

## Quick Start

Once the plugin is installed, Rewindo works automatically. Every prompt you submit and every response Claude gives is recorded.

You can run `rewindo` commands either from your terminal (if you did `pip install -e .`) or by asking Claude inside a session (e.g., "show me my timeline").

```bash
# Prompt: "Add user authentication"
# Prompt: "Add database layer"
# Prompt: "Add API endpoints"

# View your timeline
rewindo list

# Output:
ID   A  Date/Time            Files                                  Description
---- -  -------------------  -------------------------------------  ------------------------------
#3   A  2026-01-30 14:22     +api.py (+15/-0)                      "Add API endpoints"
#2   U  2026-01-30 14:18     +navbar.css (+3/-1)                    "Manual edits before prompt #3"
#1   A  2026-01-30 14:15     +db.py (+20/-0)                       "Add database layer"

# Actor column: A = Assistant (prompt), U = User (manual edit)

# Something broke? Revert to when it was working
rewindo label 2 working   # Mark checkpoint #2 as working
rewindo revert 2          # Revert to checkpoint #2

# Or just undo the last change
rewindo undo
```

## Commands

### `rewindo list [--limit N] [--query PATTERN] [--expand] [--expand-chars N]`

List timeline entries.

```bash
rewindo list                      # Show last 20 entries (compact, 60 chars)
rewindo list --limit 5            # Show last 5 entries
rewindo list --query api          # Search for "api" in prompts
rewindo list --expand             # Show longer prompts (200 chars)
rewindo list --expand --expand-chars 500  # Show 500-char prompts
```

**Output format:**
```
#ID  Timestamp             Files changed                           Prompt snippet
#17  2026-01-30 14:22     +api.py (+15/-0) +utils.py (+5/-2)    "Add pagination..." [+]
#16  2026-01-30 14:15     +types.ts (+8/-0)                       "Fix TypeScript errors"
```

The `[+]` indicator means the prompt is longer than shown. Use `--expand` to see more without reading the full prompt.

### `rewindo show <id>`

Show detailed information about a checkpoint.

```bash
rewindo show 17
```

**Output:**
```
============================================================
Checkpoint #17
============================================================
Timestamp: 2026-01-30T14:22:11-05:00
Session:    abc123

Prompt:
  Add pagination to listUsers with page size parameter

Files changed:
  src/api/users.py: +15/-2
  src/utils/pagination.ts: +5/-0

Ref:        refs/rewindo/checkpoints/17
```

### `rewindo get-prompt <id> [--max-chars N] [--offset N]`

Get the full prompt text.

```bash
rewindo get-prompt 17              # Full prompt
rewindo get-prompt 17 --max-chars 100  # First 100 characters
```

### `rewindo get-diff <id> [--max-lines N] [--file PATH]`

Get the diff for a checkpoint.

```bash
rewindo get-diff 17                    # Full diff
rewindo get-diff 17 --max-lines 50      # First 50 lines
rewindo get-diff 17 --file api.py       # Only show api.py changes
```

### `rewindo revert <id>`

Revert working tree to a checkpoint.

```bash
rewindo revert 15    # Revert to checkpoint #15
```

**Safety:** Prompts for confirmation unless `--yes` is used.

**⚠️ Important Warning:** After reverting, you will see a disclaimer about dependencies. Rewindo reverts your code, but NOT your installed packages. If you've upgraded packages (like `npm install`, `pip install`) since the checkpoint, you may need to reinstall them:

```
======================================================================
IMPORTANT: Dependencies may be out of sync!
======================================================================
You reverted to an earlier state. Your installed packages may not match.

Recommended actions:
  • npm install        # JavaScript/Node.js projects
  • pip install -r requirements.txt  # Python projects
  • bundle install     # Ruby projects
  • cargo build        # Rust projects
======================================================================
```

### `rewindo undo`

Undo the last checkpoint (revert to state before it).

```bash
rewindo undo
```

This is equivalent to "go back to before the last prompt."

**⚠️ Same dependency warning applies** - see `rewindo revert` above.

### `rewindo label <id> <label>`

Add a label to a checkpoint.

```bash
rewindo label 15 working
rewindo label 15 before-refactor
rewindo label 15 release-candidate
```

Labels appear in `rewindo list` output: `[working]`

### `rewindo search <query>`

Search prompts by text.

```bash
rewindo search authentication    # Find "authentication" in prompts
rewindo search api               # Find "api" in prompts
```

### `rewindo doctor`

Check installation and timeline health.

```bash
rewindo doctor
```

**Checks:**
- Git repository status
- Hook installation
- Timeline file integrity
- Orphaned checkpoint refs

### `rewindo export <id> [--output DIR]`

Export a checkpoint as a bundle.

```bash
rewindo export 15              # Creates ./export-00015/
rewindo export 15 -o ~/backups/checkpoint15/
```

**Bundle contains:**
- `prompt.txt` - Full prompt text
- `diff.patch` - Full unified diff
- `meta.json` - Entry metadata

## How It Works

### Automatic Recording

```
You submit prompt to Claude
         ↓
UserPromptSubmit hook fires
         ↓
Prompt saved to .claude/data/prompt_state.json
         ↓
Claude makes code changes
         ↓
Stop hook fires
         ↓
1. Compare working tree against previous checkpoint (skip if unchanged)
2. Create temporary index file (does not touch your real git index)
3. git write-tree (capture tree state)
4. git commit-tree (create detached commit)
5. git update-ref refs/rewindo/checkpoints/<id> (store ref)
6. Save diff and prompt to files
7. Append entry to .claude/data/timeline.jsonl
```

### Checkpoints Use Git Refs

Rewindo stores checkpoints in `refs/rewindo/checkpoints/<id>` instead of creating commits on your branch.

**Benefits:**
- Doesn't pollute `git log`
- Can't accidentally push to remote
- Invisible to normal git operations
- Still uses git's object model for efficiency

View them with:
```bash
git show-ref | grep rewindo
```

### Timeline Storage

```
.claude/data/
├── timeline.jsonl      # Journal of all entries
├── prompts/
│   ├── 00001.txt       # Full prompt for entry #1
│   ├── 00002.txt
│   └── ...
└── diffs/
    ├── 00001.patch     # Full diff for entry #1
    ├── 00002.patch
    └── ...
```

The `.claude/data/` directory is automatically added to `.gitignore`.

## Common Workflows

### Workflow 1: Undo a Mistake

```bash
# Claude made a mistake on the last prompt
rewindo undo

# Or revert to a specific checkpoint
rewindo list        # Find the checkpoint ID
rewindo revert 12   # Restore your code to the state at checkpoint #12
```

### Workflow 2: Mark and Restore Working States

```bash
# When something works, mark it
rewindo label 8 working

# Later when things break
rewindo search working
rewindo revert 8
```

### Workflow 3: Review What Changed

```bash
# See recent prompts and changes
rewindo list

# Get full details of a specific change
rewindo show 15
rewindo get-diff 15 --max-lines 100
```

### Workflow 4: Export and Share Changes

```bash
# Export a checkpoint for code review
rewindo export 17

# Share the export directory with a teammate
# They can review prompt.txt, diff.patch, and meta.json
```

## Data Location

| File/Directory | Purpose |
|---------------|---------|
| `.claude/data/timeline.jsonl` | Timeline journal (JSONL format) |
| `.claude/data/prompts/<id>.txt` | Full prompt texts |
| `.claude/data/diffs/<id>.patch` | Full unified diffs |
| `refs/rewindo/checkpoints/<id>` | Git refs to checkpoint commits |

## Troubleshooting

### Plugin not loading

Verify the plugin is installed by typing `/hooks` inside Claude Code. You should see the rewindo UserPromptSubmit and Stop hooks. If not, reinstall:

```
/plugin marketplace add utkarshranaa/rewindo
/plugin install rewindo@rewindo-marketplace
```

### Timeline not recording

1. Type `/hooks` inside Claude Code to confirm hooks are active
2. Make sure you're in a git repository (`git status` should succeed)
3. Run `rewindo doctor` to check timeline health

### "No checkpoints found"

Run doctor to diagnose:
```bash
rewindo doctor
```

### Revert doesn't work

Rewindo warns you if you have uncommitted changes before reverting. If you want to save them first:
```bash
git stash    # Save uncommitted work
rewindo revert 5
```

## Development

### Running Tests

```bash
python -m pytest tests/ -v
```

All 112 tests cover hooks, CLI commands, snapshots, conflict resolution, cross-platform compatibility, and performance.

### Project Structure

```
rewindo/
├── .claude-plugin/
│   ├── plugin.json        # Plugin manifest
│   └── marketplace.json   # Marketplace catalog
├── hooks/
│   ├── hooks.json         # Hook definitions
│   ├── log_prompt.py      # UserPromptSubmit hook
│   └── log_stop.py        # Stop hook
├── bin/
│   └── rewindo            # CLI tool
├── lib/rewindo/
│   ├── __init__.py        # Package init + entry point
│   ├── rewindo.py         # Core library (timeline, revert, undo)
│   ├── detector.py        # Working tree change detection
│   ├── snapshot.py        # Git snapshot creation
│   └── state.py           # State file management
├── tests/                 # 112 tests
├── setup.py               # pip install support
└── README.md
```

## Token Efficiency

Rewindo is designed to minimize token usage when used with LLMs:

- Default `list` output shows only summaries (~5KB for 20 entries)
- `get-prompt` and `get-diff` enforce server-side bounds
- Pagination via `--offset` and `--max-lines`/`--max-chars`
- Search filters reduce context
- Revert doesn't read diffs (uses SHAs directly)

## Contributing

Contributions welcome! See `PRD.md` for design context and architecture decisions.

## License

MIT

## Credits

Built for Claude Code by the Rewindo contributors.
