"""Install missing tools; no package operations run in config-only mode."""
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


def executable(name, home):
    candidate = home / ".local/bin" / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    candidate = Path("/home/linuxbrew/.linuxbrew/bin") / name
    return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None


def run(argv, dry_run=False, env=None):
    print("+ " + shlex.join([str(arg) for arg in argv]))
    if not dry_run:
        try:
            subprocess.run(argv, check=True, env=env)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Command failed with exit code {error.returncode}: "
                               + shlex.join([str(arg) for arg in argv])) from error


def fetch(url, destination):
    print("Download: " + url)
    request = urllib.request.Request(url, headers={
        "User-Agent": "terminal-dotfiles",
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        with open(destination, "wb") as output:
            shutil.copyfileobj(response, output)


def install_ghostty(home, repo, dry_run):
    if executable("ghostty", home):
        print("Keep existing Ghostty.")
        return
    architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(
        platform.machine(), platform.machine()
    )
    if architecture not in ("x86_64", "aarch64"):
        raise RuntimeError("Ghostty AppImage supports x86_64 or aarch64 here.")
    version = json.loads((repo / "versions.json").read_text())["ghostty"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\+\d+)?", version):
        raise RuntimeError("Invalid Ghostty version in versions.json.")
    asset_name = f"Ghostty-{version}-{architecture}.AppImage"
    binary = home / ".local/bin/ghostty"
    if dry_run:
        print(f"Would download and verify Ghostty {version} ({architecture}) -> {binary}")
        return
    binary.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dotfiles-download-") as temporary:
        temporary = Path(temporary)
        metadata = temporary / "release.json"
        tag = urllib.parse.quote("v" + version, safe="")
        fetch(f"https://api.github.com/repos/pkgforge-dev/ghostty-appimage/releases/tags/{tag}", metadata)
        release = json.loads(metadata.read_text())
        asset = next((item for item in release.get("assets", [])
                      if item["name"] == asset_name), None)
        if asset is None:
            raise RuntimeError(f"Release has no {asset_name}. Check versions.json.")
        expected = asset.get("digest") or ""
        if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", expected):
            raise RuntimeError("GitHub did not supply an AppImage SHA-256 digest. "
                               "Install Ghostty manually, then rerun; see README.")
        downloaded = temporary / asset_name
        fetch(asset["browser_download_url"], downloaded)
        checksum = hashlib.sha256()
        with downloaded.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                checksum.update(chunk)
        actual = checksum.hexdigest()
        if actual.lower() != expected.split(":", 1)[1].lower():
            raise RuntimeError("Ghostty download failed its SHA-256 check.")
        staged = binary.with_name(".ghostty.dotfiles-download")
        try:
            shutil.copyfile(downloaded, staged)
            staged.chmod(0o755)
            os.replace(staged, binary)
        finally:
            staged.unlink(missing_ok=True)


def install_tools(profile, home, repo, dry_run=False):
    if platform.system() != "Linux":
        raise RuntimeError("This bootstrap targets Linux; use --config-only elsewhere.")
    if os.geteuid() == 0 and not dry_run:
        raise RuntimeError("Run without sudo as your normal user. "
                           "Only native package installation requests sudo.")
    brew = executable("brew", home)
    native_missing = [name for name in ("fish", "curl", "tar")
                      if not executable(name, home)]
    if native_missing:
        if Path("/run/ostree-booted").exists():
            if "fish" in native_missing and brew:
                run([brew, "install", "fish"], dry_run)
                native_missing.remove("fish")
            if native_missing:
                raise RuntimeError("Missing on Atomic host: " + ", ".join(native_missing)
                                   + ". Bazzite normally includes these tools.")
        else:
            manager = shutil.which("apt-get") or shutil.which("dnf")
            if not manager:
                raise RuntimeError("Install fish, curl and tar first; apt/dnf not found.")
            if not shutil.which("sudo"):
                raise RuntimeError("sudo is required to install missing native packages.")
            if Path(manager).name == "apt-get":
                run(["sudo", manager, "update"], dry_run)
            run(["sudo", manager, "install", "-y"] + native_missing, dry_run)

    missing = [name for name in ("starship", "uv") if not executable(name, home)]
    if brew and missing:
        run([brew, "install"] + missing, dry_run)
    elif missing:
        if dry_run:
            for name in missing:
                print(f"Would run official {name} installer into {home / '.local/bin'}")
        else:
            target = home / ".local/bin"
            target.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="dotfiles-install-") as temporary:
                for name in missing:
                    script = Path(temporary) / (name + ".sh")
                    if name == "starship":
                        fetch("https://starship.rs/install.sh", script)
                        run(["sh", str(script), "--yes", "--bin-dir", str(target)])
                    else:
                        fetch("https://astral.sh/uv/install.sh", script)
                        environment = dict(os.environ, UV_INSTALL_DIR=str(target),
                                           UV_NO_MODIFY_PATH="1")
                        run(["sh", str(script)], env=environment)
    if profile == "desktop":
        install_ghostty(home, repo, dry_run)
