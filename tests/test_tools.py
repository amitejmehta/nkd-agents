"""Comprehensive tests for nkd_agents/tools.py"""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nkd_agents.tools import anthropic_client_ctx, bash, edit_file, read_file, subtask


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_file_text(self, tmp_path):
        """Test reading a plain text file."""
        file_path = tmp_path / "test.txt"
        content = "Hello, World!"
        file_path.write_text(content)

        result = await read_file(str(file_path))
        # Text files return list with text block
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["text"] == content

    @pytest.mark.asyncio
    async def test_read_file_image_jpg(self, tmp_path):
        """Test reading a JPG image returns base64 encoded content."""
        file_path = tmp_path / "test.jpg"
        image_data = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # Minimal JPEG header
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))

        # Should return list with dict containing base64 encoded data
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "image"
        assert result[0]["source"]["type"] == "base64"
        assert result[0]["source"]["media_type"] == "image/jpeg"
        assert result[0]["source"]["data"] == base64.b64encode(image_data).decode()

    @pytest.mark.asyncio
    async def test_read_file_image_png(self, tmp_path):
        """Test reading a PNG image returns base64 encoded content."""
        file_path = tmp_path / "test.png"
        image_data = b"\x89PNG\r\n\x1a\n"  # PNG signature
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))

        assert isinstance(result, list)
        assert result[0]["source"]["media_type"] == "image/png"
        assert result[0]["source"]["data"] == base64.b64encode(image_data).decode()

    @pytest.mark.asyncio
    async def test_read_file_image_gif(self, tmp_path):
        """Test reading a GIF image returns base64 encoded content."""
        file_path = tmp_path / "test.gif"
        image_data = b"GIF89a"  # GIF signature
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))

        assert isinstance(result, list)
        assert result[0]["source"]["media_type"] == "image/gif"
        assert result[0]["source"]["data"] == base64.b64encode(image_data).decode()

    @pytest.mark.asyncio
    async def test_read_file_image_webp(self, tmp_path):
        """Test reading a WEBP image returns base64 encoded content."""
        file_path = tmp_path / "test.webp"
        image_data = b"RIFF\x00\x00\x00\x00WEBP"  # WEBP signature
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))

        assert isinstance(result, list)
        assert result[0]["source"]["media_type"] == "image/webp"
        assert result[0]["source"]["data"] == base64.b64encode(image_data).decode()

    @pytest.mark.asyncio
    async def test_read_file_pdf(self, tmp_path):
        """Test reading a PDF returns base64 encoded content."""
        file_path = tmp_path / "test.pdf"
        pdf_data = b"%PDF-1.4"  # PDF signature
        file_path.write_bytes(pdf_data)

        result = await read_file(str(file_path))

        assert isinstance(result, list)
        assert result[0]["type"] == "document"
        assert result[0]["source"]["type"] == "base64"
        assert result[0]["source"]["media_type"] == "application/pdf"
        assert result[0]["source"]["data"] == base64.b64encode(pdf_data).decode()

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        """Test reading a non-existent file returns error message."""
        result = await read_file("/nonexistent/file.txt")

        assert isinstance(result, str)
        assert "Error reading file" in result
        assert "/nonexistent/file.txt" in result

    @pytest.mark.asyncio
    async def test_read_file_directory(self, tmp_path):
        """Test reading a directory returns error message."""
        dir_path = tmp_path / "testdir"
        dir_path.mkdir()

        result = await read_file(str(dir_path))

        assert isinstance(result, str)
        assert "Error reading file" in result


class TestEditFile:
    @pytest.mark.asyncio
    async def test_edit_file_create_new(self, tmp_path):
        """Test creating a new file with old_str=''."""
        file_path = tmp_path / "new_file.txt"
        content = "New file content"

        result = await edit_file(str(file_path), "create_file", content)

        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == content

    @pytest.mark.asyncio
    async def test_edit_file_create_nested_dirs(self, tmp_path):
        """Test creating a file in nested directories that don't exist."""
        file_path = tmp_path / "a" / "b" / "c" / "file.txt"
        content = "Nested file"

        result = await edit_file(str(file_path), "create_file", content)

        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == content
        assert file_path.parent.exists()

    @pytest.mark.asyncio
    async def test_edit_file_single_replacement(self, tmp_path):
        """Test replacing single occurrence (default count=1)."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo bar foo bar")

        result = await edit_file(str(file_path), "foo", "baz", count=1)

        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz bar foo bar"

    @pytest.mark.asyncio
    async def test_edit_file_multiple_replacements(self, tmp_path):
        """Test replacing all occurrences with count=-1."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo bar foo bar foo")

        result = await edit_file(str(file_path), "foo", "baz", count=-1)

        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz bar baz bar baz"

    @pytest.mark.asyncio
    async def test_edit_file_old_str_not_found(self, tmp_path):
        """Test error when old_str is not in file content."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("existing content")

        result = await edit_file(str(file_path), "nonexistent", "new")

        assert result == "Error: old_str not found in file content"
        assert file_path.read_text() == "existing content"  # Unchanged

    @pytest.mark.asyncio
    async def test_edit_file_same_strings(self):
        """Test error when old_str equals new_str."""
        result = await edit_file("/any/path", "same", "same")

        assert result == "Error: old_str and new_str must be different"

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self):
        """Test error when file doesn't exist and old_str is not empty."""
        result = await edit_file("/nonexistent/file.txt", "old", "new")

        assert result == "Error: File '/nonexistent/file.txt' not found"

    @pytest.mark.asyncio
    async def test_edit_file_multiple_sequential_edits(self, tmp_path):
        """Test multiple edits to same file work correctly."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("one two three")

        result1 = await edit_file(str(file_path), "one", "1")
        result2 = await edit_file(str(file_path), "two", "2")
        result3 = await edit_file(str(file_path), "three", "3")

        assert "Success" in result1
        assert "Success" in result2
        assert "Success" in result3
        assert file_path.read_text() == "1 2 3"

    @pytest.mark.asyncio
    async def test_edit_file_generic_exception(self, tmp_path):
        """Test that unexpected exceptions are caught and returned as error messages."""
        # Create a file and then make it unreadable by patching read_text
        file_path = tmp_path / "test.txt"
        file_path.write_text("original")

        with patch(
            "pathlib.Path.read_text", side_effect=PermissionError("Access denied")
        ):
            result = await edit_file(str(file_path), "old", "new")

            assert "Error editing file" in result
            assert "Access denied" in result


class TestBash:
    @pytest.mark.asyncio
    async def test_bash_success(self):
        """Test successful command execution with stdout."""
        result = await bash("echo 'Hello'")

        assert "STDOUT:" in result
        assert "Hello" in result
        assert "STDERR:" in result
        assert "EXIT CODE: 0" in result

    @pytest.mark.asyncio
    async def test_bash_failure(self):
        """Test failed command with non-zero exit code."""
        result = await bash("exit 42")

        assert "EXIT CODE: 42" in result

    @pytest.mark.asyncio
    async def test_bash_stderr(self):
        """Test command that writes to stderr."""
        result = await bash("echo 'error message' >&2")

        assert "STDERR:" in result
        assert "error message" in result
        assert "EXIT CODE: 0" in result

    @pytest.mark.asyncio
    async def test_bash_both_stdout_stderr(self):
        """Test command with both stdout and stderr output."""
        result = await bash("echo 'out'; echo 'err' >&2")

        assert "STDOUT:" in result
        assert "out" in result
        assert "STDERR:" in result
        assert "err" in result

    @pytest.mark.asyncio
    async def test_bash_command_not_found(self):
        """Test invalid command returns error in stderr."""
        result = await bash("nonexistentcommand12345")

        assert "STDERR:" in result
        assert "EXIT CODE:" in result
        # Should have non-zero exit code
        assert "EXIT CODE: 0" not in result

    @pytest.mark.asyncio
    async def test_bash_multiline_output(self):
        """Test command with multiline output."""
        result = await bash("printf 'line1\\nline2\\nline3'")

        assert "STDOUT:" in result
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_bash_cancellation(self):
        """Test that bash handles cancellation properly."""

        async def run_and_cancel():
            task = asyncio.create_task(bash("sleep 10"))
            await asyncio.sleep(0.1)  # Let it start
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return "cancelled"
            return "not cancelled"

        result = await run_and_cancel()
        assert result == "cancelled"

    @pytest.mark.asyncio
    async def test_bash_generic_exception(self):
        """Test bash handles unexpected exceptions."""
        # Mock create_subprocess_exec to raise an unexpected exception
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("Exec failed")
        ):
            result = await bash("echo test")

            assert "Error executing bash command:" in result
            assert "Exec failed" in result

    @pytest.mark.asyncio
    async def test_bash_timeout(self):
        """Test bash timeout error handling."""
        result = await bash("sleep 10", timeout=0.1)

        assert "Error: Command timed out" in result
        assert "0.1 seconds" in result


class TestSubtask:
    @pytest.mark.asyncio
    async def test_subtask_no_client(self):
        """Test subtask fails when client not set."""
        # Context vars have function scope by default, we need to test the actual subtask call
        # When client_ctx.get() is called without being set, it raises LookupError
        # We need to ensure no client is set in the context
        with patch("nkd_agents.tools.anthropic_client_ctx") as mock_ctx:
            mock_ctx.get.side_effect = LookupError("No client set")

            with pytest.raises(LookupError):
                await subtask("test", "task", model="haiku")

    @pytest.mark.asyncio
    async def test_subtask_with_client(self):
        """Test subtask executes when client is set."""
        mock_client = MagicMock()

        # Mock the llm function to return a simple response
        with patch("nkd_agents.tools.llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Task completed successfully"

            token = anthropic_client_ctx.set(mock_client)
            try:
                result = await subtask(
                    prompt="Test prompt", task_label="test task", model="haiku"
                )

                assert "subtask 'test task' complete" in result
                assert "Task completed successfully" in result

                # Verify llm was called with correct parameters
                mock_llm.assert_called_once()
                call_args = mock_llm.call_args
                assert call_args.kwargs["model"] == "claude-haiku-4-6"
                assert call_args.kwargs["max_tokens"] == 8192
            finally:
                anthropic_client_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_subtask_model_parameter(self):
        """Test subtask uses correct model based on parameter."""
        mock_client = MagicMock()

        with patch("nkd_agents.tools.llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Done"

            token = anthropic_client_ctx.set(mock_client)
            try:
                # Test sonnet
                await subtask("prompt", "task", model="sonnet")
                assert mock_llm.call_args.kwargs["model"] == "claude-sonnet-4-6"

                # Test haiku
                await subtask("prompt", "task", model="haiku")
                assert mock_llm.call_args.kwargs["model"] == "claude-haiku-4-6"
            finally:
                anthropic_client_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_subtask_exception_handling(self):
        """Test subtask handles exceptions from llm and returns error message."""
        mock_client = MagicMock()

        with patch("nkd_agents.tools.llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM failed")

            token = anthropic_client_ctx.set(mock_client)
            try:
                result = await subtask("prompt", "my_task", model="haiku")

                assert "Error executing subtask 'my_task':" in result
                assert "LLM failed" in result
            finally:
                anthropic_client_ctx.reset(token)


class TestCwdContext:
    """Test cwd_ctx with relative paths in tools."""

    @pytest.mark.asyncio
    async def test_read_file_relative_path(self, tmp_path):
        """read_file resolves relative paths against cwd_ctx."""
        from nkd_agents.tools import cwd_ctx, read_file

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("content")

        token = cwd_ctx.set(subdir)
        try:
            result = await read_file(path="test.txt")
            assert result == [{"type": "text", "text": "content"}]
        finally:
            cwd_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_edit_file_relative_path(self, tmp_path):
        """edit_file resolves relative paths against cwd_ctx."""
        from nkd_agents.tools import cwd_ctx, edit_file

        subdir = tmp_path / "subdir"
        subdir.mkdir()

        token = cwd_ctx.set(subdir)
        try:
            result = await edit_file("new.txt", "create_file", "created")
            assert "Success" in result
            assert (subdir / "new.txt").read_text() == "created"
        finally:
            cwd_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_bash_cwd_context(self, tmp_path):
        """bash executes in cwd_ctx directory."""
        from nkd_agents.tools import bash, cwd_ctx

        subdir = tmp_path / "workdir"
        subdir.mkdir()

        token = cwd_ctx.set(subdir)
        try:
            result = await bash("pwd")
            assert str(subdir) in result
        finally:
            cwd_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_cwd_isolation(self, tmp_path):
        """cwd_ctx changes don't affect other contexts."""
        from nkd_agents.tools import cwd_ctx, read_file

        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "file.txt").write_text("dir1_content")
        (dir2 / "file.txt").write_text("dir2_content")

        token1 = cwd_ctx.set(dir1)
        result1 = await read_file(path="file.txt")
        cwd_ctx.reset(token1)

        token2 = cwd_ctx.set(dir2)
        result2 = await read_file(path="file.txt")
        cwd_ctx.reset(token2)

        assert result1 == [{"type": "text", "text": "dir1_content"}]
        assert result2 == [{"type": "text", "text": "dir2_content"}]
