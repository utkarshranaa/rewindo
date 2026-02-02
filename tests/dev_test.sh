#!/bin/bash
# Development test script for Rewindo
# Run this to quickly test hooks and CLI without full plugin installation

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Rewindo Dev Test ===${NC}"

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Create temp test repo
TEMP_DIR=$(mktemp -d)
echo -e "${GREEN}Created test repo: $TEMP_DIR${NC}"

cd "$TEMP_DIR"
git init -q
git config user.email "test@rewindo.dev"
git config user.name "Rewindo Test"

# Create initial file
echo "# Test Project" > README.md
git add -A
git commit -q -m "Initial commit"

export CLAUDE_PROJECT_DIR="$TEMP_DIR"

echo -e "\n${YELLOW}Test 1: UserPromptSubmit hook${NC}"
cat <<EOF | python "$PROJECT_ROOT/hooks/log_prompt.py"
{
  "session_id": "test-session-123",
  "transcript_path": "$TEMP_DIR/.claude/projects/test.jsonl",
  "cwd": "$TEMP_DIR",
  "permission_mode": "default",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "Create a simple hello world function in Python"
}
EOF

if [ -f "$TEMP_DIR/.claude/data/prompt_state.json" ]; then
    echo -e "${GREEN}✓ Prompt captured${NC}"
else
    echo -e "${RED}✗ Prompt not captured${NC}"
    exit 1
fi

echo -e "\n${YELLOW}Test 2: Make code change (simulate Claude)${NC}"
cat <<'EOF' > hello.py
def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
EOF

git add -A

echo -e "\n${YELLOW}Test 3: Stop hook (create checkpoint)${NC}"
cat <<EOF | python "$PROJECT_ROOT/hooks/log_stop.py"
{
  "session_id": "test-session-123",
  "transcript_path": "$TEMP_DIR/.claude/projects/test.jsonl",
  "cwd": "$TEMP_DIR",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
EOF

echo -e "\n${YELLOW}Test 4: Verify checkpoint${NC}"

# Check timeline entry exists
if [ -f "$TEMP_DIR/.claude/data/timeline.jsonl" ]; then
    ENTRY_COUNT=$(wc -l < "$TEMP_DIR/.claude/data/timeline.jsonl")
    echo -e "${GREEN}✓ Timeline has $ENTRY_COUNT entry/entries${NC}"
else
    echo -e "${RED}✗ No timeline file${NC}"
    exit 1
fi

# Check git ref exists
if git show-ref | grep -q "refs/rewindo/checkpoints"; then
    echo -e "${GREEN}✓ Checkpoint ref created${NC}"
    git show-ref | grep rewindo
else
    echo -e "${RED}✗ No checkpoint ref found${NC}"
    exit 1
fi

# Check diff file exists
if ls "$TEMP_DIR/.claude/data/diffs/"*.patch 1> /dev/null 2>&1; then
    echo -e "${GREEN}✓ Diff file created${NC}"
else
    echo -e "${RED}✗ No diff file${NC}"
fi

echo -e "\n${YELLOW}Test 5: CLI list command${NC}"
if python "$PROJECT_ROOT/bin/rewindo" --cwd "$TEMP_DIR" list; then
    echo -e "${GREEN}✓ CLI list works${NC}"
else
    echo -e "${RED}✗ CLI list failed${NC}"
fi

echo -e "\n${YELLOW}Test 6: CLI revert command${NC}"
if python "$PROJECT_ROOT/bin/rewindo" --cwd "$TEMP_DIR" revert 1 --yes; then
    echo -e "${GREEN}✓ CLI revert works${NC}"
else
    echo -e "${RED}✗ CLI revert failed${NC}"
fi

# Verify file was reverted
if [ ! -f "$TEMP_DIR/hello.py" ]; then
    echo -e "${GREEN}✓ File successfully reverted (hello.py is gone)${NC}"
else
    echo -e "${RED}✗ File still exists after revert${NC}"
    exit 1
fi

# Cleanup
cd /
rm -rf "$TEMP_DIR"

echo -e "\n${GREEN}=== All tests passed! ===${NC}"
