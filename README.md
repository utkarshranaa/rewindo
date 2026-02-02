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

```bash
# Clone to your local plugins directory
git clone https://github.com/user/rewindo.git ~/.claude/plugins/rewindo

# Enable in your project
cd /path/to/your-project
claude plugin enable ~/.claude/plugins/rewindo
```

Or globally:
```bash
git clone https://github.com/user/rewindo.git ~/.claude/plugins/rewindo
```

Then enable per project as needed.

### Set Up Hooks

```bash
# Run the init command to configure Claude Code hooks
rewindo init
```

This will automatically add the necessary hooks to your Claude Code settings:
- `prompt-submit` hook saves your prompt before sending to Claude
- `stop` hook creates a checkpoint after Claude finishes responding

To check if hooks are configured:

```bash
rewindo status
```

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

Once enabled, Rewindo works automatically:

```bash
# Start working with Claude Code
claude

# Make some changes...
# Prompt: "Add user authentication"
# Prompt: "Add database layer"
# Prompt: "Add API endpoints"

# Later, view your timeline
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

### `rewindo init`

Set up Claude Code hooks automatically.

```bash
rewindo init              # Interactive setup
rewindo init --global     # Use global timeline storage
rewindo init --dry-run    # Preview changes without making them
```

This configures your `~/.claude/settings.json` to add the required hooks.

### `rewindo status`

Check if Rewindo hooks are configured.

```bash
rewindo status
```

Output:
```
Rewindo Status
============================================================
Settings location: C:\Users\You\.claude\settings.json

Hook Configuration:
  [OK] prompt-submit: rewindo capture-prompt
  [OK] stop: rewindo capture-stop

[OK] Rewindo is properly configured!
```

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
1. git diff detects changes
2. git add -A (stage changes)
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

# Or undo a specific prompt
rewindo list        # Find the prompt ID
rewindo revert 12    # Revert to before that prompt
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

### Commands not found

Make sure the plugin is enabled:
```bash
claude plugin enable /path/to/rewindo
```

### Timeline not recording

Check hooks are installed:
```bash
claude /hooks    # In Claude Code
```

Look for `rewindo` in the hooks list.

### "No checkpoints found"

Run doctor to diagnose:
```bash
rewindo doctor
```

### Revert doesn't work

Ensure you're in a git repository and have no uncommitted changes you want to keep:
```bash
git status
git stash    # Save uncommitted work
rewindo revert 5
```

## Development

### Running Tests

```bash
# End-to-end hooks test
python tests/test_hooks.py

# CLI commands test
python tests/test_cli_phase2.py

# Unit tests (when written)
pytest tests/
```

### Project Structure

```
rewindo/
├── plugin.json           # Plugin metadata
├── hooks/
│   ├── hooks.json        # Hook definitions
│   ├── log_prompt.py     # UserPromptSubmit hook
│   └── log_stop.py       # Stop hook
├── bin/
│   └── rewindo       # CLI tool
├── lib/
│   ├── __init__.py
│   └── rewindo.py        # Core library
├── tests/
│   ├── test_hooks.py
│   └── test_cli_phase2.py
└── README.md
```

## Token Efficiency

Rewindo is designed to minimize token usage when used with LLMs:

- Default `list` output shows only summaries (~5KB for 20 entries)
- `get-prompt` and `get-diff` enforce server-side bounds
- Pagination via `--offset` and `--max-lines`/`--max-chars`
- Search filters reduce context
- Revert doesn't read diffs (uses SHAs directly)

See PRD Section 14 for full token efficiency requirements.

## Contributing

Contributions welcome! Please read the PRD (`PRD.md`) for design context.

## License

MIT

## Credits

Built for Claude Code by the Rewindo contributors.
