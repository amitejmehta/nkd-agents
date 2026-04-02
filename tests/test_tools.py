"""Comprehensive tests for nkd_agents/tools.py"""

import asyncio
import base64
from unittest.mock import patch

import pytest

from nkd_agents.tools import bash, edit_file, glob, grep, read_file


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
        """Test reading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await read_file("/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_read_file_directory(self, tmp_path):
        """Test reading a directory returns error message."""
        dir_path = tmp_path / "testdir"
        dir_path.mkdir()

        with pytest.raises(IsADirectoryError):
            await read_file(str(dir_path))


class TestEditFile:
    @pytest.mark.asyncio
    async def test_create(self, tmp_path):
        file_path = tmp_path / "new_file.txt"
        result = await edit_file(
            str(file_path), mode="create", new_str="New file content"
        )
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "New file content"

    @pytest.mark.asyncio
    async def test_create_nested_dirs(self, tmp_path):
        file_path = tmp_path / "a" / "b" / "c" / "file.txt"
        result = await edit_file(str(file_path), mode="create", new_str="Nested file")
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "Nested file"

    @pytest.mark.asyncio
    async def test_create_already_exists(self, tmp_path):
        file_path = tmp_path / "existing.txt"
        file_path.write_text("original")
        with pytest.raises(ValueError, match="already exists"):
            await edit_file(str(file_path), mode="create", new_str="new content")
        assert file_path.read_text() == "original"

    @pytest.mark.asyncio
    async def test_append(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello")
        result = await edit_file(str(file_path), mode="append", new_str=" world")
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_append_file_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            await edit_file("/nonexistent/file.txt", mode="append", new_str="x")

    @pytest.mark.asyncio
    async def test_replace_str_single(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo bar foo bar")
        result = await edit_file(
            str(file_path), mode="replace", new_str="baz", old_str="foo", count=1
        )
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz bar foo bar"

    @pytest.mark.asyncio
    async def test_replace_str_all(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo bar foo bar foo")
        result = await edit_file(
            str(file_path), mode="replace", new_str="baz", old_str="foo", count=-1
        )
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz bar baz bar baz"

    @pytest.mark.asyncio
    async def test_replace_str_not_found(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("existing content")
        with pytest.raises(ValueError, match="not found in file content"):
            await edit_file(
                str(file_path), mode="replace", new_str="new", old_str="nonexistent"
            )
        assert file_path.read_text() == "existing content"

    @pytest.mark.asyncio
    async def test_replace_str_same_strings(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo")
        with pytest.raises(ValueError, match="must be different"):
            await edit_file(
                str(file_path), mode="replace", new_str="same", old_str="same"
            )

    @pytest.mark.asyncio
    async def test_replace_str_no_old_str(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo")
        with pytest.raises(ValueError, match="old_str is required"):
            await edit_file(str(file_path), mode="replace", new_str="bar")

    @pytest.mark.asyncio
    async def test_replace_str_file_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            await edit_file(
                "/nonexistent/file.txt",
                mode="replace",
                new_str="new",
                old_str="old",
            )

    @pytest.mark.asyncio
    async def test_multiple_sequential_edits(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("one two three")
        await edit_file(str(file_path), mode="replace", new_str="1", old_str="one")
        await edit_file(str(file_path), mode="replace", new_str="2", old_str="two")
        await edit_file(str(file_path), mode="replace", new_str="3", old_str="three")
        assert file_path.read_text() == "1 2 3"

    @pytest.mark.asyncio
    async def test_permission_error(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("original")
        with patch(
            "pathlib.Path.read_text", side_effect=PermissionError("Access denied")
        ):
            with pytest.raises(PermissionError, match="Access denied"):
                await edit_file(
                    str(file_path), mode="replace", new_str="new", old_str="old"
                )


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
            with pytest.raises(OSError, match="Exec failed"):
                await bash("echo test")

    @pytest.mark.asyncio
    async def test_bash_timeout(self):
        """Test bash timeout raises TimeoutError."""
        with pytest.raises(TimeoutError, match="timed out after 0.1 seconds"):
            await bash("sleep 10", timeout=0.1)

    @pytest.mark.asyncio
    async def test_bash_background_via_shell(self):
        """Background processes are run via & in the command string."""
        result = await bash("echo hello &")
        assert "EXIT CODE: 0" in result


class TestGlob:
    @pytest.mark.asyncio
    async def test_glob_matches(self, tmp_path):
        """Test glob finds matching files."""
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("x")
        (tmp_path / "c.txt").write_text("x")

        from nkd_agents.tools import cwd_ctx

        token = cwd_ctx.set(tmp_path)
        try:
            result = await glob("*.py")
            assert "a.py" in result
            assert "b.py" in result
            assert "c.txt" not in result
        finally:
            cwd_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_glob_recursive(self, tmp_path):
        """Test ** recursive glob."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("x")
        (tmp_path / "top.py").write_text("x")

        from nkd_agents.tools import cwd_ctx

        token = cwd_ctx.set(tmp_path)
        try:
            result = await glob("**/*.py")
            assert "top.py" in result
            assert "sub/deep.py" in result
        finally:
            cwd_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, tmp_path):
        """Test glob returns message when nothing matches."""
        result = await glob("*.xyz", path=str(tmp_path))
        assert result == "No matches found"

    @pytest.mark.asyncio
    async def test_glob_custom_path(self, tmp_path):
        """Test glob with explicit path argument."""
        sub = tmp_path / "dir"
        sub.mkdir()
        (sub / "f.md").write_text("x")

        result = await glob("*.md", path=str(sub))
        assert "f.md" in result

    @pytest.mark.asyncio
    async def test_glob_excludes_directories(self, tmp_path):
        """Test glob only returns files, not directories."""
        (tmp_path / "file.py").write_text("x")
        (tmp_path / "dir.py").mkdir()  # directory with .py name

        result = await glob("*.py", path=str(tmp_path))
        assert "file.py" in result
        lines = [line for line in result.splitlines() if line.strip()]
        assert len(lines) == 1


class TestGrep:
    @pytest.mark.asyncio
    async def test_grep_finds_pattern(self, tmp_path):
        """Test grep finds matching lines."""
        (tmp_path / "test.py").write_text(
            "def hello():\n    pass\n\ndef world():\n    pass\n"
        )

        result = await grep("def hello", path=str(tmp_path))
        assert "def hello" in result

    @pytest.mark.asyncio
    async def test_grep_with_include_filter(self, tmp_path):
        """Test grep --glob filter."""
        (tmp_path / "a.py").write_text("target_string\n")
        (tmp_path / "b.txt").write_text("target_string\n")

        result = await grep("target_string", include="*.py", path=str(tmp_path))
        assert "target_string" in result
        assert "b.txt" not in result

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, tmp_path):
        """Test grep returns message when nothing matches."""
        (tmp_path / "test.py").write_text("nothing here\n")

        result = await grep("nonexistent_xyz", path=str(tmp_path))
        assert "No matches found" in result

    @pytest.mark.asyncio
    async def test_grep_respects_cwd(self, tmp_path):
        """Test grep uses cwd_ctx when no path given."""
        from nkd_agents.tools import cwd_ctx

        (tmp_path / "file.py").write_text("unique_marker_abc\n")

        token = cwd_ctx.set(tmp_path)
        try:
            result = await grep("unique_marker_abc")
            assert "unique_marker_abc" in result
        finally:
            cwd_ctx.reset(token)


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
            result = await edit_file("new.txt", mode="create", new_str="created")
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
