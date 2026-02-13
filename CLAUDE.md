# CLAUDE.md

## Project

Rewindo is a Claude Code plugin that automatically records every prompt and creates reversible git checkpoints. It uses git refs (not branch commits) to keep `git log` clean.

## Running the CLI

```bash
# If installed via pip install -e .
rewindo <command>

# If not installed, run directly
python bin/rewindo <command>
```

## Common Commands

```bash
rewindo list                        # Show timeline
rewindo show <id>                   # Show checkpoint details
rewindo get-prompt <id>             # Get full prompt text
rewindo get-diff <id>               # Get diff for a checkpoint
rewindo revert <id>                 # Revert to a checkpoint
rewindo undo                        # Undo last checkpoint
rewindo label <id> <label>          # Add label to checkpoint
rewindo search <query>              # Search prompts
rewindo doctor                      # Health check
rewindo export <id>                 # Export checkpoint bundle
```

## Project Structure

```
rewindo/
  .claude-plugin/plugin.json    # Claude Code plugin manifest
  hooks/hooks.json              # Hook definitions (UserPromptSubmit, Stop)
  hooks/log_prompt.py           # Captures prompts on submit
  hooks/log_stop.py             # Creates checkpoints when Claude stops
  bin/rewindo                   # CLI tool
  lib/rewindo/                  # Core library package
    __init__.py                 # Package init + pip entry point
    rewindo.py                  # Rewindo class (timeline, revert, undo)
    detector.py                 # Working tree change detection
    snapshot.py                 # Git snapshot creation
    state.py                    # State file management
  tests/                        # Test suite (112 tests)
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Key Architecture

- Checkpoints stored in `refs/rewindo/checkpoints/<id>` (detached commits, not on branch)
- Timeline stored in `.claude/data/timeline.jsonl` (JSONL append-only)
- Full prompts in `.claude/data/prompts/<id>.txt`
- Full diffs in `.claude/data/diffs/<id>.patch`
- Stop hook uses temp `GIT_INDEX_FILE` to avoid modifying user's real index
- Diffs compare against previous checkpoint (not HEAD) to show per-prompt delta
