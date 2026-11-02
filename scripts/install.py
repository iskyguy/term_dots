#!/usr/bin/env python3
"""Manage reversible dotfile links and explicitly delimited config blocks."""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from packages import executable, install_tools

REPO = Path(__file__).resolve().parents[1]
BEGIN = "\n# >>> terminal-dotfiles >>>\n"
END = "# <<< terminal-dotfiles <<<\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def present(path):
    return path.exists() or path.is_symlink()


def xdg_path(variable, fallback):
    value = os.environ.get(variable)
    return Path(value) if value and Path(value).is_absolute() else fallback


def strip_block(text):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise RuntimeError("Malformed terminal-dotfiles block; repair its markers first.")
    if BEGIN not in text:
        return text
    start = text.index(BEGIN)
    finish = text.index(END, start) + len(END)
    return text[:start] + text[finish:]


def fish_quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def desktop_quote(value):
    value = str(value).replace("%", "%%")
    for character in ("\\", '"', "$", chr(96)):
        value = value.replace(character, "\\" + character)
    return '"' + value + '"'


class Config:
    def __init__(self, home, dry_run=False):
        self.home = home
        actual_home = home == Path.home().resolve()
        self.config = xdg_path("XDG_CONFIG_HOME", home / ".config") if actual_home else home / ".config"
        self.state_dir = xdg_path("XDG_STATE_HOME", home / ".local/state") if actual_home else home / ".local/state"
        self.state_dir = self.state_dir / "terminal-dotfiles"
        self.state_path = self.state_dir / "state.json"
        self.dry_run = dry_run
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {
            "schema": 1, "entries": {}, "hooks": {}
        }
        if self.state.get("schema") != 1:
            raise RuntimeError("Unsupported state schema.")

    def atomic_write(self, path, data, mode=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode is None:
            mode = stat.S_IMODE(path.stat().st_mode) if path.is_file() else 0o644
        descriptor, name = tempfile.mkstemp(prefix=".dotfiles-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def backup(self, path):
        if path.is_dir() and not path.is_symlink():
            raise RuntimeError(f"Expected a file, found a directory: {path}")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = self.state_dir / "backups" / stamp / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination, follow_symlinks=False)
        print(f"Backup: {path} -> {destination}")
        return str(destination)

    def save(self):
        if not self.dry_run:
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.atomic_write(self.state_path,
                              (json.dumps(self.state, indent=2) + "\n").encode(), 0o600)

    @staticmethod
    def matches(path, entry):
        if entry["kind"] == "link":
            return path.is_symlink() and os.readlink(path) == entry["source"]
        return (path.is_file() and not path.is_symlink()
                and digest(path.read_bytes()) == entry["digest"])

    def managed(self, path, source=None, text=None):
        key = str(path)
        old = self.state["entries"].get(key)
        desired = {"kind": "link", "source": str(source)} if source else {
            "kind": "file", "digest": digest(text.encode())
        }
        if old and self.matches(path, old) and all(old.get(k) == v for k, v in desired.items()):
            return
        print(f"{'Link' if source else 'Write'}: {path}")
        if self.dry_run:
            return
        backup = old.get("backup") if old else None
        if present(path) and not (old and self.matches(path, old)):
            conflict = self.backup(path)
            if not old:
                backup = conflict
        path.parent.mkdir(parents=True, exist_ok=True)
        if source:
            temporary = path.with_name(path.name + ".dotfiles-link")
            if present(temporary):
                raise RuntimeError(f"Temporary path already exists: {temporary}")
            try:
                temporary.symlink_to(source)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            self.atomic_write(path, text.encode())
        desired["backup"] = backup
        self.state["entries"][key] = desired
        self.save()

    def hook(self, path, body):
        raw = path.read_bytes() if present(path) else b""
        base = strip_block(raw.decode("utf-8"))
        new = (base + BEGIN + body.rstrip("\n") + "\n" + END).encode()
        if raw == new:
            return
        print(f"Update managed block: {path}")
        if self.dry_run:
            return
        key = str(path)
        if key not in self.state["hooks"]:
            self.state["hooks"][key] = {
                "backup": self.backup(path) if present(path) else None,
                "original_digest": digest(raw),
            }
        self.atomic_write(path, new)
        self.save()

    def remove_hook(self, key):
        path = Path(key)
        entry = self.state["hooks"][key]
        print(f"Remove managed block: {path}")
        if self.dry_run:
            return
        if present(path):
            raw = path.read_bytes()
            clean = strip_block(raw.decode("utf-8")).encode()
            if digest(clean) == entry["original_digest"]:
                path.unlink()
                if entry["backup"]:
                    shutil.copy2(entry["backup"], path, follow_symlinks=False)
            elif clean != raw:
                self.atomic_write(path, clean)
        del self.state["hooks"][key]
        self.save()

    def remove_entry(self, key):
        path = Path(key)
        entry = self.state["entries"][key]
        print(f"Remove managed file/link: {path}")
        if self.dry_run:
            return True
        if present(path) and not self.matches(path, entry):
            print(f"Kept edited/unmanaged file: {path}. Original backup: {entry.get('backup')}")
            return False
        if present(path):
            path.unlink()
        if entry.get("backup"):
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry["backup"], path, follow_symlinks=False)
        del self.state["entries"][key]
        self.save()
        return True

    def install(self, profile, fish, ghostty):
        shared = self.config / "fish/terminal-dotfiles"
        links = {
            shared / "init.fish": REPO / "common/fish/init.fish",
            shared / "starship.toml": REPO / f"profiles/{profile}/starship.toml",
            self.config / "fish/completions/uv.fish": REPO / "common/fish/completions/uv.fish",
            self.config / "fish/completions/uvx.fish": REPO / "common/fish/completions/uvx.fish",
            self.config / "fastfetch/config.jsonc": REPO / "common/fastfetch/config.jsonc",
        }
        fish_config = self.config / "fish/config.fish"
        fish_body = f"if test -f {fish_quote(shared / 'init.fish')}\n    source {fish_quote(shared / 'init.fish')}\nend"
        hooks = {fish_config: fish_body}
        files = {}
        if profile == "desktop":
            # Ghostty still loads config after config.ghostty. Only this block changes.
            ghostty_body = ((REPO / "profiles/desktop/ghostty.config").read_text()
                            + "command = " + shlex.quote(fish) + "\n")
            hooks[self.config / "ghostty/config"] = ghostty_body
            launcher = self.home / ".local/share/applications/terminal-dotfiles-ghostty.desktop"
            files[launcher] = (
                "[Desktop Entry]\nType=Application\nName=Ghostty (dotfiles)\n"
                f"Exec={desktop_quote(ghostty)}\n"
                "Icon=utilities-terminal\nTerminal=false\nCategories=System;TerminalEmulator;\n"
            )
        for path in list(links) + list(files) + list(hooks):
            if path.is_dir():
                raise RuntimeError(f"Expected a file, found a directory: {path}")
        for path in hooks:
            if present(path):
                strip_block(path.read_bytes().decode("utf-8"))
        wanted = {str(path) for path in list(links) + list(files)}
        for key in list(self.state["entries"]):
            if key not in wanted and not self.remove_entry(key):
                raise RuntimeError("Resolve the edited managed file before switching profiles.")
        for key in list(self.state["hooks"]):
            if key not in {str(path) for path in hooks}:
                self.remove_hook(key)
        for path, source in links.items():
            self.managed(path, source=source)
        for path, text in files.items():
            self.managed(path, text=text)
        for path, body in hooks.items():
            self.hook(path, body)
        self.state.update(profile=profile, repo=str(REPO))
        self.save()

    def uninstall(self):
        complete = True
        for key in list(self.state["hooks"]):
            self.remove_hook(key)
        for key in list(self.state["entries"]):
            complete = self.remove_entry(key) and complete
        if not self.dry_run and complete:
            self.state.pop("profile", None)
            self.save()
        return complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("desktop", "headless", "uninstall", "doctor"))
    parser.add_argument("--config-only", action="store_true", help="Skip package installation and all downloads.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writes or network.")
    parser.add_argument("--home", type=Path, help="Alternate target home; requires --config-only for installs.")
    parser.add_argument("--fish", help="Absolute Fish executable path for desktop config.")
    args = parser.parse_args()
    home = (args.home or Path.home()).expanduser().resolve()
    if args.home and args.profile in ("desktop", "headless") and not (args.config_only or args.dry_run):
        parser.error("--home requires --config-only or --dry-run.")
    if args.fish and (not os.path.isabs(args.fish) or "\n" in args.fish or "\r" in args.fish):
        parser.error("--fish must be an absolute path without newlines.")
    config = Config(home, args.dry_run)
    if args.profile == "uninstall":
        return 0 if config.uninstall() else 1
    if args.profile == "doctor":
        profile = config.state.get("profile")
        print("Active profile:", profile or "none")
        names = ["fish", "starship", "uv", "fastfetch"] + (["ghostty"] if profile == "desktop" else [])
        okay = bool(profile)
        for name in names:
            location = executable(name, home)
            print(f"{name}: {location or 'MISSING'}")
            okay = bool(location) and okay
        for key, entry in config.state["entries"].items():
            if not config.matches(Path(key), entry):
                print("Changed or missing managed path:", key)
                okay = False
        for key in config.state["hooks"]:
            path = Path(key)
            if not path.is_file() or BEGIN not in path.read_text() or END not in path.read_text():
                print("Missing managed configuration block:", key)
                okay = False
        return 0 if okay else 1
    if not args.config_only:
        install_tools(args.profile, home, REPO, args.dry_run)
    fish = args.fish or executable("fish", home) or "/usr/bin/fish"
    ghostty = executable("ghostty", home) or str(home / ".local/bin/ghostty")
    config.install(args.profile, fish, ghostty)
    print(f"{'Planned' if args.dry_run else 'Installed'} {args.profile} profile.")
    if not args.dry_run:
        print("Start a new Fish session (fish), or reopen Ghostty.")
        print("Configuration is linked to this checkout; keep it here, or rerun after moving it.")
    return 0


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9+ is required.")
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        sys.exit("Error: " + str(error))
