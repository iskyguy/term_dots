import contextlib
import hashlib
import io
import json
import os
import pty
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import packages


class FastfetchPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home with spaces"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.binary = self.home / ".local/bin/fastfetch"
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def release(self, architecture="amd64", kind=tarfile.REGTYPE):
        payload = b"#!/bin/sh\nprintf 'fastfetch test\\n'\n"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            member = tarfile.TarInfo(
                f"fastfetch-linux-{architecture}-polyfilled/usr/bin/fastfetch")
            member.type = kind
            member.size = len(payload) if kind == tarfile.REGTYPE else 0
            member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
            archive.addfile(member, io.BytesIO(payload) if member.size else None)
            # Only the expected binary is copied; other members must never be extracted.
            extra = tarfile.TarInfo("../../unexpected-file")
            archive.addfile(extra, io.BytesIO())
        data = buffer.getvalue()
        self.pin(data, architecture)
        return data, payload

    def pin(self, data, architecture="amd64"):
        (self.repo / "versions.json").write_text(json.dumps({"fastfetch": {
            "version": "2.70.0", "sha256": {architecture: hashlib.sha256(data).hexdigest()}
        }}))

    def install(self, data, architecture="x86_64", dry_run=False):
        with patch("packages.executable", return_value=None), \
             patch("packages.platform.machine", return_value=architecture), \
             patch("packages.fetch", side_effect=lambda _url, path: path.write_bytes(data)) as fetch:
            packages.install_fastfetch(self.home, self.repo, dry_run)
        return fetch

    def test_verified_release_for_supported_architectures(self):
        for machine, architecture in (("x86_64", "amd64"), ("amd64", "amd64"),
                                      ("aarch64", "aarch64"), ("arm64", "aarch64")):
            with self.subTest(machine=machine):
                data, payload = self.release(architecture)
                fetch = self.install(data, machine)
                self.assertEqual(self.binary.read_bytes(), payload)
                self.assertEqual(self.binary.stat().st_mode & 0o777, 0o755)
                self.assertIn(f"/2.70.0/fastfetch-linux-{architecture}-polyfilled.tar.gz",
                              fetch.call_args.args[0])
                self.assertCountEqual(self.root.iterdir(), [self.repo, self.home])

    def test_existing_fastfetch_is_reused_without_download(self):
        with patch("packages.executable", return_value="/usr/bin/fastfetch"), \
             patch("packages.fetch") as fetch:
            packages.install_fastfetch(self.home, self.repo, False)
        fetch.assert_not_called()
        self.assertFalse(self.home.exists())

    def test_dry_run_makes_no_downloads_or_writes(self):
        data, _ = self.release()
        fetch = self.install(data, dry_run=True)
        fetch.assert_not_called()
        self.assertFalse(self.home.exists())

    def test_bad_checksum_preserves_existing_binary(self):
        data, _ = self.release()
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"previous installation")
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.install(data + b"tampered")
        self.assertEqual(self.binary.read_bytes(), b"previous installation")
        self.assertEqual(list(self.binary.parent.iterdir()), [self.binary])

    def test_invalid_archive_and_nonregular_binary_are_rejected(self):
        for case in ("corrupt", "missing", "symlink"):
            with self.subTest(case=case):
                if case == "corrupt":
                    data = b"not a tar file"
                    self.pin(data)
                elif case == "missing":
                    data, _ = self.release("aarch64")
                    self.pin(data)
                else:
                    data, _ = self.release(kind=tarfile.SYMTYPE)
                with self.assertRaisesRegex(RuntimeError, "archive|regular file"):
                    self.install(data)
                self.assertFalse(self.binary.exists())

    def test_failed_replace_preserves_binary_and_cleans_staging_file(self):
        data, _ = self.release()
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"previous installation")
        with patch("packages.os.replace", side_effect=OSError("test failure")), \
             self.assertRaises(OSError):
            self.install(data)
        self.assertEqual(self.binary.read_bytes(), b"previous installation")
        self.assertEqual(list(self.binary.parent.iterdir()), [self.binary])

    def test_invalid_pin_is_rejected_before_download(self):
        for version, checksum in (("../../bad", "0" * 64), ("2.70.0", "bad")):
            with self.subTest(version=version, checksum=checksum):
                (self.repo / "versions.json").write_text(json.dumps({"fastfetch": {
                    "version": version, "sha256": {"amd64": checksum}
                }}))
                with self.assertRaisesRegex(RuntimeError, "versions.json"):
                    self.install(b"")
                self.assertFalse(self.home.exists())

    def test_unsupported_architecture_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "x86_64 or aarch64"):
            self.install(b"", architecture="riscv64")
        self.assertFalse(self.home.exists())

    @patch("packages.os.geteuid", return_value=1000)
    @patch("packages.platform.system", return_value="Linux")
    def test_homebrew_installs_missing_cli_tools(self, _system, _uid):
        def executable(name, _home):
            return None if name in ("starship", "uv", "fastfetch") else "/bin/" + name

        with patch("packages.executable", side_effect=executable), \
             patch("packages.run") as run, patch("packages.fetch") as fetch:
            packages.install_tools("headless", self.home, self.repo)
        run.assert_called_once_with(["/bin/brew", "install", "starship", "uv", "fastfetch"], False)
        fetch.assert_not_called()

    @patch("packages.os.geteuid", return_value=1000)
    @patch("packages.platform.system", return_value="Linux")
    def test_without_homebrew_uses_release_fallback(self, _system, _uid):
        def executable(name, _home):
            return None if name in ("brew", "fastfetch") else "/bin/" + name

        with patch("packages.executable", side_effect=executable), \
             patch("packages.install_fastfetch") as fastfetch, patch("packages.run") as run:
            packages.install_tools("headless", self.home, self.repo)
        fastfetch.assert_called_once_with(self.home, self.repo, False)
        run.assert_not_called()


class FastfetchConfigTests(unittest.TestCase):
    def test_shared_config_is_ascii_and_uses_no_network_or_desktop_modules(self):
        text = (REPO / "common/fastfetch/config.jsonc").read_text()
        config = json.loads(text)
        self.assertTrue(text.isascii())
        self.assertEqual(config["logo"]["type"], "builtin")
        self.assertEqual(config["modules"], ["title", "separator", "os", "host", "kernel",
                                             "uptime", "packages", "shell", "terminal", "cpu",
                                             "memory", "disk", "break", "colors"])

    @unittest.skipUnless(shutil.which("fastfetch"), "Fastfetch executable unavailable.")
    def test_fastfetch_accepts_shared_config(self):
        result = subprocess.run(
            [shutil.which("fastfetch"), "--config", str(REPO / "common/fastfetch/config.jsonc"),
             "--format", "json"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(module["type"] == "OS" for module in json.loads(result.stdout)))


@unittest.skipUnless(shutil.which("fish"), "Fish executable unavailable.")
class FastfetchStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home with spaces"
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        self.log = self.home / "fastfetch.log"
        self.environment = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                                XDG_CONFIG_HOME=str(self.home / ".config"),
                                XDG_DATA_HOME=str(self.home / ".local/share"),
                                XDG_STATE_HOME=str(self.home / ".local/state"),
                                XDG_CACHE_HOME=str(self.home / ".cache"),
                                TERM="xterm-256color", FASTFETCH_TEST_LOG=str(self.log))
        for name, body in (("starship", "exit 0\n"),
                           ("fastfetch", 'printf "ran\\n" >> "$FASTFETCH_TEST_LOG"\n')):
            tool = self.bin / name
            tool.write_text("#!/bin/sh\n" + body)
            tool.chmod(0o755)

    def run_fish(self, interactive=True, tty_input=True, tty_output=True):
        argv = [shutil.which("fish"), "--no-config"]
        if interactive:
            argv.append("--interactive")
        # Keep host Homebrew paths out of this isolated startup test.
        script = ("function fish_add_path; end; source "
                  + "'" + str(REPO / "common/fish/init.fish").replace("'", "\\'")
                  + "'; printf 'READY\\n'")
        argv.extend(["--command", script])
        master, slave = pty.openpty()
        try:
            result = subprocess.run(argv, env=self.environment,
                                    stdin=slave if tty_input else subprocess.DEVNULL,
                                    stdout=slave if tty_output else subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, timeout=10)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        if not tty_output:
            self.assertEqual(result.stdout, "READY\n")

    def test_interactive_terminal_stays_quiet(self):
        self.run_fish()
        self.assertFalse(self.log.exists())

    def test_interactive_ssh_terminal_stays_quiet(self):
        self.environment["SSH_CONNECTION"] = "192.0.2.1 1234 192.0.2.2 22"
        self.run_fish()
        self.assertFalse(self.log.exists())

    def test_noninteractive_shell_stays_quiet(self):
        self.run_fish(interactive=False)
        self.assertFalse(self.log.exists())

    def test_redirected_output_stays_quiet(self):
        self.run_fish(tty_output=False)
        self.assertFalse(self.log.exists())

    def test_redirected_input_stays_quiet(self):
        self.run_fish(tty_input=False)
        self.assertFalse(self.log.exists())

    def test_dumb_terminal_stays_quiet(self):
        self.environment["TERM"] = "dumb"
        self.run_fish()
        self.assertFalse(self.log.exists())

    def test_missing_fastfetch_stays_quiet(self):
        (self.bin / "fastfetch").unlink()
        self.run_fish()
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
