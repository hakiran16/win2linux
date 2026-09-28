# Win2Linux

GNOME settings helper for Windows migrants — one-click toggles to make GNOME feel like Windows, plus an optional **Windows 10 theme for KDE Plasma** (based on [Dedoimedo's Plasma guide](https://www.dedoimedo.com/computers/plasma-look-like-win10.html)).

![GTK4 + libadwaita](https://img.shields.io/badge/GTK4-libadwaita-blue) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-yellow) ![License MIT](https://img.shields.io/badge/license-MIT-green)

## Features

**GNOME toggles (via `gsettings`, instant, reversible):**
- Swap Win+Space ↔ Alt+Shift for language switch
- Add US/IR keyboard layouts
- Tap-to-click, natural scroll, flat mouse accel
- Show battery %, 12-hour clock, dock-minimize, focus-on-hover, dock to bottom

**KDE Plasma — Windows 10 theme (user-local, reversible):**
- **Install** downloads We10XOS-kde + Segoe UI fonts to `~/.local/share/…`, backs up `kdeglobals/kwinrc/plasmarc` to `~/.config/win2linux/backups/`, then applies We10XOSLight colors, Segoe UI 10pt, Breeze (Tiny) decorations
- **Remove** deletes those files and restores the backup
- For the full Dedoimedo look, finish manually in System Settings: Breeze Twilight global theme, KwinDE/Win10 icons, and from Discover install **Tiled Menu** + **Present Windows Button** + a Win10 wallpaper
- Breeze10 decorations require manual compile (see guide) — app falls back to Breeze

## Requirements

- GNOME *or* KDE Plasma (theme section targets Plasma)
- Python 3.10+, PyGObject with `Gtk 4.0` + `Adw 1`, `gsettings` in PATH
- Plasma extras: `kwriteconfig5`/`kwriteconfig6`, `fc-cache`

## Run

```bash
python3 win2linux.py
# or
./win2linux.py
```

### Language

English is the default. Persian (`فارسی`) is also available — select it from the **Windows 10 Theme** row’s dropdown, or set `WIN2LINUX_LANG=fa` as an environment variable. The first launch may pre-seed from the system locale if it already contains `fa`/`fa_IR`; otherwise English is used. The UI mirrors right-to-left when Persian is active (`Gtk.TextDirection.RTL`).

Install deps on Ubuntu/Fedora:

```bash
# Ubuntu/Debian
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
# Fedora
sudo dnf install python3-gobject gtk4 libadwaita
```

## Install (desktop entry)

```bash
mkdir -p ~/.local/share/applications ~/.local/bin
cp win2linux.py ~/.local/bin/win2linux
cp win2linux.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications
```

## Attribution

Plasma theme recipe from [Dedoimedo — Make Plasma look like Windows 10](https://www.dedoimedo.com/computers/plasma-look-like-win10.html) (We10XOS-kde by yeyushengfan258, Segoe UI).

## License

MIT — see [LICENSE](LICENSE).
