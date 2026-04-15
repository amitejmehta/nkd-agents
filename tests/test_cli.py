import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import MessageParam

from nkd_agents.cli import (
    CLI,
    MODELS,
    THINKING,
    TOOLS,
    auto_compact,
)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Create a CLI instance with a mock API key, in a clean directory with no CLAUDE.md."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return CLI()


class TestBottomToolbar:
    def test_shows_model(self, cli: CLI):
        frags = cli.bottom_toolbar()
        text = "".join(f[1] for f in frags)
        assert MODELS[0] in text

    def test_shows_mode(self, cli: CLI):
        frags = cli.bottom_toolbar()
        text = "".join(f[1] for f in frags)
        assert "None" in text

    def test_thinking_off(self, cli: CLI):
        frags = cli.bottom_toolbar()
        text = "".join(f[1] for f in frags)
        assert "✗" in text

    def test_thinking_on(self, cli: CLI):
        cli.kwargs["thinking"] = THINKING
        frags = cli.bottom_toolbar()
        text = "".join(f[1] for f in frags)
        assert "✓" in text

    def test_reflects_model_change(self, cli: CLI):
        cli.switch_model()
        frags = cli.bottom_toolbar()
        text = "".join(f[1] for f in frags)
        assert MODELS[1] in text

    def test_reflects_mode_change(self, cli: CLI):
        cli.cycle_mode()
        frags = cli.bottom_toolbar()
        text = "".join(f[1] for f in frags)
        assert "Plan" in text


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
        assert "thinking" not in cli.kwargs
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
        assert "thinking" not in cli.kwargs
        cli.toggle_thinking()
        assert cli.kwargs["thinking"] == THINKING

    def test_disable(self, cli: CLI):
        cli.kwargs["thinking"] = THINKING
        cli.toggle_thinking()
        assert "thinking" not in cli.kwargs


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
            mock_llm.assert_called_once_with(
                cli.client, messages=cli.messages, fns=TOOLS, **cli.kwargs
            )

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


class TestBuildSystemPrompt:
    def test_neither_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert CLI().build_system_prompt() is None

    def test_global_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        global_md = tmp_path / ".nkd-agents" / "CLAUDE.md"
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
        global_md = tmp_path / ".nkd-agents" / "CLAUDE.md"
        global_md.parent.mkdir()
        global_md.write_text("global content")
        (tmp_path / "CLAUDE.md").write_text("local content")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = CLI().build_system_prompt()
        assert result is not None
        assert result.index("global content") < result.index("local content")

    def test_appends_cwd_and_home(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / "CLAUDE.md").write_text("local content")
        result = CLI().build_system_prompt()
        assert result is not None
        assert f"CWD: {tmp_path}" in result
        assert f"HOME: {tmp_path}" in result

    def test_empty_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        global_md = tmp_path / ".nkd-agents" / "CLAUDE.md"
        global_md.parent.mkdir()
        global_md.write_text("")
        (tmp_path / "CLAUDE.md").write_text("")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert CLI().build_system_prompt() is None


class TestBuildMessage:
    def test_none_mode(self, cli: CLI):
        from nkd_agents.cli import START_PHRASE

        result = cli.build_message("do something")
        assert result.startswith(START_PHRASE)
        assert "Mode: None." in result
        assert result.endswith(" do something")
        assert "(" not in result

    def test_plan_mode(self, cli: CLI):
        from nkd_agents.cli import MODE_PREFIXES

        cli.mode = "plan"
        result = cli.build_message("review this")
        assert "Mode: Plan" in result
        assert f"({MODE_PREFIXES['plan']})" in result
        assert result.endswith(" review this")

    def test_socratic_mode(self, cli: CLI):
        from nkd_agents.cli import MODE_PREFIXES

        cli.mode = "socratic"
        result = cli.build_message("explain this")
        assert "Mode: Socratic" in result
        assert f"({MODE_PREFIXES['socratic']})" in result
        assert result.endswith(" explain this")

    def test_custom_start_phrase(self, tmp_path, monkeypatch):
        import importlib

        import nkd_agents.cli as cli_mod

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("NKD_START_PHRASE", "Custom phrase.")
        importlib.reload(cli_mod)
        cli = cli_mod.CLI()
        result = cli.build_message("task")
        assert result.startswith("Custom phrase.")

    def test_custom_plan_prefix(self, tmp_path, monkeypatch):
        import importlib

        import nkd_agents.cli as cli_mod

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("NKD_PLAN_MODE", "HANDS OFF!")
        importlib.reload(cli_mod)
        cli = cli_mod.CLI()
        cli.mode = "plan"
        result = cli.build_message("review")
        assert "(HANDS OFF!)" in result


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


class TestAutoCompact:
    async def test_no_op_below_threshold(self, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 10)
        msgs = [_user_text(f"msg{i}") for i in range(9)]
        with patch("nkd_agents.cli.agent", new_callable=AsyncMock) as mock_agent:
            await auto_compact(msgs, AsyncMock())
        mock_agent.assert_not_called()
        assert len(msgs) == 9

    async def test_summarizes_old_messages(self, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 6)
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_TARGET", 4)
        msgs = [
            _user_text("task A"),
            _assistant_tool_use("t0"),
            _user_tool_result("t0"),
            _assistant_text("done A"),
            _user_text("task B"),
            _assistant_tool_use("t1"),
            _user_tool_result("t1"),
            _assistant_text("done B"),
        ]
        with patch(
            "nkd_agents.cli.agent",
            new_callable=AsyncMock,
            return_value="Completed task A.",
        ):
            await auto_compact(msgs, AsyncMock())
        assert len(msgs) == 5  # 1 summary + 4 protected
        assert msgs[0]["role"] == "user"
        assert "conversation_summary" in msgs[0]["content"][0]["text"]
        assert msgs[1] == _user_text("task B")

    async def test_summary_content_injected(self, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 4)
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_TARGET", 2)
        msgs = [
            _user_text("first"),
            _assistant_text("reply"),
            _user_text("second"),
            _assistant_text("reply2"),
            _user_text("third"),
        ]
        with patch(
            "nkd_agents.cli.agent",
            new_callable=AsyncMock,
            return_value="User discussed first and second topics.",
        ):
            await auto_compact(msgs, AsyncMock())
        assert (
            "User discussed first and second topics." in msgs[0]["content"][0]["text"]
        )

    async def test_calls_agent_with_correct_args(self, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 4)
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_TARGET", 2)
        monkeypatch.setattr("nkd_agents.cli.COMPACT_MODEL", "claude-haiku-4-5")
        msgs = [
            _user_text("do X"),
            _assistant_text("did X"),
            _user_text("do Y"),
            _assistant_text("did Y"),
            _user_text("do Z"),
        ]
        with patch(
            "nkd_agents.cli.agent", new_callable=AsyncMock, return_value="Summary"
        ) as mock_agent:
            await auto_compact(msgs, AsyncMock())
        kw = mock_agent.call_args.kwargs
        assert kw["model"] == "claude-haiku-4-5"
        assert kw["max_tokens"] == 2048
        sent = kw["messages"]
        assert sent[-1]["role"] == "user"  # summary prompt appended last
        assert sent[0]["role"] == "user"  # old messages intact

    async def test_stacks_existing_summary(self, monkeypatch):
        """Prior <conversation_summary> is fed to agent so new summary is cumulative."""
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 4)
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_TARGET", 2)
        prior: MessageParam = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "<conversation_summary>\nPrior work.\n</conversation_summary>\n\nContinue.",
                }
            ],
        }
        msgs = [
            prior,
            _assistant_text("ok"),
            _user_text("new task"),
            _assistant_text("done"),
            _user_text("next"),
        ]
        with patch(
            "nkd_agents.cli.agent", new_callable=AsyncMock, return_value="Updated."
        ) as mock_agent:
            await auto_compact(msgs, AsyncMock())
        sent = mock_agent.call_args.kwargs["messages"]
        assert any("conversation_summary" in str(m.get("content", "")) for m in sent)

    async def test_orphan_protection_at_boundary(self, monkeypatch):
        """Boundary landing on tool_result walks back — no orphaned pairs."""
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 4)
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_TARGET", 2)
        msgs = [
            _user_text("a"),
            _assistant_tool_use("t0"),
            _user_tool_result("t0"),
            _assistant_text("done"),
            _user_text("q"),
            _assistant_text("r"),
        ]
        with patch(
            "nkd_agents.cli.agent", new_callable=AsyncMock, return_value="Summary"
        ):
            await auto_compact(msgs, AsyncMock())
        tool_use_ids = {
            b["id"]
            for m in msgs
            for b in m.get("content", [])
            if isinstance(b, dict) and b.get("type") == "tool_use"
        }
        tool_result_ids = {
            b["tool_use_id"]
            for m in msgs
            for b in m.get("content", [])
            if isinstance(b, dict) and b.get("type") == "tool_result"
        }
        assert tool_use_ids == tool_result_ids

    async def test_preserves_protected_region(self, monkeypatch):
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_AFTER", 4)
        monkeypatch.setattr("nkd_agents.cli.AUTO_COMPACT_TARGET", 2)
        msgs = [
            _user_text("a"),
            _assistant_text("b"),
            _user_text("c"),
            _assistant_text("d"),
            _user_text("e"),
        ]
        with patch(
            "nkd_agents.cli.agent", new_callable=AsyncMock, return_value="Summary."
        ):
            await auto_compact(msgs, AsyncMock())
        assert "conversation_summary" in msgs[0]["content"][0]["text"]
        assert msgs[1] == _user_text("c")
