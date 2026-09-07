import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import MessageParam

from nkd_agents.cli import (
    CLI,
    MODELS,
    MODES,
    START_PHRASE,
    TOOLS,
)
from nkd_agents.tty import ESC


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Create a CLI instance with a mock API key, in a clean directory with no CLAUDE.md."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return CLI()


class TestToolbar:
    def test_shows_model(self, cli: CLI):
        assert MODELS[0].split("claude-")[1] in cli.toolbar()

    def test_shows_mode(self, cli: CLI):
        assert "Act" in cli.toolbar()

    def test_thinking_off(self, cli: CLI):
        assert "think:✗" in cli.toolbar()

    def test_thinking_on(self, cli: CLI):
        cli.toggle_thinking()
        assert "think:✓" in cli.toolbar()

    def test_reflects_model_change(self, cli: CLI):
        cli.switch_model()
        assert MODELS[1].split("claude-")[1] in cli.toolbar()

    def test_reflects_mode_change(self, cli: CLI):
        cli.cycle_mode()
        assert "Plan" in cli.toolbar()


class TestInit:
    def test_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("NKD_AGENTS_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        CLI()  # should not raise

    def test_defaults(self, cli: CLI):
        assert cli.kwargs["model"] == MODELS[0]
        assert cli.kwargs["max_tokens"] > 0
        assert cli.kwargs["thinking"] == {"type": "disabled"}
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
        assert cli.kwargs["model"] == MODELS[1]

    def test_wraps_around(self, cli: CLI):
        for _ in range(len(MODELS)):
            cli.switch_model()
        assert cli.kwargs["model"] == MODELS[0]

    def test_syncs_idx_with_nkd_model(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("NKD_MODEL", MODELS[1])
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        cli = CLI()
        assert cli.kwargs["model"] == MODELS[1]
        cli.switch_model()
        assert cli.kwargs["model"] == MODELS[2]


class TestToggleThinking:
    def test_toggles(self, cli: CLI):
        assert cli.kwargs["thinking"]["type"] == "disabled"
        cli.toggle_thinking()
        assert cli.kwargs["thinking"]["type"] == "adaptive"
        cli.toggle_thinking()
        assert cli.kwargs["thinking"]["type"] == "disabled"


class TestCycleMode:
    def test_cycles_modes(self, cli: CLI):
        initial = cli.mode
        cli.cycle_mode()
        assert cli.mode != initial

    def test_wraps_around(self, cli: CLI):
        for _ in range(len(MODES)):
            cli.cycle_mode()
        assert cli.mode == MODES[0]


class TestPromptLoop:
    async def test_queues_cwd_mode_and_phrase_prefixed_message(
        self, cli: CLI, tmp_path
    ):
        cli.mode = MODES[1]
        with patch.object(
            cli.session,
            "prompt_async",
            AsyncMock(side_effect=["hello", asyncio.CancelledError]),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cli.prompt_loop()

        message = await cli.queue.get()
        assert message["role"] == "user"
        assert message["content"] == (
            f"CWD: {tmp_path} Mode: {MODES[1]}. {START_PHRASE} hello"
        )

    async def test_skips_blank_input(self, cli: CLI):
        with patch.object(
            cli.session,
            "prompt_async",
            AsyncMock(side_effect=["   ", asyncio.CancelledError]),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cli.prompt_loop()
        assert cli.queue.empty()


class TestInterrupt:
    def test_escape_binding(self, cli: CLI):
        assert ESC in cli.session.key_bindings

    def test_no_task(self, cli: CLI):
        cli.llm_task = None
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

    def test_clears_buffer_when_text_present(self, cli: CLI):
        cli.llm_task = MagicMock()
        cli.llm_task.done.return_value = False
        cli.session.buf, cli.session.cursor = "some input", 4
        cli.interrupt()
        assert (cli.session.buf, cli.session.cursor) == ("", 0)
        cli.llm_task.cancel.assert_not_called()

    def test_cancels_task_when_buffer_empty(self, cli: CLI):
        cli.llm_task = MagicMock()
        cli.llm_task.done.return_value = False
        cli.interrupt()
        cli.llm_task.cancel.assert_called_once()


class TestLLMLoop:
    async def test_processes_queue(self, cli: CLI):
        with patch("nkd_agents.cli.agent", new_callable=AsyncMock) as mock_llm:
            msg: MessageParam = {
                "role": "user",
                "content": [{"type": "text", "text": "hi"}],
            }
            await cli.queue.put(msg)
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
            assert len(cli.messages) == 1
            assert cli.messages[0] is msg
            mock_llm.assert_called_once()
            call_kwargs = mock_llm.call_args
            assert call_kwargs.args == (cli.client,)
            assert call_kwargs.kwargs["messages"] is cli.messages
            assert call_kwargs.kwargs["fns"] == TOOLS

    async def test_survives_cancelled_llm_task(self, cli: CLI):
        call_count = 0

        async def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.CancelledError()

        with patch("nkd_agents.cli.agent", side_effect=mock_llm):
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


class TestApproxTokens:
    def test_empty(self, cli: CLI):
        assert cli._approx_tokens() == 0

    def test_grows_with_messages(self, cli: CLI):
        cli.messages.append({"role": "user", "content": "x" * 400})
        assert cli._approx_tokens() > 90


class TestCompact:
    async def test_noop_when_few_messages(self, cli: CLI):
        cli.messages.append({"role": "user", "content": "hi"})
        with patch("nkd_agents.cli.agent", new_callable=AsyncMock) as mock_agent:
            await cli.compact()
            mock_agent.assert_not_called()
        assert len(cli.messages) == 1

    async def test_summarizes_head_and_keeps_recent_tail(self, cli: CLI):
        from nkd_agents.cli import COMPACT_TAIL

        cli.messages.extend({"role": "user", "content": f"msg{i}"} for i in range(10))
        tail_before = cli.messages[-COMPACT_TAIL:]

        with patch(
            "nkd_agents.cli.agent", AsyncMock(return_value="summary text")
        ) as mock_agent:
            await cli.compact()
            call_kwargs = mock_agent.call_args.kwargs
            assert len(call_kwargs["messages"]) == 10 - COMPACT_TAIL + 1

        assert cli.messages[-COMPACT_TAIL:] == tail_before
        assert "summary text" in cli.messages[0]["content"]
        assert len(cli.messages) == 2 + COMPACT_TAIL


class TestLLMLoopCompactTrigger:
    async def test_triggers_compact_over_threshold(self, cli: CLI, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.COMPACT_TOKEN_THRESHOLD", 1)

        async def mock_llm(*args, **kwargs):
            kwargs["messages"].append({"role": "assistant", "content": "hi"})

        with (
            patch("nkd_agents.cli.agent", side_effect=mock_llm),
            patch.object(cli, "compact", new_callable=AsyncMock) as mock_compact,
        ):
            await cli.queue.put({"role": "user", "content": "hello"})
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
            mock_compact.assert_called_once()

    async def test_skips_compact_under_threshold(self, cli: CLI, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.COMPACT_TOKEN_THRESHOLD", 10_000_000)

        async def mock_llm(*args, **kwargs):
            kwargs["messages"].append({"role": "assistant", "content": "hi"})

        with (
            patch("nkd_agents.cli.agent", side_effect=mock_llm),
            patch.object(cli, "compact", new_callable=AsyncMock) as mock_compact,
        ):
            await cli.queue.put({"role": "user", "content": "hello"})
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
            mock_compact.assert_not_called()


class TestBuildSystemPrompt:
    def test_neither_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert CLI().build_system_prompt() is None

    def test_global_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        global_md = tmp_path / ".claude" / "CLAUDE.md"
        global_md.parent.mkdir()
        global_md.write_text("global content")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = CLI().build_system_prompt()
        assert result is not None
        assert "global content" in result

    def test_local_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / "CLAUDE.md").write_text("local content")
        result = CLI().build_system_prompt()
        assert result is not None
        assert "local content" in result

    def test_both_global_first(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        global_md = tmp_path / ".claude" / "CLAUDE.md"
        global_md.parent.mkdir()
        global_md.write_text("global content")
        (tmp_path / "CLAUDE.md").write_text("local content")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = CLI().build_system_prompt()
        assert result is not None
        assert result.index("global content") < result.index("local content")

    def test_empty_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        global_md = tmp_path / ".claude" / "CLAUDE.md"
        global_md.parent.mkdir()
        global_md.write_text("")
        (tmp_path / "CLAUDE.md").write_text("")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert CLI().build_system_prompt() is None


# --- helpers for auto_compact tests ---


def _user_text(text: str) -> MessageParam:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _assistant_tool_use(tool_id: str = "t1") -> MessageParam:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tool_id, "name": "bash", "input": {}}],
    }


def _user_tool_result(tool_id: str = "t1") -> MessageParam:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}],
    }


def _assistant_text(text: str = "done") -> MessageParam:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def _mock_client() -> AsyncMock:
    client = AsyncMock()
    client.messages.create = AsyncMock()
    return client
