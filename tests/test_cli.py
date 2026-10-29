import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nkd_agents import cli as cli_module
from nkd_agents.cli import (
    MODELS,
    THINKING,
    AgentCLI,
)
from nkd_agents.tools import bash, edit_file, read_file, write_file
from nkd_agents.tty import TUI

ESC = "\x1b"

FNS = (read_file, write_file, edit_file, bash)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    for name in ("NKD_MODES", "NKD_START_PHRASE", "NKD_COMPACT_TOKENS"):
        monkeypatch.delenv(name, raising=False)


async def forever(*args) -> None:
    await asyncio.Event().wait()


@pytest.fixture
def cli() -> AgentCLI:
    cli = AgentCLI()
    cli.tui.draw = MagicMock()
    cli.tui.log = MagicMock()
    cli.tui.input_loop = AsyncMock(side_effect=forever)
    return cli


@pytest.fixture
def tui(cli: AgentCLI) -> TUI:
    return cli.tui


async def run_until_idle(cli: AgentCLI, delay: float = 0.05) -> None:
    task = asyncio.create_task(cli.run())
    await asyncio.sleep(delay)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


class TestInit:
    def test_defaults(self, cli: AgentCLI):
        assert cli.kwargs["model"] == MODELS[0]
        assert cli.kwargs["thinking"] == THINKING
        assert cli.kwargs["max_tokens"] == 20000
        assert cli.msgs == []
        assert cli.current_task is None

    def test_env_overrides(self, tui, monkeypatch):
        monkeypatch.setenv("NKD_MODES", "A,B")
        monkeypatch.setenv("NKD_START_PHRASE", "hey")
        monkeypatch.setenv("NKD_COMPACT_TOKENS", "7")
        c = AgentCLI()
        assert (c.modes, c.mode, c.start_phrase, c.compact_tokens) == (
            ["A", "B"],
            "A",
            "hey",
            7,
        )

    def test_no_system_without_claude_md(self, cli: AgentCLI):
        assert "system" not in cli.kwargs

    def test_system_from_claude_md(self, tui, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("system prompt")
        assert "system prompt" in AgentCLI().kwargs["system"]


class TestSystemPrompt:
    def test_global_then_local(self, tui, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("global")
        (tmp_path / "CLAUDE.md").write_text("local")
        assert AgentCLI().kwargs["system"] == "global\n\nlocal"

    def test_empty_files_give_none(self, tui, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("")
        (tmp_path / "CLAUDE.md").write_text("  \n")
        assert "system" not in AgentCLI().kwargs


class TestRun:
    async def test_prepends_cwd_mode_and_phrase(self, cli: AgentCLI, tmp_path):
        cli.cycle_mode()
        with patch.object(cli_module, "agent", new_callable=AsyncMock) as llm:
            cli.q.put_nowait("hello")
            await run_until_idle(cli)
        assert cli.msgs == [
            {
                "role": "user",
                "content": f"CWD: {tmp_path} Mode: Plan. {cli.start_phrase} hello",
            }
        ]
        kwargs = llm.call_args.kwargs
        assert llm.call_args.args == (cli.client,)
        assert kwargs["messages"] is cli.msgs
        assert kwargs["fns"] == cli.fns
        assert kwargs["model"] == MODELS[0]

    async def test_batches_queued_submissions(self, cli: AgentCLI):
        with patch.object(cli_module, "agent", new_callable=AsyncMock) as llm:
            cli.q.put_nowait("a")
            cli.q.put_nowait("b")
            await run_until_idle(cli)
        llm.assert_called_once()
        assert cli.msgs[0]["content"].endswith("a\nb")

    async def test_survives_cancelled_turn(self, cli: AgentCLI):
        calls = 0

        async def fake(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise asyncio.CancelledError

        with patch.object(cli_module, "agent", side_effect=fake):
            cli.q.put_nowait("first")
            task = asyncio.create_task(cli.run())
            await asyncio.sleep(0.02)
            cli.q.put_nowait("second")
            await asyncio.sleep(0.02)
            task.cancel()
        assert calls == 2

    async def test_logs_error_and_continues(self, cli: AgentCLI, caplog):
        fake = AsyncMock(side_effect=[RuntimeError("boom"), None])
        with patch.object(cli_module, "agent", fake):
            cli.q.put_nowait("first")
            task = asyncio.create_task(cli.run())
            await asyncio.sleep(0.02)
            cli.q.put_nowait("second")
            await asyncio.sleep(0.02)
            task.cancel()
        assert fake.call_count == 2
        assert "boom" in caplog.text

    async def test_current_task_during_turn_and_redraws(self, cli: AgentCLI, tui: TUI):
        seen: list[bool] = []

        async def fake(*args, **kwargs):
            seen.append(cli.current_task is not None)

        with patch.object(cli_module, "agent", side_effect=fake):
            cli.q.put_nowait("x")
            await run_until_idle(cli)
        assert seen == [True]
        assert cli.current_task is None
        assert tui.draw.call_count == 2


class TestCompact:
    async def test_single_message_not_compacted(self, cli: AgentCLI):
        cli.compact_tokens = 0
        cli.msgs.append({"role": "user", "content": "hi"})
        with patch.object(cli_module, "agent", new_callable=AsyncMock) as llm:
            await cli.turn()
        llm.assert_awaited_once()
        assert cli.msgs == [{"role": "user", "content": "hi"}]

    async def test_summarizes_history_keeps_latest(self, cli: AgentCLI):
        cli.compact_tokens = 1
        cli.msgs.extend({"role": "user", "content": f"m{i}"} for i in range(10))
        llm = AsyncMock(side_effect=["the summary", None])
        with patch.object(cli_module, "agent", llm):
            await cli.turn()
        sent = llm.call_args_list[0].kwargs["messages"]
        assert len(sent) == 10
        assert sent[-1]["content"] == cli_module.COMPACT_PROMPT
        assert [m["role"] for m in cli.msgs] == ["user", "assistant", "user"]
        assert "the summary" in cli.msgs[0]["content"]
        assert cli.msgs[2] == {"role": "user", "content": "m9"}
        assert llm.call_args_list[1].kwargs["messages"] is cli.msgs

    async def test_skips_compact_under_threshold(self, cli: AgentCLI):
        cli.msgs.extend({"role": "user", "content": "x"} for _ in range(3))
        with patch.object(cli_module, "agent", new_callable=AsyncMock) as llm:
            await cli.turn()
        llm.assert_awaited_once()


class TestCLI:
    def test_binds_ui_label(self, cli: AgentCLI):
        assert cli.tui.label() == cli.label()

    def test_bindings(self, cli: AgentCLI):
        assert cli.bindings["\r"] == cli.submit
        assert cli.bindings["\x03"] == cli.quit
        assert cli.bindings[ESC] == cli.escape
        assert cli.bindings["\t"] == cli.switch_model
        assert cli.bindings[ESC + "[Z"] == cli.cycle_mode

    def test_quit_raises_eof(self, cli: AgentCLI):
        with pytest.raises(EOFError):
            cli.quit()

    def test_switch_model_cycles_and_wraps(self, cli: AgentCLI):
        seen = []
        for _ in range(len(MODELS) + 1):
            cli.switch_model()
            seen.append(cli.kwargs["model"])
        assert seen == [*MODELS[1:], MODELS[0], MODELS[1]]

    def test_cycle_mode_wraps(self, cli: AgentCLI):
        seen = []
        for _ in range(len(cli.modes)):
            cli.cycle_mode()
            seen.append(cli.mode)
        assert seen == [*cli.modes[1:], cli.modes[0]]

    def test_label_idle(self, cli: AgentCLI):
        assert cli.label() == "sonnet|act ○ "

    def test_label_busy(self, cli: AgentCLI):
        cli.current_task = MagicMock()
        assert cli.label() == "sonnet|act ● "

    def test_label_tracks_model_and_mode(self, cli: AgentCLI):
        cli.switch_model()
        cli.cycle_mode()
        assert cli.label() == "opus|plan ○ "

    def test_submit_logs_queues_and_clears(self, cli: AgentCLI, tui: TUI):
        tui.buf = "  hello \n"
        cli.submit()
        assert cli.q.get_nowait() == "hello"
        assert tui.buf == ""
        tui.log.assert_called_once()
        assert "hello" in tui.log.call_args.args[0]

    def test_submit_blank_does_nothing(self, cli: AgentCLI, tui: TUI):
        tui.buf = "   "
        cli.submit()
        assert cli.q.empty()
        assert tui.buf == ""
        tui.log.assert_not_called()

    def test_escape_clears_buffer_first(self, cli: AgentCLI, tui: TUI):
        cli.current_task = MagicMock()
        tui.buf = "typed"
        cli.escape()
        assert tui.buf == ""
        cli.current_task.cancel.assert_not_called()

    def test_escape_without_task_is_noop(self, cli: AgentCLI):
        cli.escape()

    def test_escape_interrupts_when_buffer_empty(self, cli: AgentCLI):
        cli.current_task = MagicMock()
        cli.escape()
        cli.current_task.cancel.assert_called_once()


class TestRunWiring:
    async def test_starts_input_loop_with_bindings(self, cli: AgentCLI, tui: TUI):
        await run_until_idle(cli)
        tui.input_loop.assert_awaited_once_with(cli.bindings)

    async def test_quit_ends_run(self, cli: AgentCLI, tui: TUI):
        tui.input_loop = AsyncMock(side_effect=EOFError)
        with pytest.raises(ExceptionGroup) as e:
            await cli.run()
        assert e.group_contains(EOFError)


class TestFns:
    def test_includes_web_tools_when_available(self):
        from nkd_agents.web import fetch_url, web_search

        assert AgentCLI().fns[-2:] == (fetch_url, web_search)

    def test_falls_back_without_web_extra(self, monkeypatch, caplog):
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.endswith("web"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        with caplog.at_level("WARNING"):
            assert AgentCLI().fns == FNS
        assert "web tools unavailable" in caplog.text
