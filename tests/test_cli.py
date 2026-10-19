import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import MessageParam

from nkd_agents.cli import (
    CLI,
    MODELS,
    MODES,
    START_PHRASE,
    default_fns,
)
from nkd_agents.tools import bash, edit_file, read_file, write_file
from nkd_agents.tty import ESC

NAMES = list(MODELS)
FNS = (read_file, write_file, edit_file, bash)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Create a CLI instance with a mock API key, in a clean directory with no CLAUDE.md."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return CLI(FNS)


class TestToolbar:
    def test_shows_model(self, cli: CLI):
        assert NAMES[0].split("-")[1].capitalize() in cli.toolbar()

    def test_shows_mode(self, cli: CLI):
        assert "Act" in cli.toolbar()

    def test_thinking_off(self, cli: CLI):
        assert "think:✗" in cli.toolbar()

    def test_thinking_on(self, cli: CLI):
        cli.toggle_thinking()
        assert "think:✓" in cli.toolbar()

    def test_reflects_model_change(self, cli: CLI):
        cli.switch_model()
        assert NAMES[1].split("-")[1].capitalize() in cli.toolbar()

    def test_reflects_mode_change(self, cli: CLI):
        cli.cycle_mode()
        assert "Plan" in cli.toolbar()

    def test_idle_shows_hollow_circle(self, cli: CLI):
        assert cli.toolbar().startswith(" ○ ")

    def test_running_shows_filled_circle(self, cli: CLI):
        cli.llm_task = MagicMock(done=lambda: False)
        assert cli.toolbar().startswith(" ● ")


class TestDelete:
    @pytest.mark.parametrize("key", ["\x17", "\x1b\x7f"])
    def test_deletes_last_word(self, cli: CLI, key: str):
        cli.session.buf = "foo bar  "
        cli.session._handle(key)
        assert cli.session.buf == "foo "
        cli.session._handle(key)
        assert cli.session.buf == ""

    def test_plain_delete_is_unbound(self, cli: CLI):
        cli.session.buf = "foo"
        cli.session._handle("\x7f")
        assert cli.session.buf == "foo"


class TestDefaultFns:
    def test_includes_web_tools_when_available(self):
        from nkd_agents.web import fetch_url, web_search

        assert default_fns()[-2:] == (fetch_url, web_search)

    def test_falls_back_without_web_extra(self, monkeypatch, caplog):
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.endswith("web"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        with caplog.at_level("WARNING"):
            assert default_fns() == FNS
        assert "web tools unavailable" in caplog.text


class TestInit:
    def test_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("NKD_AGENTS_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        CLI(FNS)  # should not raise

    def test_defaults(self, cli: CLI):
        assert cli.kwargs["model"] == NAMES[0]
        assert cli.kwargs["max_tokens"] > 0
        assert cli.kwargs["thinking"] == {"type": "between_tools"}
        assert cli.messages == []
        assert cli.llm_task is None

    def test_loads_claude_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("system prompt")
        assert "system prompt" in CLI(FNS).kwargs["system"]

    def test_no_claude_md(self, cli: CLI):
        assert "system" not in cli.kwargs


class TestSwitchModel:
    def test_cycles_through_models(self, cli: CLI):
        assert cli.kwargs["model"] == NAMES[0]
        cli.switch_model()
        assert cli.kwargs["model"] == NAMES[1]

    def test_wraps_around(self, cli: CLI):
        for _ in range(len(NAMES)):
            cli.switch_model()
        assert cli.kwargs["model"] == NAMES[0]


class TestToggleThinking:
    def test_sonnet_5_5_toggles(self, cli: CLI):
        assert cli.kwargs["model"] == "claude-sonnet-5-5"
        assert cli.kwargs["thinking"] == {"type": "between_tools"}
        cli.toggle_thinking()
        assert cli.kwargs["thinking"]["type"] == "adaptive"
        cli.toggle_thinking()
        assert cli.kwargs["thinking"] == {"type": "between_tools"}

    def test_opus_5_5_never_disabled(self, cli: CLI):
        cli.switch_model()
        assert cli.kwargs["model"] == "claude-opus-5-5"
        assert cli.kwargs["thinking"]["type"] == "adaptive"
        cli.toggle_thinking()
        assert cli.kwargs["thinking"]["type"] == "adaptive"

    def test_haiku_5_5_toggles(self, cli: CLI):
        cli.switch_model()
        cli.switch_model()
        assert cli.kwargs["model"] == "claude-haiku-5-5"
        assert cli.kwargs["thinking"] == {"type": "disabled"}
        cli.toggle_thinking()
        assert cli.kwargs["thinking"]["type"] == "adaptive"
        cli.toggle_thinking()
        assert cli.kwargs["thinking"] == {"type": "disabled"}

    def test_switch_model_resets_thinking(self, cli: CLI):
        cli.toggle_thinking()
        for _ in range(len(NAMES)):
            cli.switch_model()
        assert cli.kwargs["thinking"] == {"type": "between_tools"}


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
        cli.session.buf = "some input"
        cli.interrupt()
        assert cli.session.buf == ""
        cli.llm_task.cancel.assert_not_called()

    def test_cancels_task_when_buffer_empty(self, cli: CLI):
        cli.llm_task = MagicMock()
        cli.llm_task.done.return_value = False
        cli.interrupt()
        cli.llm_task.cancel.assert_called_once()


class TestLLMLoop:
    async def test_processes_queue(self, cli: CLI):
        with (
            patch("nkd_agents.cli.agent", new_callable=AsyncMock) as mock_llm,
            patch.object(cli, "count_tokens", AsyncMock(return_value=0)),
        ):
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
            assert call_kwargs.kwargs["fns"] == FNS

    async def test_survives_cancelled_llm_task(self, cli: CLI):
        call_count = 0

        async def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.CancelledError()

        with (
            patch("nkd_agents.cli.agent", side_effect=mock_llm),
            patch.object(cli, "count_tokens", AsyncMock(return_value=0)),
        ):
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

    async def test_count_tokens_failure_does_not_kill_loop(self, cli: CLI):
        cli.messages.append({"role": "user", "content": "earlier"})
        counter = AsyncMock(side_effect=[RuntimeError("boom"), 0])

        with (
            patch("nkd_agents.cli.agent", new_callable=AsyncMock) as mock_llm,
            patch.object(cli, "count_tokens", counter),
        ):
            await cli.queue.put({"role": "user", "content": "first"})
            await cli.queue.put({"role": "user", "content": "second"})
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
        assert counter.call_count == 2
        mock_llm.assert_called_once()
        assert cli.messages[-1]["content"] == "second"


class TestCountTokens:
    async def test_returns_api_input_tokens(self, cli: CLI):
        mock_resp = MagicMock(input_tokens=42)
        with patch.object(
            cli.client.messages, "count_tokens", AsyncMock(return_value=mock_resp)
        ) as mock_count:
            result = await cli.count_tokens()
        assert result == 42
        mock_count.assert_called_once()
        call_kwargs = mock_count.call_args.kwargs
        assert call_kwargs["messages"] is cli.messages
        assert "max_tokens" not in call_kwargs


def _mock_create_response(text: str) -> MagicMock:
    block = MagicMock(type="text", text=text)
    return MagicMock(content=[block])


class TestCompact:
    async def test_noop_when_only_latest_message(self, cli: CLI):
        cli.messages.append(_user_text("hi"))
        with patch.object(
            cli.client.messages, "create", new_callable=AsyncMock
        ) as mock_create:
            await cli.compact()
            mock_create.assert_not_called()
        assert cli.messages == [_user_text("hi")]

    async def test_summarizes_history_and_keeps_latest(self, cli: CLI):
        cli.messages.extend({"role": "user", "content": f"msg{i}"} for i in range(10))

        with patch.object(
            cli.client.messages,
            "create",
            AsyncMock(return_value=_mock_create_response("summary text")),
        ) as mock_create:
            await cli.compact()
            call_kwargs = mock_create.call_args.kwargs
            assert len(call_kwargs["messages"]) == 11

        assert len(cli.messages) == 3
        assert "summary text" in cli.messages[0]["content"]
        assert cli.messages[1]["role"] == "assistant"
        assert cli.messages[2] == {"role": "user", "content": "msg9"}

    async def test_handles_tool_use_pairs_without_splitting(self, cli: CLI):
        cli.messages.extend(
            [
                _user_text("earlier"),
                _assistant_tool_use(),
                _user_tool_result(),
                _user_text("latest"),
            ]
        )

        with patch.object(
            cli.client.messages,
            "create",
            AsyncMock(return_value=_mock_create_response("summary text")),
        ):
            await cli.compact()

        assert len(cli.messages) == 3
        assert "summary text" in cli.messages[0]["content"]
        assert cli.messages[2] == _user_text("latest")


class TestLLMLoopCompactTrigger:
    async def test_triggers_compact_over_threshold(self, cli: CLI, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.COMPACT_TOKENS", 1)
        cli.messages.append({"role": "user", "content": "earlier"})
        seen: list[int] = []

        async def mock_compact():
            seen.append(len(cli.messages))
            cli.messages[:] = [cli.messages[-1]]

        with (
            patch("nkd_agents.cli.agent", new_callable=AsyncMock),
            patch.object(cli, "count_tokens", AsyncMock(return_value=100)),
            patch.object(cli, "compact", side_effect=mock_compact),
        ):
            await cli.queue.put({"role": "user", "content": "hello"})
            loop_task = asyncio.create_task(cli.llm_loop())
            await asyncio.sleep(0.05)
            loop_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await loop_task
        assert seen == [2]
        assert [m["content"] for m in cli.messages] == ["hello"]

    async def test_skips_compact_under_threshold(self, cli: CLI, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.COMPACT_TOKENS", 10_000_000)
        cli.messages.append({"role": "user", "content": "earlier"})

        with (
            patch("nkd_agents.cli.agent", new_callable=AsyncMock),
            patch.object(cli, "count_tokens", AsyncMock(return_value=100)),
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
        assert CLI(FNS).build_system_prompt() is None

    def test_global_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        global_md = tmp_path / ".claude" / "CLAUDE.md"
        global_md.parent.mkdir()
        global_md.write_text("global content")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = CLI(FNS).build_system_prompt()
        assert result is not None
        assert "global content" in result

    def test_local_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / "CLAUDE.md").write_text("local content")
        result = CLI(FNS).build_system_prompt()
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
        result = CLI(FNS).build_system_prompt()
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
        assert CLI(FNS).build_system_prompt() is None


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
