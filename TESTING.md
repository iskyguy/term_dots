# Validation

Validation completed on Bazzite:

- 39 unittest cases passed, including Fish syntax and startup checks.
- Bash syntax check for install.sh passed.
- Both desktop and headless dry-run commands completed without config writes.
- Git's whitespace/error check passed.
- The desktop profile was applied, reusing Bazzite's Fastfetch 2.68.1.
- The installed profile passes install.sh doctor; another desktop dry-run plans
  no configuration changes.
- The pinned Fastfetch 2.70.0 x86-64 release was downloaded, checksum-verified,
  installed into a temporary home, executed, and checked against the shared config.
- The ARM64 release was downloaded, checksum-verified, and its binary extracted;
  it was not executed on this x86-64 host.

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
- Fastfetch uses Homebrew when available and the pinned release otherwise.
- Both Fastfetch architectures and their aliases select the correct release.
- Fastfetch checksum failures and failed replacements preserve existing binaries.
- Fastfetch archives are never extracted wholesale; missing/nonregular binaries
  and invalid archives are rejected, and staging files are cleaned up.
- Fastfetch config links respect XDG_CONFIG_HOME, survive profile switching and
  relocation, and restore previous files, permissions, and symlinks on uninstall.
- User replacements of the managed Fastfetch config survive uninstall.
- Doctor reports missing Fastfetch, and the shared config parses with Fastfetch.
- Interactive Fish and simulated SSH terminals invoke Fastfetch. Non-interactive
  shells, redirected input/output, dumb terminals, missing Fastfetch, and the
  machine-local opt-out all produce no Fastfetch startup output.

The unittest suite makes no network requests or package installations. Fish and
Fastfetch checks run automatically when their executables are available.

Ubuntu Server/Mint installations, ARM64 execution, live Homebrew/native package
installation, GUI rendering, Ghostty startup, and actual SSH/OpenCode clipboard
behavior were not tested here. Run install.sh doctor and a normal SSH session on
each destination after installing.
