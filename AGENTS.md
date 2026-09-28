# AGENTS.md

## Project

Single-file GTK4 / libadwaita app (`win2linux.py`, ~886 lines) that toggles GNOME settings to feel like Windows and optionally installs a Windows 10 look for KDE Plasma (Dedoimedo guide). No tests, no lint, no CI. Not a git repo (run `git init`; `update-desktop-database` after `.desktop` install).

**Languages**: English (default), Persian (`fa`) — UI strings table-driven, English fallback, full `set_direction(Gtk.TextDirection.RTL)` mirroring.

### Key files

- `win2linux.py` — all logic, UI, gsettings I/O, theme install/remove
- `win2linux.desktop` — `Exec=win2linux` (assumes `pip install -e .` or `python3 /path/win2linux.py`)
- `pyproject.toml` — `[project.scripts] win2linux = "win2linux:main"`, no runtime dependencies listed
- `README.md` — full feature list, install, requirements
- `AGENTS.md` — this file

## Verify

```bash
# Compile check (works only with PYTHONPYCACHEPREFIX because __pycache__ is root-owned)
PYTHONPYCACHEPREFIX=/tmp/pyc python3 -m py_compile win2linux.py && echo "OK"

# Quick import test (gi needs a display; headless may fail on the gi.require_version lines)
DISPLAY=:0 python3 -c "import win2linux; print('import OK')"
```

**Environment requirements**: GNOME or KDE Plasma, `gsettings` in PATH, PyGObject `Gtk 4.0 + Adw 1`, Plasma extras `kwriteconfig5/6`, `fc-cache`.

## Architecture

- `main()` → `Win2LinuxApp(Adw.Application, id=com.github.win2linux)` → `Win2LinuxWindow(720x580)`.
- `SettingItem(key,label,description,current_fn,apply_fn)` holds per-toggle state.
- `load_settings()` builds `self.settings` dict; `build_ui()` renders categorized `Adw.ActionRow` + `Gtk.Switch` + info `MessageDialog` inside `ToastOverlay`.
- Each setting has a `get_*` (reads gsettings) and `set_*` (writes gsettings) method pair.
- `run_gsettings(args)` → `subprocess.run(['gsettings',…], capture_output=True, timeout=5)`; returns `(stdout, ok)`.

### Adding / modifying a setting

1. Add a `SettingItem` entry in `load_settings()` (key, label, description, get_fn, apply_fn).
2. Ensure a `get_*` and `set_*` method exist on the window class.
3. Add the key to the appropriate category tuple in `build_ui()` (or it will never appear in the UI).
4. The `description` is split on `\n\n` — first paragraph becomes the row subtitle, rest appears in the ⓘ dialog.

## gsettings conventions

- `run_gsettings` returns `(stdout, ok)`; **25 of 26 setters ignore `ok`**, so a failed write still toasts "Enabled/Disabled". Check the return code if you need failure handling.
- `get_*` returning `False` can mean "off" or "schema/key missing". Several `get_*` methods (e.g. `get_dock_state`, `get_window_buttons_state`) explicitly test for `"No such schema"` / `"No such key"` and return `False` — do not assume off-state.
- **Inverted-polarity pattern**: `disable_hot_corner`/`set_hot_corner` and `detach_dialogs`/`set_detach_dialogs` flip the boolean (`'false' if active else 'true'`) because the gsettings key meaning is opposite to the UI label.
- `on_toggle` **must return `False`** for the `state-set` signal to propagate correctly.
- Theme row is custom (Install/Remove buttons), not created via `create_setting_row`.

## Theme subsystem

- Install/Remove are **button-driven**, not routed through `create_setting_row`. The `apply_fn` for `kde_windows_theme` is a literal `pass` (`win2linux.py:611`).
- `install_plasma_theme_threaded` / `remove_plasma_theme_threaded` run in a daemon thread + `GLib.idle_add` for UI updates.
- On-disk layout: marker at `~/.local/share/win2linux/theme-installed.json`, backups at `~/.config/win2linux/backups/<timestamp>/`.
- `theme_is_installed()` sniffs three paths; if all three exist → installed. **Fallback** may report installed even if only one path exists.
- `reset_to_breeze_defaults()` hardcodes 5 `kwriteconfig5` commands; does **not** touch `kglobalshortcutsrc` (backed up but never reset).
- **Known quirk**: each Segoe UI TTF is `shutil.copy2`‑ed **twice** at `win2linux.py:193–194` (harmless duplicate).
- **Known quirk**: dead `elif dst.exists(): pass` at `win2linux.py:105–106` (never triggered because `shutil.copy2` raises on missing source).
- **Known quirk**: `kglobalshortcutsrc` is backed up but the restore logic does not reset it.
- Unpinned `master` tarballs with `extractall` and no `filter=` → assumes archive layout (`We10XOS-kde master.tar.gz`, `segoe-ui-linux master.tar.gz`).

## Persian (`fa`) language support

- **Table-driven**, not gettext: `LANGUAGES = {"en": "English", "fa": "فارسی"}`; state persisted to `~/.config/win2linux/config.json`.
- **Default is English**. First launch may pre-seed from `GLib.get_language_names()` only if it already contains `fa`/`fa_IR`; otherwise `en`. An explicit choice is always honored.
- `WIN2LINUX_LANG=fa` env var overrides for headless smoke tests.
- One call mirrors the entire UI: `self.set_direction(Gtk.TextDirection.RTL if lang == "fa" else Gtk.TextDirection.LTR)` — mirrors header bar, `Adw.ActionRow` suffixes (switch/ⓘ/buttons), and all `Gtk.Align.START` labels.
- **Do not translate** (keep verbatim in both languages): gschema + key names, `Under the hood:` blocks, URLs, `We10XOS`/`Segoe UI`/`Breeze`/`KwinDE`/`Noto Sans`, distro names.
- `build_ui()` reconstructs wholesale on language change (`self.set_content(toolbar_view)`), so the dropdown's own tooltip/aria text also comes from the table.
- **Scope** (~60 translatable chunks): 18 SettingItem labels, 18 description paragraphs (split on `\n\n`), ~12 UI chrome strings, ~6 theme-row strings, ~10 toasts/dialogs.
- **Selector UI**: `Gtk.DropDown.new_from_strings(["English", "فارسی"])` in the header bar; `notify::selected` → `_apply_language(lang)` → `save_config(lang); load_settings(); build_ui(); set_direction`.

## Publishing

```bash
git init                              # already done
git branch -m main
git remote add origin <github-url>
git push -u main origin master          # or main
update-desktop-database ~/.local/share/applications  # after .desktop copy
```

*Full Dedoimedo look is only partly automated*: Breeze Twilight, KwinDE/Win10 icons, Tiled Menu + Present Windows Button from Discover, Win10 wallpaper still require manual steps (see README). Breeze10 decorations need a manual Qt compile fallback.

## Known Quirks (verified from source)

- `shutil.copy2(f, fonts_dst / f.name)` called **twice** at `win2linux.py:193–194` (Segoe UI TTFs). Harmless duplicate.
- **25 of 26 gsettings setters ignore the success flag** (`ok`), so a failed write still toasts "Enabled"/"Disabled".
- Dead `elif dst.exists(): pass` at `win2linux.py:105–106` (never reached because `shutil.copy2` raises on missing source).
- `kglobalshortcutsrc` is **backed up but never reset** during restore.
- `theme_is_installed()` fallback may report installed when only one of three sniff paths exists.
- `reset_to_breeze_defaults()` hardcodes 5 `kwriteconfig5` commands; does not reset `kglobalshortcutsrc`.
- Archive extraction uses `extractall(tmp)` with no `filter=` → assumes `master` tarball layout; may break if repo changes.
