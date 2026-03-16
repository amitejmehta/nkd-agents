import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import omit
from anthropic.types import TextBlock, ToolUseBlock

from nkd_agents.anthropic import user
from nkd_agents.cli import CLI, COMPACT_MSG, MODELS, THINKING, TOOLS


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Create a CLI instance with a mock API key, in a clean directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return CLI()


class TestInit:
    def test_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("NKD_AGENTS_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        CLI()  # should not raise

    def test_defaults(self, cli: CLI):
        assert cli.model_idx == 0
        assert cli.kwargs["model"] == MODELS[0]
        assert cli.kwargs["max_tokens"] > 0
        assert cli.kwargs["thinking"] is omit
        assert cli.messages == []
        assert cli.llm_task is None

    def test_loads_claude_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("system prompt")
        assert "system prompt" in CLI().kwargs["system"]

    def test_no_claude_md(self, cli: CLI):
        assert "system" not in cli.kwargs


class TestSwitchModel:
    def test_cycles_through_models(self, cli: CLI):
        assert cli.kwargs["model"] == MODELS[0]
        cli.switch_model()
        assert cli.model_idx == 1
        assert cli.kwargs["model"] == MODELS[1]

    def test_wraps_around(self, cli: CLI):
        for _ in range(len(MODELS)):
            cli.switch_model()
        assert cli.model_idx == 0
        assert cli.kwargs["model"] == MODELS[0]


class TestToggleThinking:
    def test_enable(self, cli: CLI):
        assert cli.kwargs["thinking"] is omit
        cli.toggle_thinking()
        assert cli.kwargs["thinking"] == THINKING

    def test_disable(self, cli: CLI):
        cli.toggle_thinking()
        cli.toggle_thinking()
        assert cli.kwargs["thinking"] is omit


class TestCycleMode:
    def test_cycles_modes(self, cli: CLI):
        initial = cli.mode
        cli.cycle_mode()
        assert cli.mode != initial

    def test_wraps_around(self, cli: CLI):
        from nkd_agents.cli import MODE_PREFIXES

        n = len(MODE_PREFIXES)
        for _ in range(n):
            cli.cycle_mode()
        assert cli.mode == list(MODE_PREFIXES)[0]


class TestInterrupt:
    def test_no_task(self, cli: CLI):
        cli.interrupt()  # should not raise

    def test_done_task(self, cli: CLI):
        cli.llm_task = MagicMock()
        cli.llm_task.done.return_value = True
        cli.interrupt()
        cli.llm_task.cancel.assert_not_called()

    def test_running_task(self, cli: CLI):
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
        assert len(cli.messages) == 3
        assert cli.messages[0]["content"][0]["type"] == "text"
        assert cli.messages[1]["content"][0].type == "text"
        assert cli.messages[2] == user(COMPACT_MSG)

    def test_empty(self, cli: CLI):
        cli.compact_history()
        assert cli.messages == []

    def test_multiple_tool_rounds(self, cli: CLI):
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
        assert len(cli.messages) == 3
        assert cli.messages[0]["role"] == "user"
        assert cli.messages[1]["role"] == "assistant"
        assert cli.messages[2] == user(COMPACT_MSG)

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
        assert cli.messages == [user(COMPACT_MSG)]

    def test_no_tool_messages(self, cli: CLI):
        cli.messages[:] = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": [TextBlock(type="text", text="hello")]},
        ]
        cli.compact_history()
        assert len(cli.messages) == 2


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
                cli.client, cli.messages, TOOLS, **cli.kwargs
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
