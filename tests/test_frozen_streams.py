"""
Regression: PyInstaller windowed exe (console=False) must not crash on print().

OSError: [Errno 22] Invalid argument was raised in checks.py when stdout/stderr
were invalid file descriptors set by PyInstaller for no-console builds.
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from ollama_tray._startup import redirect_frozen_streams


class _BrokenStream(io.RawIOBase):
    """Simulates PyInstaller windowed-exe invalid stdout/stderr."""

    def write(self, b):
        raise OSError(22, "Invalid argument")

    def flush(self):
        raise OSError(22, "Invalid argument")


@contextmanager
def _fake_frozen(stdout, stderr):
    orig_out, orig_err = sys.stdout, sys.stderr
    orig_frozen = getattr(sys, "frozen", None)
    try:
        sys.stdout = stdout
        sys.stderr = stderr
        sys.frozen = True
        yield
    finally:
        sys.stdout = orig_out
        sys.stderr = orig_err
        if orig_frozen is None:
            if hasattr(sys, "frozen"):
                del sys.frozen
        else:
            sys.frozen = orig_frozen


class TestRedirectFrozenStreams(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_broken_stream_replaced_with_log(self):
        with _fake_frozen(_BrokenStream(), _BrokenStream()):
            redirect_frozen_streams(log_base=self.tmp)
            # Should not raise
            print("stdout works", file=sys.stdout)
            print("stderr works", file=sys.stderr)

    def test_none_stream_replaced_with_log(self):
        with _fake_frozen(None, None):
            redirect_frozen_streams(log_base=self.tmp)
            print("stdout works", file=sys.stdout)
            print("stderr works", file=sys.stderr)

    def test_log_file_created(self):
        with _fake_frozen(_BrokenStream(), _BrokenStream()):
            redirect_frozen_streams(log_base=self.tmp)
        log_path = os.path.join(self.tmp, "ollama-tray", "ollama-tray.log")
        self.assertTrue(os.path.exists(log_path))

    def test_healthy_frozen_streams_untouched(self):
        good = io.StringIO()
        with _fake_frozen(good, good):
            redirect_frozen_streams(log_base=self.tmp)
            self.assertIs(sys.stdout, good, "Healthy streams must not be replaced")

    def test_non_frozen_skips_redirect(self):
        broken = _BrokenStream()
        orig_out = sys.stdout
        try:
            sys.stdout = broken
            # No sys.frozen set
            if hasattr(sys, "frozen"):
                del sys.frozen
            redirect_frozen_streams(log_base=self.tmp)
            self.assertIs(sys.stdout, broken, "Non-frozen must leave streams alone")
        finally:
            sys.stdout = orig_out


class TestFrozenStreamPreventsCrashInChecks(unittest.TestCase):
    """
    Verify the specific crash path: checks.py print() to sys.stderr.
    After redirect_frozen_streams() runs, print to stderr must not OSError.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_print_to_stderr_after_redirect_no_crash(self):
        with _fake_frozen(_BrokenStream(), _BrokenStream()):
            redirect_frozen_streams(log_base=self.tmp)
            try:
                # Exact pattern from checks.py line 540
                print("Warning: Ollama server not reachable.", file=sys.stderr)
            except OSError as e:
                self.fail(f"print() to stderr raised OSError after redirect: {e}")

    def test_print_to_stdout_after_redirect_no_crash(self):
        with _fake_frozen(_BrokenStream(), _BrokenStream()):
            redirect_frozen_streams(log_base=self.tmp)
            try:
                print("Ollama started (process mode).")
            except OSError as e:
                self.fail(f"print() to stdout raised OSError after redirect: {e}")


class TestNarrowCodecStreams(unittest.TestCase):
    """
    Regression: cp1252 stdout raises UnicodeEncodeError on non-ASCII chars.

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192' in
    windows.py cli_install() print. redirect_frozen_streams() must reconfigure
    narrow-codec streams to UTF-8 when frozen.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _make_cp1252_stream(self):
        buf = io.BytesIO()
        return io.TextIOWrapper(buf, encoding="cp1252")

    def test_unicode_arrow_no_crash_after_redirect(self):
        narrow = self._make_cp1252_stream()
        with _fake_frozen(narrow, narrow):
            redirect_frozen_streams(log_base=self.tmp)
            try:
                # Previously crashed: UnicodeEncodeError 'charmap' can't encode '→'
                print("Installed autostart: HKCU Run 'OllamaTray' -> C:\\dist\\ollama-tray.exe")
            except UnicodeEncodeError as e:
                self.fail(f"print() raised UnicodeEncodeError after redirect: {e}")

    def test_stream_reconfigured_to_utf8(self):
        narrow = self._make_cp1252_stream()
        with _fake_frozen(narrow, narrow):
            redirect_frozen_streams(log_base=self.tmp)
            enc = getattr(sys.stdout, "encoding", None)
            self.assertEqual(enc, "utf-8", f"stdout encoding should be utf-8, got {enc!r}")

    def test_non_ascii_chars_survive_reconfigure(self):
        narrow = self._make_cp1252_stream()
        with _fake_frozen(narrow, narrow):
            redirect_frozen_streams(log_base=self.tmp)
            # Must not raise
            print("em-dash: —  arrow: →  degree: °")


if __name__ == "__main__":
    unittest.main()
