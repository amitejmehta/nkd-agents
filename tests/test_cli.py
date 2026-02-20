import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import omit
from anthropic.types import TextBlock, ToolUseBlock

import nkd_agents.cli as cli_module
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


class TestCycleSkillPrompt:
    def test_xml_tags_match(self, cli: CLI):
        """Opening and closing tags wrap content with matching stem."""
        doc = cli.cycle_prompt()
        stem = doc.text.splitlines()[0][len("<prompt ") : -1]
        assert doc.text.startswith(f"<prompt {stem}>\n")
        assert doc.text.strip().endswith(f"</prompt {stem}>")

    def test_cursor_at_end(self, cli: CLI):
        doc = cli.cycle_prompt()
        assert doc.cursor_position == len(doc.text)

    def test_cycles_through_all_builtins(self, cli: CLI):
        nkd_dir = Path(cli_module.__file__).parent / "prompts"
        n = len(list(nkd_dir.glob("*.md")))
        docs = [cli.cycle_prompt() for _ in range(n)]
        assert len({d.text for d in docs}) == n

    def test_wraps_around(self, cli: CLI):
        nkd_dir = Path(cli_module.__file__).parent / "prompts"
        n = len(list(nkd_dir.glob("*.md")))
        first = cli.cycle_prompt().text
        for _ in range(n - 1):
            cli.cycle_prompt()
        assert cli.cycle_prompt().text == first

    def test_local_prompts_included(self, cli: CLI, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "aaa_local.md").write_text("local content")
        cli.prompt_idx = 0
        doc = cli.cycle_prompt()
        assert "<prompt aaa_local>" in doc.text
        assert "local content" in doc.text

    def test_alphabetical_order(self, cli: CLI, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "zzz_last.md").write_text("last")
        nkd_dir = Path(cli_module.__file__).parent / "prompts"
        n = len(list(nkd_dir.glob("*.md")))
        cli.prompt_idx = 0
        docs = [cli.cycle_prompt() for _ in range(n + 1)]
        assert "<prompt zzz_last>" in docs[-1].text

    def test_local_overrides_same_name(self, cli: CLI, tmp_path, monkeypatch):
        """Local prompt with same name as builtin: both appear."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prompts").mkdir()
        nkd_dir = Path(cli_module.__file__).parent / "prompts"
        builtin = next(nkd_dir.glob("*.md"))
        (tmp_path / "prompts" / builtin.name).write_text("local override")
        cli.prompt_idx = 0
        nkd_count = len(list(nkd_dir.glob("*.md")))
        docs = [cli.cycle_prompt() for _ in range(nkd_count + 1)]
        # same stem appears twice — one with local content
        matches = [d for d in docs if f"<prompt {builtin.stem}>" in d.text]
        assert len(matches) == 2
        assert any("local override" in d.text for d in matches)


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
