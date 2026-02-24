import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import omit
from anthropic.types import TextBlock, ToolUseBlock
from prompt_toolkit.document import Document

from nkd_agents.cli import CLI, MODELS, PLAN_MODE_PREFIX, TOOLS


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
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # CLI no longer validates key at init; AsyncAnthropic accepts missing key
        CLI()  # should not raise

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
        assert "system prompt" in CLI().settings["system"]

    def test_no_claude_md(self, cli: CLI):
        assert cli.settings["system"].startswith("Working directory:")


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


class TestCycleSkillPrompt:
    @pytest.fixture
    def skills_dir(self, tmp_path, monkeypatch):
        """Isolated skills dir with no builtins."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("nkd_agents.cli.__file__", str(tmp_path / "fake_cli.py"))
        d = tmp_path / "skills"
        d.mkdir()
        return d

    def test_empty_returns_blank(self, cli: CLI, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no skills/ dir at all
        monkeypatch.setattr("nkd_agents.cli.__file__", str(tmp_path / "fake_cli.py"))
        assert cli.cycle_prompt() == Document("", 0)

    def test_flat_skill_xml_and_cursor(self, cli: CLI, skills_dir):
        """Flat *.md: correct XML tags, stem, content, cursor at end."""
        (skills_dir / "debug.md").write_text("debug content")
        cli.prompt_idx = -1
        doc = cli.cycle_prompt()
        assert doc.text == "<skill debug>\ndebug content\n</skill debug>\n"
        assert doc.cursor_position == len(doc.text)

    def test_nested_anthropic_style(self, cli: CLI, skills_dir):
        """Nested skills/debug/skill.md uses parent dir name as stem."""
        (skills_dir / "debug").mkdir()
        (skills_dir / "debug" / "skill.md").write_text("nested content")
        cli.prompt_idx = -1
        doc = cli.cycle_prompt()
        assert doc.text == "<skill debug>\nnested content\n</skill debug>\n"

    def test_flat_and_nested_together(self, cli: CLI, skills_dir):
        """Both formats coexist; collect all docs and verify both stems appear."""
        (skills_dir / "aaa.md").write_text("flat")
        (skills_dir / "zzz").mkdir()
        (skills_dir / "zzz" / "skill.md").write_text("nested")
        cli.prompt_idx = -1
        # number of builtins + 2 local skills
        from nkd_agents import cli as m

        n_builtins = len(list((Path(m.__file__).parent / "skills").glob("*.md")))
        docs = [cli.cycle_prompt() for _ in range(n_builtins + 2)]
        texts = [d.text for d in docs]
        assert any("<skill aaa>" in t for t in texts)
        assert any("<skill zzz>" in t for t in texts)

    def test_wraps_around(self, cli: CLI, skills_dir):
        (skills_dir / "a.md").write_text("a")
        (skills_dir / "b.md").write_text("b")
        from nkd_agents import cli as m

        n_builtins = len(list((Path(m.__file__).parent / "skills").glob("*.md")))
        n = n_builtins + 2
        cli.prompt_idx = -1
        first = cli.cycle_prompt().text
        for _ in range(n - 1):
            cli.cycle_prompt()
        assert cli.cycle_prompt().text == first


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
