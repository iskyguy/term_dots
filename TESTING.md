# Validation

Validation completed in the build environment:

- 15 unittest cases: 14 passed; 1 skipped because Fish is not installed.
- Bash syntax check for install.sh passed.
- Both desktop and headless dry-run commands completed without config writes.
- Git's whitespace/error check passed.

Behavior exercised with temporary homes and mocked downloads:

- Repeated installs keep one Fish source block and do not create new backups.
- Existing Fish/Ghostty content outside managed blocks remains intact.
- Original regular files, file permissions, and symlinks restore on uninstall.
- Later user edits outside managed blocks survive uninstall.
- Switching desktop to headless removes/restores desktop configuration and launcher.
- Headless bootstrap never invokes the Ghostty installer.
- Changed generated files are preserved rather than deleted during uninstall.
- Malformed hook markers fail before configuration changes.
- Config-only mode requires no package installation.
- Relocating the checkout repairs links while retaining original backups.
- Invalid XDG paths fall back to standard locations.
- Both Starship TOML files parse; the headless prompt configuration is ASCII.
- An AppImage digest mismatch leaves an existing binary untouched.

The Fish syntax test runs automatically when Fish is available.
Actual package downloads/installations, Fish/Starship prompt rendering, Ghostty
startup, and OpenCode clipboard behavior over SSH were not executed here.
Run install.sh doctor and a normal SSH session on the destination after installing.
