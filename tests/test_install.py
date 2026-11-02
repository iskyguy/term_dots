import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import install
import packages


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home with spaces"
        self.config = self.home / ".config"
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def write(self, relative, text):
        target = self.home / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def apply(self, profile):
        install.Config(self.home).install(profile, "/usr/bin/fish",
                                          str(self.home / ".local/bin/ghostty"))

    def test_headless_and_idempotence(self):
        self.apply("headless")
        target = self.config / "fish/config.fish"
        before = target.read_bytes()
        self.apply("headless")
        self.assertEqual(before, target.read_bytes())
        self.assertEqual(target.read_text().count(install.BEGIN), 1)
        prompt = self.config / "fish/terminal-dotfiles/starship.toml"
        self.assertEqual(prompt.resolve(), REPO / "profiles/headless/starship.toml")
        fastfetch = self.config / "fastfetch/config.jsonc"
        self.assertEqual(fastfetch.resolve(), REPO / "common/fastfetch/config.jsonc")
        self.assertFalse((self.config / "ghostty").exists())
        self.assertFalse((self.home / ".local/share/applications").exists())
        self.assertFalse(list((self.home / ".local/state").rglob("backups/*")))

    def test_switch_and_restore_original_files(self):
        fish = self.write(".config/fish/config.fish", "set -gx KEEP_ME yes")
        ghostty = self.write(".config/ghostty/config", "font-size = 14\n")
        modern = self.write(".config/ghostty/config.ghostty", "theme = dark:dark,light:light\n")
        completion = self.write(".config/fish/completions/uv.fish", "# original completion\n")
        fastfetch = self.write(".config/fastfetch/config.jsonc", '{"modules": ["os"]}\n')
        originals = {path: path.read_bytes() for path in (fish, ghostty, modern, completion, fastfetch)}
        fish.chmod(0o600)
        fastfetch.chmod(0o600)
        self.apply("desktop")
        self.assertTrue(fish.read_bytes().startswith(originals[fish]))
        self.assertIn("clipboard-write = allow", ghostty.read_text())
        self.assertEqual(modern.read_bytes(), originals[modern])
        self.apply("headless")
        self.assertEqual(fastfetch.resolve(), REPO / "common/fastfetch/config.jsonc")
        self.assertEqual(ghostty.read_bytes(), originals[ghostty])
        self.assertFalse((self.home / ".local/share/applications/terminal-dotfiles-ghostty.desktop").exists())
        self.assertTrue(install.Config(self.home).uninstall())
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        self.assertEqual(fish.stat().st_mode & 0o777, 0o600)
        self.assertEqual(fastfetch.stat().st_mode & 0o777, 0o600)

    def test_fastfetch_original_symlink_restores_without_editing_target(self):
        original = self.write("my-fastfetch.jsonc", '{"modules": ["kernel"]}\n')
        fastfetch = self.config / "fastfetch/config.jsonc"
        fastfetch.parent.mkdir(parents=True)
        fastfetch.symlink_to("../../my-fastfetch.jsonc")
        self.apply("headless")
        self.assertEqual(original.read_text(), '{"modules": ["kernel"]}\n')
        self.assertTrue(install.Config(self.home).uninstall())
        self.assertEqual(os.readlink(fastfetch), "../../my-fastfetch.jsonc")

    def test_replaced_fastfetch_config_is_kept_during_uninstall(self):
        self.apply("headless")
        fastfetch = self.config / "fastfetch/config.jsonc"
        fastfetch.unlink()
        fastfetch.write_text('{"modules": ["os"]}\n')
        self.assertFalse(install.Config(self.home).uninstall())
        self.assertEqual(fastfetch.read_text(), '{"modules": ["os"]}\n')

    def test_user_edits_outside_block_survive_uninstall(self):
        fish = self.write(".config/fish/config.fish", "# original\n")
        self.apply("headless")
        with fish.open("a") as output:
            output.write("set -gx ADDED_LATER yes\n")
        self.assertTrue(install.Config(self.home).uninstall())
        self.assertEqual(fish.read_text(), "# original\nset -gx ADDED_LATER yes\n")

    def test_original_symlinks_restore_without_editing_their_targets(self):
        original = self.write("my-own-fish.fish", "# my other repo\n")
        fish = self.config / "fish/config.fish"
        fish.parent.mkdir(parents=True)
        fish.symlink_to("../../my-own-fish.fish")
        completion = self.config / "fish/completions/uv.fish"
        completion.parent.mkdir(parents=True)
        completion.symlink_to("missing-original.fish")
        self.apply("headless")
        self.assertEqual(original.read_text(), "# my other repo\n")
        self.assertTrue(install.Config(self.home).uninstall())
        self.assertTrue(fish.is_symlink())
        self.assertEqual(os.readlink(fish), "../../my-own-fish.fish")
        self.assertTrue(completion.is_symlink())
        self.assertEqual(os.readlink(completion), "missing-original.fish")

    def test_dry_run_writes_nothing(self):
        install.Config(self.home, dry_run=True).install(
            "desktop", "/usr/bin/fish", "/some/ghostty")
        self.assertFalse(self.home.exists())

    def test_edited_launcher_is_kept_during_uninstall(self):
        self.apply("desktop")
        launcher = self.home / ".local/share/applications/terminal-dotfiles-ghostty.desktop"
        launcher.write_text("# user replacement\n")
        self.assertFalse(install.Config(self.home).uninstall())
        self.assertEqual(launcher.read_text(), "# user replacement\n")

    def test_malformed_hook_refused_before_config_changes(self):
        self.write(".config/fish/config.fish", install.BEGIN + "unfinished\n")
        with self.assertRaises(RuntimeError):
            self.apply("desktop")
        self.assertFalse((self.config / "fish/terminal-dotfiles").exists())
        self.assertFalse((self.home / ".local/state").exists())

    def test_new_install_uninstall_cleans_owned_files(self):
        self.apply("desktop")
        self.assertTrue(install.Config(self.home).uninstall())
        self.assertFalse((self.config / "fish/config.fish").exists())
        self.assertFalse((self.config / "ghostty/config").exists())
        self.assertFalse((self.config / "fish/completions/uv.fish").is_symlink())
        self.assertFalse((self.config / "fastfetch/config.jsonc").is_symlink())

    def test_cli_config_only_never_needs_packages(self):
        result = subprocess.run(
            ["bash", str(REPO / "install.sh"), "headless", "--config-only",
             "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.config / "fish/config.fish").exists())
        self.assertTrue((self.config / "fastfetch/config.jsonc").is_symlink())

    def test_relocation_repairs_links_and_preserves_original_backups(self):
        original = self.write(".config/fish/completions/uv.fish", "# keep me\n")
        self.apply("headless")
        moved_repo = Path(self.temporary.name) / "new checkout"
        shutil.copytree(REPO / "common", moved_repo / "common")
        shutil.copytree(REPO / "profiles", moved_repo / "profiles")
        with patch("install.REPO", moved_repo):
            self.apply("headless")
        self.assertEqual(original.resolve(), moved_repo / "common/fish/completions/uv.fish")
        self.assertEqual((self.config / "fastfetch/config.jsonc").resolve(),
                         moved_repo / "common/fastfetch/config.jsonc")
        self.assertTrue(install.Config(self.home).uninstall())
        self.assertEqual(original.read_text(), "# keep me\n")

    def test_xdg_paths_ignore_invalid_empty_values(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}):
            self.assertEqual(install.xdg_path("XDG_CONFIG_HOME", self.config), self.config)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative"}):
            self.assertEqual(install.xdg_path("XDG_CONFIG_HOME", self.config), self.config)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config)}):
            self.assertEqual(install.xdg_path("XDG_CONFIG_HOME", Path("/other")), self.config)

    def test_fastfetch_respects_custom_xdg_config_home(self):
        custom = self.home / "custom config"
        with patch("install.Path.home", return_value=self.home), \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": str(custom),
                                     "XDG_STATE_HOME": str(self.home / "custom state")}):
            config = install.Config(self.home)
            config.install("headless", "/usr/bin/fish", "/unused/ghostty")
            self.assertEqual((custom / "fastfetch/config.jsonc").resolve(),
                             REPO / "common/fastfetch/config.jsonc")
            self.assertTrue(config.uninstall())
            self.assertFalse((custom / "fastfetch/config.jsonc").is_symlink())

    def test_doctor_reports_missing_fastfetch(self):
        self.apply("headless")
        for available in (True, False):
            with self.subTest(available=available):
                def executable(name, _home):
                    return None if name == "fastfetch" and not available else "/bin/" + name

                with patch.object(sys, "argv", ["install.py", "doctor", "--home", str(self.home)]), \
                     patch("install.executable", side_effect=executable), \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(install.main(), 0 if available else 1)
                self.assertIn("fastfetch: " + ("/bin/fastfetch" if available else "MISSING"),
                              output.getvalue())


class PackageTests(unittest.TestCase):
    @patch("packages.install_ghostty")
    @patch("packages.executable", return_value="/usr/bin/already-installed")
    @patch("packages.os.geteuid", return_value=1000)
    def test_headless_never_installs_ghostty(self, _uid, _exe, ghostty):
        packages.install_tools("headless", Path("/example"), REPO)
        ghostty.assert_not_called()

    def test_verified_appimage_and_mismatch(self):
        payload = b"fake AppImage payload for an offline installer test"
        for correct in (True, False):
            with self.subTest(correct=correct), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                binary = home / ".local/bin/ghostty"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"previous")

                def fake_fetch(url, destination):
                    if "api.github.com" in url:
                        destination.write_text(json.dumps({"assets": [{
                            "name": "Ghostty-1.4.0-x86_64.AppImage",
                            "digest": "sha256:" + (hashlib.sha256(payload).hexdigest() if correct else "0" * 64),
                            "browser_download_url": "https://example.invalid/appimage",
                        }]}))
                    else:
                        destination.write_bytes(payload)

                with patch("packages.executable", return_value=None), \
                     patch("packages.platform.machine", return_value="x86_64"), \
                     patch("packages.fetch", side_effect=fake_fetch):
                    if correct:
                        packages.install_ghostty(home, REPO, False)
                        self.assertEqual(binary.read_bytes(), payload)
                        self.assertTrue(os.access(binary, os.X_OK))
                    else:
                        with self.assertRaises(RuntimeError):
                            packages.install_ghostty(home, REPO, False)
                        self.assertEqual(binary.read_bytes(), b"previous")

    def test_prompt_toml_and_headless_ascii(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("TOML parsing check requires Python 3.11+.")
        for profile in ("desktop", "headless"):
            text = (REPO / "profiles" / profile / "starship.toml").read_text()
            parsed = tomllib.loads(text)
            self.assertIn("$python", parsed["format"])
            if profile == "headless":
                self.assertTrue(text.isascii())
                self.assertTrue(parsed["username"]["show_always"])

    @unittest.skipUnless(shutil.which("fish"), "Fish executable unavailable in this test environment.")
    def test_fish_syntax(self):
        for path in (REPO / "common/fish").rglob("*.fish"):
            subprocess.run(["fish", "--no-execute", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
