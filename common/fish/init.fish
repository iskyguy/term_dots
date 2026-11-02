# Loaded at the end of config.fish by the installer's managed block.
# Keep machine-specific exports in ~/.config/fish/local.fish (outside Git).
fish_add_path --global "$HOME/.local/bin"
if test -d /home/linuxbrew/.linuxbrew/bin
    fish_add_path --global /home/linuxbrew/.linuxbrew/bin /home/linuxbrew/.linuxbrew/sbin
end

if not status is-interactive
    return
end

set -gx VIRTUAL_ENV_DISABLE_PROMPT 1
set -gx STARSHIP_CONFIG "$__fish_config_dir/terminal-dotfiles/starship.toml"

# Native Fish suggestions and Git completions need no third-party plugin.
abbr --add --position command gs 'git status --short --branch'
abbr --add --position command gsw 'git switch'
abbr --add --position command gd 'git diff'
abbr --add --position command gl 'git log --oneline --graph --decorate -15'
abbr --add --position command uvr 'uv run'

if command -q starship
    starship init fish | source
end

if test -f "$__fish_config_dir/local.fish"
    source "$__fish_config_dir/local.fish"
end

# Show system info only in real terminals, never in scripts or redirected output.
# Set TERMINAL_DOTFILES_FASTFETCH to 0 in local.fish to disable startup output.
if test "$TERMINAL_DOTFILES_FASTFETCH" != 0; and test "$TERM" != dumb
    if isatty stdin; and isatty stdout; and command -q fastfetch
        command fastfetch
    end
end
