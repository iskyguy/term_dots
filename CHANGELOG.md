# Changelog

## v0.2 - 2026-11-02

### Added

- Fastfetch installation for both desktop and headless profiles, reusing existing
  installations or installing missing copies through Homebrew.
- A pinned, checksum-verified official Fastfetch fallback for x86-64 and ARM64,
  installed into ~/.local/bin without system layering or additional repositories.
- Shared Fastfetch configuration with reversible backups and XDG-aware symlinks.
- Automatic Fastfetch display in interactive Fish terminals, including SSH, with
  guards for scripts, redirected input/output, dumb terminals, and missing tools.
  Machine-local settings can disable automatic display.
- Fastfetch doctor checks and installation, configuration, and startup tests.
- Project release tracking in VERSION, separate from tool pins in versions.json.

### Changed

- Pull-and-reapply instructions now use the normal installer so newly added tools
  are installed. Existing tool versions are still preserved, not upgraded.
