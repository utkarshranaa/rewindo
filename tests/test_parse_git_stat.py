#!/usr/bin/env python3
"""Unit tests for parse_git_stat() in hooks/log_stop.py.

Covers edge cases: spaces in filenames, binary files, unicode,
summary lines, empty input, and large change counts.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Import parse_git_stat directly from log_stop.py
_hooks_dir = Path(__file__).parent.parent / "hooks"
_spec = importlib.util.spec_from_file_location("log_stop", _hooks_dir / "log_stop.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_git_stat = _mod.parse_git_stat
get_last_checkpoint_sha = _mod.get_last_checkpoint_sha


class TestParseGitStat:

    def test_empty_string_returns_empty_list(self):
        assert parse_git_stat("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert parse_git_stat("   \n  \n") == []

    def test_single_file(self):
        output = " hello.py | 5 +++--"
        result = parse_git_stat(output)
        assert len(result) == 1
        assert result[0]["path"] == "hello.py"
        assert result[0]["add"] == 3
        assert result[0]["del"] == 2

    def test_multiple_files(self):
        output = (
            " foo.py  | 10 +++++++---\n"
            " bar.txt |  2 +-\n"
        )
        result = parse_git_stat(output)
        assert len(result) == 2
        assert result[0]["path"] == "foo.py"
        assert result[1]["path"] == "bar.txt"

    def test_file_with_spaces_in_name(self):
        output = " my file with spaces.py | 3 +++"
        result = parse_git_stat(output)
        assert len(result) == 1
        assert result[0]["path"] == "my file with spaces.py"
        assert result[0]["add"] == 3

    def test_file_in_subdirectory(self):
        output = " src/lib/utils.py | 8 +++-----"
        result = parse_git_stat(output)
        assert len(result) == 1
        assert result[0]["path"] == "src/lib/utils.py"
        assert result[0]["add"] == 3
        assert result[0]["del"] == 5

    def test_summary_line_is_skipped(self):
        """The last line of git diff --stat is a summary — should not be parsed."""
        output = (
            " foo.py | 3 +++\n"
            " 1 file changed, 3 insertions(+)\n"
        )
        result = parse_git_stat(output)
        # Summary line doesn't match the pipe pattern, so only foo.py
        assert len(result) == 1
        assert result[0]["path"] == "foo.py"

    def test_only_additions(self):
        output = " new_file.py | 20 ++++++++++++++++++++"
        result = parse_git_stat(output)
        assert result[0]["add"] == 20
        assert result[0]["del"] == 0

    def test_only_deletions(self):
        output = " old_file.py | 10 ----------"
        result = parse_git_stat(output)
        assert result[0]["add"] == 0
        assert result[0]["del"] == 10

    def test_zero_changes(self):
        """File with 0 changes (mode change only)."""
        output = " script.sh | 0"
        result = parse_git_stat(output)
        assert len(result) == 1
        assert result[0]["add"] == 0
        assert result[0]["del"] == 0

    def test_unicode_filename(self):
        output = " résumé.txt | 2 ++"
        result = parse_git_stat(output)
        assert len(result) == 1
        assert result[0]["path"] == "résumé.txt"

    def test_filename_with_brackets(self):
        output = " src/[config].ts | 4 ++++"
        result = parse_git_stat(output)
        assert len(result) == 1
        assert result[0]["path"] == "src/[config].ts"

    def test_large_change_count(self):
        """Git truncates +/- indicators for large changes — total count is in the number."""
        output = " bigfile.py | 500 +++++++++++++++++++++++++++++++++++++++++++++++++++"
        result = parse_git_stat(output)
        assert len(result) == 1
        # The number (500) is captured, not used for add/del directly
        # add/del come from counting + and - in the indicator string
        assert result[0]["path"] == "bigfile.py"

    def test_returns_list_of_dicts_with_correct_keys(self):
        output = " app.py | 1 +"
        result = parse_git_stat(output)
        assert "path" in result[0]
        assert "add" in result[0]
        assert "del" in result[0]


class TestGetLastCheckpointSha:

    def test_returns_none_when_file_missing(self, tmp_path):
        timeline = tmp_path / "timeline.jsonl"
        assert get_last_checkpoint_sha(timeline) is None

    def test_returns_none_for_empty_file(self, tmp_path):
        timeline = tmp_path / "timeline.jsonl"
        timeline.write_text("")
        assert get_last_checkpoint_sha(timeline) is None

    def test_returns_sha_from_single_entry(self, tmp_path):
        import json
        timeline = tmp_path / "timeline.jsonl"
        timeline.write_text(json.dumps({
            "id": 1,
            "checkpoint_sha": "abc123def456"
        }) + "\n")
        assert get_last_checkpoint_sha(timeline) == "abc123def456"

    def test_returns_sha_from_last_entry(self, tmp_path):
        import json
        timeline = tmp_path / "timeline.jsonl"
        with open(timeline, "w") as f:
            f.write(json.dumps({"id": 1, "checkpoint_sha": "sha_one"}) + "\n")
            f.write(json.dumps({"id": 2, "checkpoint_sha": "sha_two"}) + "\n")
        assert get_last_checkpoint_sha(timeline) == "sha_two"

    def test_skips_entries_without_sha(self, tmp_path):
        import json
        timeline = tmp_path / "timeline.jsonl"
        with open(timeline, "w") as f:
            f.write(json.dumps({"id": 1, "checkpoint_sha": "sha_one"}) + "\n")
            f.write(json.dumps({"id": 2}) + "\n")  # no checkpoint_sha
        assert get_last_checkpoint_sha(timeline) == "sha_one"

    def test_skips_corrupted_lines(self, tmp_path):
        import json
        timeline = tmp_path / "timeline.jsonl"
        with open(timeline, "w") as f:
            f.write(json.dumps({"id": 1, "checkpoint_sha": "sha_one"}) + "\n")
            f.write("{invalid json}\n")
            f.write(json.dumps({"id": 3, "checkpoint_sha": "sha_three"}) + "\n")
        assert get_last_checkpoint_sha(timeline) == "sha_three"

    def test_all_corrupted_returns_none(self, tmp_path):
        timeline = tmp_path / "timeline.jsonl"
        timeline.write_text("{bad}\n{also bad}\n")
        assert get_last_checkpoint_sha(timeline) is None

    def test_entries_with_none_sha_are_skipped(self, tmp_path):
        import json
        timeline = tmp_path / "timeline.jsonl"
        with open(timeline, "w") as f:
            f.write(json.dumps({"id": 1, "checkpoint_sha": "sha_one"}) + "\n")
            f.write(json.dumps({"id": 2, "checkpoint_sha": None}) + "\n")
        assert get_last_checkpoint_sha(timeline) == "sha_one"
