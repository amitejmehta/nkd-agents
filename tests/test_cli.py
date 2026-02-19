import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import omit
from anthropic.types import TextBlock, ToolUseBlock

from nkd_agents.cli import CLI, MODELS, PLAN_MODE_PREFIX, TOOLS, _load_skill


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Create a CLI instance with a mock API key, in a clean directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NKD_AGENTS_ANTHROPIC_API_KEY", "test-key")
    return CLI()


class TestInit:
    def test_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("NKD_AGENTS_ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="NKD_AGENTS_ANTHROPIC_API_KEY"):
            CLI()

    def test_defaults(self, cli: CLI):
        assert cli.model_idx == 0
        assert cli.settings["model"] == MODELS[0]
        assert cli.settings["max_tokens"] == 20000
        assert cli.settings["thinking"] is omit
        assert cli.plan_mode == ""
        assert cli.messages == []
        assert cli.llm_task is None

    def test_loads_claude_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NKD_AGENTS_ANTHROPIC_API_KEY", "test-key")
        (tmp_path / "CLAUDE.md").write_text("system prompt")
        assert CLI().settings["system"] == "system prompt"

    def test_no_claude_md(self, cli: CLI):
        assert "system" not in cli.settings


class TestSwitchModel:
    def test_cycles_through_models(self, cli: CLI):
        assert cli.settings["model"] == MODELS[0]
        cli.switch_model()
        assert cli.model_idx == 1
        assert cli.settings["model"] == MODELS[1]

    def test_wraps_around(self, cli: CLI):
        for _ in range(len(MODELS)):
            cli.switch_model()
        assert cli.model_idx == 0
        assert cli.settings["model"] == MODELS[0]


class TestToggleThinking:
    def test_enable(self, cli: CLI):
        assert cli.settings["thinking"] is omit
        cli.toggle_thinking()
        assert cli.settings["thinking"] == {"type": "adaptive"}

    def test_disable(self, cli):
        cli.toggle_thinking()
        cli.toggle_thinking()
        assert cli.settings["thinking"] is omit


class TestTogglePlanMode:
    def test_toggle_on_off(self, cli: CLI):
        assert cli.plan_mode == ""
        cli.toggle_plan_mode()
        assert cli.plan_mode == PLAN_MODE_PREFIX
        cli.toggle_plan_mode()
        assert cli.plan_mode == ""


class TestInterrupt:
    def test_no_task(self, cli: CLI):
        cli.interrupt()  # should not raise

    def test_done_task(self, cli: CLI):
        cli.llm_task = MagicMock()
        cli.llm_task.done.return_value = True
        cli.interrupt()
        cli.llm_task.cancel.assert_not_called()

    def test_running_task(self, cli):
        cli.llm_task = MagicMock()
        cli.llm_task.done.return_value = False
        cli.interrupt()
        cli.llm_task.cancel.assert_called_once()


class TestCompactHistory:
    def test_removes_tool_messages(self, cli: CLI):
        cli.messages[:] = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    ToolUseBlock(type="tool_use", id="1", name="bash", input={})
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "ok"}
                ],
            },
            {"role": "assistant", "content": [TextBlock(type="text", text="done")]},
        ]
        cli.compact_history()
        assert len(cli.messages) == 2
        assert cli.messages[0]["content"][0]["type"] == "text"
        assert cli.messages[1]["content"][0].type == "text"

    def test_empty(self, cli: CLI):
        cli.compact_history()
        assert cli.messages == []

    def test_multiple_tool_rounds(self, cli):
        cli.messages[:] = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    ToolUseBlock(type="tool_use", id="1", name="bash", input={})
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "ok"}
                ],
            },
            {
                "role": "assistant",
                "content": [
                    ToolUseBlock(type="tool_use", id="2", name="bash", input={})
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "2", "content": "ok"}
                ],
            },
            {"role": "assistant", "content": [TextBlock(type="text", text="done")]},
        ]
        cli.compact_history()
        assert len(cli.messages) == 2
        assert cli.messages[0]["role"] == "user"
        assert cli.messages[1]["role"] == "assistant"

    def test_all_tool_messages(self, cli: CLI):
        cli.messages[:] = [
            {
                "role": "assistant",
                "content": [
                    ToolUseBlock(type="tool_use", id="1", name="bash", input={})
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "ok"}
                ],
            },
        ]
        cli.compact_history()
        assert cli.messages == []

    def test_no_tool_messages(self, cli: CLI):
        cli.messages[:] = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": [TextBlock(type="text", text="hello")]},
        ]
        cli.compact_history()
        assert len(cli.messages) == 2


class TestLoadSkill:
    def test_returns_correct_content(self, tmp_path):
        (tmp_path / "alpha.md").write_text("skill alpha content")
        (tmp_path / "beta.md").write_text("skill beta content")
        assert _load_skill(tmp_path, "1") == "skill alpha content"
        assert _load_skill(tmp_path, "2") == "skill beta content"

    def test_invalid_number_returns_none(self, tmp_path):
        (tmp_path / "alpha.md").write_text("skill alpha content")
        assert _load_skill(tmp_path, "99") is None

    def test_non_numeric_input_returns_none(self, tmp_path):
        (tmp_path / "alpha.md").write_text("skill alpha content")
        assert _load_skill(tmp_path, "abc") is None

    def test_empty_dir_returns_none(self, tmp_path):
        assert _load_skill(tmp_path, "1") is None

    def test_only_md_files_listed(self, tmp_path):
        (tmp_path / "alpha.md").write_text("md content")
        (tmp_path / "ignored.txt").write_text("txt content")
        # Only the .md file counts, so "1" should return the md content
        assert _load_skill(tmp_path, "1") == "md content"
        # "2" should return None (no second .md file)
        assert _load_skill(tmp_path, "2") is None


class TestLLMLoop:
    async def test_processes_queue(self, cli: CLI):
        with patch("nkd_agents.cli.llm", new_callable=AsyncMock) as mock_llm:
            msg = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
            await cli.queue.put(msg)
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
            assert len(cli.messages) == 1
            assert cli.messages[0] is msg
            mock_llm.assert_called_once_with(
                cli.client, cli.messages, TOOLS, **cli.settings
            )

    async def test_survives_cancelled_llm_task(self, cli: CLI):
        call_count = 0

        async def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.CancelledError()

        with patch("nkd_agents.cli.llm", side_effect=mock_llm):
            await cli.queue.put(
                {"role": "user", "content": [{"type": "text", "text": "first"}]}
            )
            await cli.queue.put(
                {"role": "user", "content": [{"type": "text", "text": "second"}]}
            )
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
            assert call_count == 2
            assert len(cli.messages) == 2
