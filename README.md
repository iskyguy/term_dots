# Terminal dotfiles

Release: **v0.2** ([VERSION](VERSION), [release notes](CHANGELOG.md)).
The project release is separate from the tool versions pinned in versions.json.

One Linux dotfiles repository, with two install profiles:

| Feature | desktop | headless |
| --- | --- | --- |
| Fish suggestions and Git completion | Yes | Yes |
| Starship: directory, Git branch/status, Python/active venv | Yes | Yes |
| uv and uvx completion | Yes | Yes |
| Fastfetch system summary in interactive Fish terminals | Yes | Yes |
| Host name in prompt | During SSH sessions | Always |
| Prompt symbols | Unicode; suits Ghostty | ASCII; no special font needed |
| Ghostty + app-menu launcher | Yes | No |
| Graphical packages, services, desktop changes | Ghostty only | None |

The headless profile assumes the machine is used through SSH or a text console.
Ghostty runs on your desktop; install headless on each remote machine where you
want the same Fish and Python tools.

## Install

Prerequisites: Linux, Bash, Python 3.9+, and network access for missing tools.
Use a regular user account with sudo access if native packages are missing.
Bazzite already supplies Fish, Fastfetch, and Python. Run on the host, outside
Distrobox/Toolbox. Use desktop on Bazzite/Linux Mint desktops and headless on
Ubuntu servers.

Keep the checkout at a permanent path because the installer creates symlinks.
For example, extract or clone into ~/src/terminal-dotfiles, then:

    cd ~/src/terminal-dotfiles
    bash install.sh desktop --dry-run
    bash install.sh desktop

On a remote/headless computer:

    cd ~/src/terminal-dotfiles
    bash install.sh headless --dry-run
    bash install.sh headless
    fish

No profile changes the login shell or starts an SSH server. Your existing GNOME
Files SFTP bookmarks, SSH keys, SSH configuration, and OpenCode settings are kept
outside this repository and are not managed.

### Start Fish automatically

Desktop: open **Ghostty (dotfiles)** from the application menu. Ghostty is
configured to start Fish. Bazzite recommends selecting the shell in the terminal
application rather than changing the system login shell.

Headless: connect directly into Fish with:

    ssh -t username@server fish

For a normal mutable Linux server, you can optionally make a native Fish install
your login shell after testing it. Check that the Fish path is listed in
/etc/shells, then run this from Fish:

    chsh -s (command -v fish)

This optional command changes future interactive logins; the installer does not
run it. On Bazzite/Atomic systems use the terminal command or ssh command above.
Uninstalling these dotfiles does not undo a login-shell change made separately.

### Configure tools you already installed

    bash install.sh desktop --config-only
    bash install.sh headless --config-only

Config-only makes no downloads or package-manager calls. If Fish is installed at
a custom path, pass e.g. --fish /custom/bin/fish. With no detected Fish executable,
config-only uses /usr/bin/fish; install Fish before launching Ghostty.

### How packages are installed

| Situation | Action |
| --- | --- |
| Tool already exists | Keep it; rerunning does not upgrade existing tools |
| Homebrew available, including normal Bazzite setups | Install missing Starship/uv/Fastfetch with brew |
| Fish/curl/tar missing on mutable Fedora, Debian/Ubuntu, or Mint | Install missing native packages with sudo dnf or apt-get |
| No Homebrew | Official Starship and uv installers, targeting ~/.local/bin |
| Fastfetch missing, no Homebrew | Pinned official Linux release, verified against the SHA-256 in versions.json, targeting ~/.local/bin |
| Desktop lacks Ghostty | Pinned community AppImage, SHA-256 verified against GitHub release metadata |
| Atomic host | No rpm-ostree layering or system shell changes |

Ghostty and the standalone Fastfetch fallback are version-pinned (versions.json).
Native/Homebrew packages and the official Starship/uv installers use their current
available versions; this is a version-controlled configuration, not a fully locked
OS environment. Existing tools are reused regardless of the pinned versions.

The bootstrap downloads the official Starship/uv installer scripts into temporary
files before executing them. It does not install Homebrew itself. On Atomic hosts
without Homebrew, the same user-local installer fallback works.

Fastfetch's standalone fallback uses the official compatibility (polyfilled)
tarball for x86-64 or ARM64. Only the Fastfetch binary is copied from the verified
archive. This also works on Ubuntu/Mint releases without a Fastfetch apt package;
no PPA, extra package repository, or system-wide installation is required. On
other architectures, install Fastfetch separately before rerunning the installer.

Ghostty's Linux AppImage is community-maintained and linked from Ghostty's
documentation. If GitHub blocks the download, omits its asset digest, or your
system cannot run AppImages, install Ghostty using its documented distribution
options and rerun this installer; existing Ghostty installations are reused.
The headless profile never downloads Ghostty.

## What is managed

- Fish config: an explicitly marked source block appended to config.fish.
- Shared Fish initialization and uv/uvx completion: symlinks into this checkout.
- Starship: a symlink to the selected profile; your original starship.toml remains
  untouched. The Fish init sets STARSHIP_CONFIG to the managed profile.
- Fastfetch: ~/.config/fastfetch/config.jsonc links to the shared configuration.
  An existing file or symlink is backed up and restored on uninstall.
- Desktop Ghostty: a marked settings block in ~/.config/ghostty/config, plus a
  launcher in ~/.local/share/applications/terminal-dotfiles-ghostty.desktop.
  Ghostty still supports this config filename and loads it after config.ghostty.
  An existing config.ghostty is left intact; the managed settings take precedence
  over earlier values of those same options.

XDG_CONFIG_HOME and XDG_STATE_HOME are respected when set.
Only marked blocks in existing Fish/Ghostty files are updated. Existing content
outside the blocks is preserved, including changes you add later.

Before replacing an existing managed path or editing a configuration for the first
time, the installer records a backup under:

    ~/.local/state/terminal-dotfiles/backups/

That directory is outside the repository. State is recorded in state.json beside
the backups. Keep the state if you want uninstall to restore previous files.

Uninstall restores the original managed files where possible and removes its
blocks. If you replaced a generated file after installation, uninstall leaves your
replacement alone and reports it instead of deleting it. Review the printed
backup paths if manual recovery is needed.

Installed programs and downloaded binaries stay installed after uninstall.
Backups and empty parent directories are retained. No Git identity is configured.

## Customize and sync

Edit these tracked files:

- common/fish/init.fish: paths, abbreviations, Starship initialization.
- common/fastfetch/config.jsonc: shared system summary and logo settings.
- profiles/desktop/starship.toml: desktop prompt.
- profiles/headless/starship.toml: remote prompt.
- profiles/desktop/ghostty.config: Ghostty settings.
- versions.json: Ghostty and standalone Fastfetch versions, plus Fastfetch checksums.

Fish and Starship edits take effect in a new Fish session. Reapply the desktop
profile after changing ghostty.config, because its marked block is generated.
Keep machine-specific exports in ~/.config/fish/local.fish; the shared init
sources that file during interactive sessions, before displaying Fastfetch.
It is outside this checkout.

Useful abbreviations (expand when you type a space):

| Abbreviation | Expansion |
| --- | --- |
| gs | git status --short --branch |
| gsw | git switch |
| gd | git diff |
| gl | git log --oneline --graph --decorate -15 |
| uvr | uv run |

Initialize your repository after extracting:

    git init -b main
    git add .
    git commit -m "Add desktop and headless terminal dotfiles"

Set your Git name/email beforehand if they are not already configured. Add your
own remote with git remote add origin YOUR_REPOSITORY_URL, then git push -u origin
main. No account, credentials, or remote URL is embedded in this project.

For subsequent installations:

    git clone YOUR_REPOSITORY_URL ~/src/terminal-dotfiles
    cd ~/src/terminal-dotfiles
    bash install.sh desktop

Use headless on servers. To switch an existing machine, rerun the installer with
the other profile. Switching to headless restores/removes the managed Ghostty
configuration and launcher but leaves the Ghostty program installed.

Pull updates on each machine, then reapply its profile:

    git pull --ff-only
    bash install.sh headless

Use desktop instead of headless on desktops. Reapplying the normal installer
installs any newly added tools, such as Fastfetch, while preserving existing ones.
Use --config-only when all tools are already installed and you want no downloads
or package-manager calls. Pulling alone does not install missing tools or new links.

If you move the checkout, rerun from the new path to repair the symlinks and source
block. Configure the same XDG environment when installing and uninstalling.

## System summary (Fastfetch)

Both profiles automatically run Fastfetch when starting an interactive Fish shell
with terminal input and output, including SSH sessions. Scripts, non-interactive
SSH commands, redirected input/output, and TERM=dumb sessions stay quiet. If
Fastfetch is missing (for example after a config-only install), startup skips it.

The shared configuration uses the detected distro's built-in ASCII logo and
plain text labels, with no special font, image backend, or graphical dependency.
Only local system information is requested: no weather or public-IP network calls.
Edit common/fastfetch/config.jsonc to customize the display; linked changes apply
the next time Fastfetch runs, including after a pull.

To disable automatic display on one machine, add this to
~/.config/fish/local.fish (or $XDG_CONFIG_HOME/fish/local.fish):

    set -g TERMINAL_DOTFILES_FASTFETCH 0

You can still run fastfetch manually at any time.

## Python environments

From Fish:

    uv init my-project
    cd my-project
    uv run python --version

uv run creates/uses the project environment without explicit activation.
If you want an active environment shown in the prompt:

    source .venv/bin/activate.fish

Leave it with deactivate. Starship displays the active environment; it does not
create environments or automatically activate them when changing directories.

## SSH and clipboard

Ghostty enables OSC 52 clipboard writes and the ssh-env/ssh-terminfo helpers.
OpenCode can run on the remote host while Ghostty receives clipboard sequences
locally. Exact OpenCode/tmux clipboard behavior still depends on those versions.
OpenCode itself is installed and configured separately.

For a basic clipboard check, run this on the remote machine from Ghostty:

    printf '\033]52;c;dGVzdA==\a'

Then paste into a local text editor; it should contain test. Use an ordinary SSH
session first when diagnosing clipboard problems, before adding tmux.

File transfers remain in GNOME Files via your existing sftp:// bookmarks.
This repo does not install a file manager or configure persistent network mounts.

## Check, test, and remove

    bash install.sh doctor
    python3 -m unittest discover -s tests -v
    bash -n install.sh
    bash install.sh uninstall --dry-run
    bash install.sh uninstall

The tests use temporary homes, fake downloads, and no package installations or
network requests. When Fastfetch is available, its configuration is checked locally.
They check file preservation, backups, repeated installs, profile switching,
edited-file protection, dry-run behavior, prompt TOML, AppImage/Fastfetch verification,
and safe Fastfetch archive handling. Fish syntax and startup behavior in simulated
terminals are checked when Fish is available; otherwise those tests are skipped.

Testing support: --home /a/temporary/home --config-only redirects config and
state operations without changing the HOME environment variable.

Live package installation, GUI rendering, and an actual remote OpenCode session
must be checked on your target machines. Those checks cannot be inferred from
the offline tests.

## Upgrades

For Brew-installed tools:

    brew upgrade starship uv

If Homebrew installed Fastfetch, update it with brew upgrade fastfetch. A bundled
or native-package Fastfetch installation is updated through its OS instead.

For a standalone uv installation:

    uv self update

For standalone Starship, rerun its official installer targeting ~/.local/bin.
For the managed Ghostty AppImage, download the desired stable release, verify its
checksum, and replace ~/.local/bin/ghostty while Ghostty is closed. Updating
versions.json changes the default for new machines; it does not overwrite an
existing executable automatically.

For standalone Fastfetch, download a chosen official compatibility tarball, verify
its checksum, and replace ~/.local/bin/fastfetch. When changing its pinned default,
update the version and both architecture checksums in versions.json together.
That pin only affects new installations, not an existing Fastfetch executable.

## Reference documentation

- https://docs.bazzite.gg/Advanced/Best_Shell_Practices/
- https://docs.bazzite.gg/Installing_and_Managing_Software/Homebrew/
- https://ghostty.org/docs/install/binary
- https://github.com/pkgforge-dev/ghostty-appimage
- https://ghostty.org/docs/config
- https://ghostty.org/docs/config/reference
- https://fishshell.com/docs/current/
- https://starship.rs/guide/
- https://starship.rs/config/
- https://docs.astral.sh/uv/getting-started/installation/
- https://docs.astral.sh/uv/reference/installer/
- https://github.com/fastfetch-cli/fastfetch
- https://github.com/fastfetch-cli/fastfetch/wiki/Configuration
