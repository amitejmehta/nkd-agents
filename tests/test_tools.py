"""Comprehensive tests for nkd_agents/tools.py"""

import asyncio
from unittest.mock import patch

import pytest

from nkd_agents.tools import (
    FileContent,
    bash,
    edit_file,
    glob,
    grep,
    read_file,
    write_file,
)


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_file_text(self, tmp_path):
        """Text file returns FileContent with raw bytes and ext."""
        file_path = tmp_path / "test.txt"
        content = "Hello, World!"
        file_path.write_text(content)

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == "txt"
        assert result.data == content.encode("utf-8")

    @pytest.mark.asyncio
    async def test_read_file_image_jpg(self, tmp_path):
        """JPG returns FileContent with ext='jpg'."""
        file_path = tmp_path / "test.jpg"
        image_data = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == "jpg"
        assert result.data == image_data

    @pytest.mark.asyncio
    async def test_read_file_image_png(self, tmp_path):
        file_path = tmp_path / "test.png"
        image_data = b"\x89PNG\r\n\x1a\n"
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == "png"
        assert result.data == image_data

    @pytest.mark.asyncio
    async def test_read_file_image_gif(self, tmp_path):
        file_path = tmp_path / "test.gif"
        image_data = b"GIF89a"
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == "gif"
        assert result.data == image_data

    @pytest.mark.asyncio
    async def test_read_file_image_webp(self, tmp_path):
        file_path = tmp_path / "test.webp"
        image_data = b"RIFF\x00\x00\x00\x00WEBP"
        file_path.write_bytes(image_data)

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == "webp"
        assert result.data == image_data

    @pytest.mark.asyncio
    async def test_read_file_pdf(self, tmp_path):
        file_path = tmp_path / "test.pdf"
        pdf_data = b"%PDF-1.4"
        file_path.write_bytes(pdf_data)

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == "pdf"
        assert result.data == pdf_data

    @pytest.mark.asyncio
    async def test_read_file_no_extension(self, tmp_path):
        file_path = tmp_path / "Makefile"
        file_path.write_text("all:")

        result = await read_file(str(file_path))
        assert isinstance(result, FileContent)
        assert result.ext == ""

    @pytest.mark.asyncio
    async def test_read_file_too_large(self, tmp_path):
        """Non-binary files over 50 000 bytes return an error string."""
        file_path = tmp_path / "big.txt"
        file_path.write_bytes(b"x" * 50001)

        result = await read_file(str(file_path))
        assert isinstance(result, str)
        assert "too large" in result

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            await read_file("/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_read_file_directory(self, tmp_path):
        dir_path = tmp_path / "testdir"
        dir_path.mkdir()

        with pytest.raises(IsADirectoryError):
            await read_file(str(dir_path))


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_create(self, tmp_path):
        file_path = tmp_path / "new_file.txt"
        result = await write_file(str(file_path), content="New file content")
        assert result == f"Success: Created {file_path}"
        assert file_path.read_text() == "New file content"

    @pytest.mark.asyncio
    async def test_create_nested_dirs(self, tmp_path):
        file_path = tmp_path / "a" / "b" / "c" / "file.txt"
        result = await write_file(str(file_path), content="Nested file")
        assert result == f"Success: Created {file_path}"
        assert file_path.read_text() == "Nested file"

    @pytest.mark.asyncio
    async def test_create_already_exists(self, tmp_path):
        file_path = tmp_path / "existing.txt"
        file_path.write_text("original")
        with pytest.raises(ValueError, match="already exists"):
            await write_file(str(file_path), content="new content")
        assert file_path.read_text() == "original"


class TestEditFile:
    @pytest.mark.asyncio
    async def test_replace_first_occurrence(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo bar foo bar")
        result = await edit_file(str(file_path), old_str="foo", new_str="baz")
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz bar foo bar"

    @pytest.mark.asyncio
    async def test_replace_all(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo bar foo bar foo")
        result = await edit_file(str(file_path), old_str="foo", new_str="baz", count=-1)
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz bar baz bar baz"

    @pytest.mark.asyncio
    async def test_replace_count_n(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo foo foo")
        result = await edit_file(str(file_path), old_str="foo", new_str="baz", count=2)
        assert result == f"Success: Updated {file_path}"
        assert file_path.read_text() == "baz baz foo"

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            await edit_file("/nonexistent/file.txt", old_str="old", new_str="new")

    @pytest.mark.asyncio
    async def test_old_str_not_found(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("existing content")
        with pytest.raises(ValueError, match="not found in file content"):
            await edit_file(str(file_path), old_str="nonexistent", new_str="new")
        assert file_path.read_text() == "existing content"

    @pytest.mark.asyncio
    async def test_same_strings(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("same")
        with pytest.raises(ValueError, match="must be different"):
            await edit_file(str(file_path), old_str="same", new_str="same")

    @pytest.mark.asyncio
    async def test_count_zero_raises(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo")
        with pytest.raises(ValueError, match="positive integer or -1"):
            await edit_file(str(file_path), old_str="foo", new_str="bar", count=0)

    @pytest.mark.asyncio
    async def test_count_minus_two_raises(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("foo")
        with pytest.raises(ValueError, match="positive integer or -1"):
            await edit_file(str(file_path), old_str="foo", new_str="bar", count=-2)

    @pytest.mark.asyncio
    async def test_multiple_sequential_edits(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("one two three")
        await edit_file(str(file_path), old_str="one", new_str="1")
        await edit_file(str(file_path), old_str="two", new_str="2")
        await edit_file(str(file_path), old_str="three", new_str="3")
        assert file_path.read_text() == "1 2 3"

    @pytest.mark.asyncio
    async def test_permission_error(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("original")
        with patch(
            "pathlib.Path.read_text", side_effect=PermissionError("Access denied")
        ):
            with pytest.raises(PermissionError, match="Access denied"):
                await edit_file(str(file_path), old_str="old", new_str="new")


class TestEditFileCheckOrder:
    """
    The check order in edit_file is a load-bearing invariant.

    Wrong ordering causes LLM agentic loops to spiral: if old_str == new_str is checked
    before existence, an LLM probing with identical strings gets "must be different" even
    when the string isn't in the file — a false signal of existence. The LLM then can't
    reconcile that with the subsequent "not found" error and loops indefinitely.

    Correct order:
        1. file not found
        2. invalid count
        3. old_str not in file
        4. old_str == new_str   ← only reachable when string IS present
    """

    @pytest.mark.asyncio
    async def test_file_not_found_beats_invalid_count(self, tmp_path):
        """File not found is reported before count is validated."""
        with pytest.raises(ValueError, match="not found"):
            await edit_file("/nonexistent/file.txt", old_str="x", new_str="y", count=0)

    @pytest.mark.asyncio
    async def test_invalid_count_beats_old_str_not_found(self, tmp_path):
        """Invalid count is reported before old_str existence is checked."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello")
        with pytest.raises(ValueError, match="positive integer or -1"):
            await edit_file(str(file_path), old_str="nothere", new_str="y", count=0)

    @pytest.mark.asyncio
    async def test_old_str_not_found_beats_same_strings(self, tmp_path):
        """
        old_str not in file is reported before old_str == new_str is checked.

        This is the critical invariant. If reversed, an LLM passing old_str == new_str
        gets "must be different" even when the string isn't present — a false signal
        of existence that causes the LLM to spiral trying to fix its replacement.
        """
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world")
        with pytest.raises(ValueError, match="not found in file content"):
            await edit_file(str(file_path), old_str="nothere", new_str="nothere")


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

    @pytest.mark.asyncio
    async def test_glob_excludes_hidden_by_default(self, tmp_path):
        """Test glob ignores hidden files and dirs by default."""
        (tmp_path / "visible.py").write_text("x")
        (tmp_path / ".hidden.py").write_text("x")
        hidden_dir = tmp_path / ".venv"
        hidden_dir.mkdir()
        (hidden_dir / "pkg.py").write_text("x")

        result = await glob("**/*.py", path=str(tmp_path))
        assert "visible.py" in result
        assert ".hidden.py" not in result
        assert ".venv/pkg.py" not in result

    @pytest.mark.asyncio
    async def test_glob_include_hidden(self, tmp_path):
        """Test glob includes hidden files when include_hidden=True."""
        (tmp_path / "visible.py").write_text("x")
        (tmp_path / ".hidden.py").write_text("x")
        hidden_dir = tmp_path / ".venv"
        hidden_dir.mkdir()
        (hidden_dir / "pkg.py").write_text("x")

        result = await glob("**/*.py", path=str(tmp_path), include_hidden=True)
        assert "visible.py" in result
        assert ".hidden.py" in result
        assert ".venv/pkg.py" in result


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

    @pytest.mark.asyncio
    async def test_grep_excludes_hidden_by_default(self, tmp_path):
        """Test grep ignores hidden files and dirs by default."""
        (tmp_path / "visible.py").write_text("secret_token\n")
        (tmp_path / ".hidden.py").write_text("secret_token\n")
        hidden_dir = tmp_path / ".venv"
        hidden_dir.mkdir()
        (hidden_dir / "pkg.py").write_text("secret_token\n")

        result = await grep("secret_token", path=str(tmp_path))
        assert "visible.py" in result
        assert ".hidden.py" not in result
        assert ".venv" not in result

    @pytest.mark.asyncio
    async def test_grep_total_output_capped_at_200_lines(self, tmp_path):
        """Total output is capped at 200 lines, even across many files / many matches."""
        # 10 files with 100 matches each = 1000 hits; far more than 200 lines.
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text("hit\n" * 100)

        result = await grep("hit", path=str(tmp_path), context=0)
        assert len(result.splitlines()) <= 200

    @pytest.mark.asyncio
    async def test_grep_include_hidden(self, tmp_path):
        """Test grep searches hidden files when include_hidden=True."""
        (tmp_path / "visible.py").write_text("secret_token\n")
        hidden_dir = tmp_path / ".venv"
        hidden_dir.mkdir()
        (hidden_dir / "pkg.py").write_text("secret_token\n")

        result = await grep("secret_token", path=str(tmp_path), include_hidden=True)
        assert "visible.py" in result
        assert ".venv" in result


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
            assert isinstance(result, FileContent)
            assert result.data == b"content"
            assert result.ext == "txt"
        finally:
            cwd_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_edit_file_relative_path(self, tmp_path):
        """write_file resolves relative paths against cwd_ctx."""
        from nkd_agents.tools import cwd_ctx, write_file

        subdir = tmp_path / "subdir"
        subdir.mkdir()

        token = cwd_ctx.set(subdir)
        try:
            result = await write_file("new.txt", content="created")
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

        assert isinstance(result1, FileContent) and result1.data == b"dir1_content"
        assert isinstance(result2, FileContent) and result2.data == b"dir2_content"
