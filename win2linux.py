#!/usr/bin/env python3
"""
Win2Linux - GNOME settings helper for Windows migrants.
Applies Windows-familiar defaults via gsettings and optionally
installs a Windows 10 look for KDE Plasma (Dedoimedo guide).
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib
import subprocess
import os
import shutil
import tempfile
import urllib.request
import tarfile
import configparser
import threading
import json
from pathlib import Path


MARKER = Path.home() / ".local" / "share" / "win2linux" / "theme-installed.json"
BACKUP_DIR = Path.home() / ".config" / "win2linux" / "backups"


class SettingItem:
    def __init__(self, key, label, description, current_fn, apply_fn):
        self.key = key
        self.label = label
        self.description = description
        self.current_fn = current_fn
        self.apply_fn = apply_fn
        self._active = False

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, value):
        self._active = value


# ── Plasma Windows-10 theme helpers (Dedoimedo guide) ──────────────
# Ingredients from https://www.dedoimedo.com/computers/plasma-look-like-win10.html:
#   We10XOS plasma theme, Breeze10 decorations, Segoe UI, KwinDE/Win10 icons,
#   Win10 wallpaper, Present Windows Button, Tiled Menu.
# Applied config: Breeze Twilight global, Breeze Dark plasma style,
#   We10XOSLight colors, Segoe UI 10pt, KwinDE icons, We10XOS-light splash.

THEME_SOURCES = {
    "we10xos": "https://github.com/yeyushengfan258/We10XOS-kde/archive/refs/heads/master.tar.gz",
    "segoe": "https://github.com/mrbvrz/segoe-ui-linux/archive/refs/heads/master.tar.gz",
    "icons_kwinde": "https://store.kde.org/p/1387736/",
}

KDE_CONFIG_FILES = ["kdeglobals", "kwinrc", "plasmarc", "kglobalshortcutsrc"]


def is_plasma() -> bool:
    return shutil.which("plasmashell") is not None or os.environ.get("XDG_CURRENT_DESKTOP", "").lower().find("kde") != -1


def theme_is_installed() -> bool:
    if MARKER.exists():
        return True
    candidates = [
        Path.home() / ".local/share/plasma/desktoptheme/We10XOS",
        Path.home() / ".local/share/color-schemes/We10XOSLight.colors",
        Path.home() / ".local/share/icons/KwinDE",
    ]
    return any(p.exists() for p in candidates)


def backup_kde_configs() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / ts
    dest.mkdir(parents=True)
    for name in KDE_CONFIG_FILES:
        src = Path.home() / ".config" / name
        if src.exists():
            shutil.copy2(src, dest / name)
    meta = {"created": ts, "files": KDE_CONFIG_FILES}
    (dest / "meta.json").write_text(json.dumps(meta, indent=2))
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({"backup": str(dest), "installed_at": ts}, indent=2))
    return dest


def restore_kde_configs() -> str:
    if MARKER.exists():
        try:
            data = json.loads(MARKER.read_text())
            bdir = Path(data.get("backup", ""))
            if bdir.exists():
                for name in KDE_CONFIG_FILES:
                    src = bdir / name
                    dst = Path.home() / ".config" / name
                    if src.exists():
                        shutil.copy2(src, dst)
                    elif dst.exists():
                        pass
                return f"Restored from {bdir.name}"
        except Exception:
            pass
    latest = sorted(BACKUP_DIR.glob("*"), reverse=True)
    if latest:
        bdir = latest[0]
        for name in KDE_CONFIG_FILES:
            src = bdir / name
            dst = Path.home() / ".config" / name
            if src.exists():
                shutil.copy2(src, dst)
        return f"Restored from {bdir.name}"
    return "No backup found — resetting to Breeze defaults"


def reset_to_breeze_defaults():
    for cmd in [
        ["kwriteconfig5", "--file", "kdeglobals", "--group", "General", "--key", "ColorScheme", "BreezeLight"],
        ["kwriteconfig5", "--file", "kdeglobals", "--group", "General", "--key", "XftHintStyle", "hintslight"],
        ["kwriteconfig5", "--file", "kdeglobals", "--group", "WM", "--key", "activeFont", "Noto Sans,10,-1,5,75,0,0,0,0,0"],
        ["kwriteconfig5", "--file", "kwinrc", "--group", "org.kde.kdecoration2", "--key", "library", "org.kde.kwin.aurorae"],
        ["kwriteconfig5", "--file", "kwinrc", "--group", "org.kde.kdecoration2", "--key", "theme", "Breeze"],
    ]:
        try:
            subprocess.run(cmd, timeout=5)
        except Exception:
            pass


def download(url: str, dest: Path):
    urllib.request.urlretrieve(url, str(dest))


def install_plasma_theme_threaded(on_progress, on_done):
    def run():
        tmp = None
        try:
            on_progress("Backing up current Plasma settings…")
            backup_kde_configs()

            on_progress("Downloading We10XOS theme…")
            tmp = Path(tempfile.mkdtemp(prefix="win2linux-"))
            archive = tmp / "we10xos.tar.gz"
            download(THEME_SOURCES["we10xos"], archive)
            with tarfile.open(archive) as tf:
                tf.extractall(tmp)

            src_root = next((p for p in tmp.iterdir() if p.is_dir() and "We10XOS" in p.name), None)
            if src_root is None:
                raise RuntimeError("We10XOS archive layout unexpected")

            targets = {
                "color-schemes": Path.home() / ".local/share/color-schemes",
                "plasma/desktoptheme": Path.home() / ".local/share/plasma/desktoptheme",
                "aurorae/themes": Path.home() / ".local/share/aurorae/themes",
                "konsole": Path.home() / ".local/share/konsole",
                "plasma/look-and-feel": Path.home() / ".local/share/plasma/look-and-feel",
            }
            for sub, dst in targets.items():
                src = src_root / sub
                if src.exists():
                    dst.mkdir(parents=True, exist_ok=True)
                    for item in src.iterdir():
                        d = dst / item.name
                        if d.exists():
                            if d.is_dir():
                                shutil.rmtree(d)
                            else:
                                d.unlink()
                        if item.is_dir():
                            shutil.copytree(item, d)
                        else:
                            shutil.copy2(item, d)

            # Fonts — clone Segoe UI archive; install to ~/.local/share/fonts
            try:
                on_progress("Installing Segoe UI fonts…")
                fonts_archive = tmp / "segoe.tar.gz"
                download(THEME_SOURCES["segoe"], fonts_archive)
                with tarfile.open(fonts_archive) as tf:
                    tf.extractall(tmp)
                segoe_root = next((p for p in tmp.iterdir() if p.is_dir() and "segoe" in p.name.lower()), None)
                if segoe_root:
                    fonts_dst = Path.home() / ".local/share/fonts/win10-segoe"
                    fonts_dst.mkdir(parents=True, exist_ok=True)
                    for f in segoe_root.rglob("*.ttf"):
                        shutil.copy2(f, fonts_dst / f.name)
                        shutil.copy2(f, fonts_dst / f.name)
                    for f in segoe_root.rglob("*.TTF"):
                        shutil.copy2(f, fonts_dst / f.name)
                    try:
                        subprocess.run(["fc-cache", "-f", str(fonts_dst)], timeout=10)
                    except Exception:
                        pass
            except Exception as e:
                on_progress(f"Fonts step skipped: {e}")

            on_progress("Applying Plasma settings…")
            # Dedoimedo settings
            kwrite = shutil.which("kwriteconfig5") or shutil.which("kwriteconfig6")
            if kwrite:
                settings = [
                    [kwrite, "--file", "kdeglobals", "--group", "General", "--key", "ColorScheme", "We10XOSLight"],
                    [kwrite, "--file", "kdeglobals", "--group", "General", "--key", "font", "Segoe UI,10,-1,5,50,0,0,0,0,0"],
                    [kwrite, "--file", "kdeglobals", "--group", "General", "--key", "menuFont", "Segoe UI,10,-1,5,50,0,0,0,0,0"],
                    [kwrite, "--file", "kdeglobals", "--group", "General", "--key", "smallestReadableFont", "Segoe UI,8,-1,5,50,0,0,0,0,0"],
                    [kwrite, "--file", "kdeglobals", "--group", "WM", "--key", "activeFont", "Segoe UI,10,-1,5,75,0,0,0,0,0"],
                    [kwrite, "--file", "kdeglobals", "--group", "Icons", "--key", "Theme", "KwinDE"],
                ]
                for cmd in settings:
                    try:
                        subprocess.run(cmd, timeout=5, capture_output=True)
                    except Exception:
                        pass
                # Breeze10 decorations need compilation — fall back to Breeze with thin borders
                try:
                    subprocess.run([kwrite, "--file", "kwinrc", "--group", "org.kde.kdecoration2", "--key", "library", "org.kde.breeze"], timeout=5)
                    subprocess.run([kwrite, "--file", "kwinrc", "--group", "org.kde.kdecoration2", "--key", "theme", "Breeze"], timeout=5)
                    subprocess.run([kwrite, "--file", "kwinrc", "--group", "org.kde.kdecoration2", "--key", "BorderSize", "Tiny"], timeout=5)
                except Exception:
                    pass
            else:
                on_progress("kwriteconfig not found — theme files installed, apply manually in System Settings.")

            # Wallpaper hint
            on_progress("Done. Log out and back in (or restart Plasma) to fully apply.")

            # Suggest optional Discover widgets (manual)
            GLib.idle_add(lambda: on_done(True, "Windows 10 theme installed. For full Dedoimedo look:\n• System Settings → Global Theme → Breeze Twilight\n• Window Decorations → Breeze (Tiny borders)\n• Icons → KwinDE (or Win10I)\n• Install 'Tiled Menu' & 'Present Windows Button' from Discover.\nLog out/in to apply."))
        except Exception as e:
            GLib.idle_add(lambda: on_done(False, f"Install failed: {e}"))
            return
        finally:
            if tmp and tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    threading.Thread(target=run, daemon=True).start()


def remove_plasma_theme_threaded(on_progress, on_done):
    def run():
        try:
            on_progress("Removing theme files…")
            for p in [
                Path.home() / ".local/share/plasma/desktoptheme/We10XOS",
                Path.home() / ".local/share/plasma/desktoptheme/We10XOS-dark",
                Path.home() / ".local/share/color-schemes/We10XOS.colors",
                Path.home() / ".local/share/color-schemes/We10XOSLight.colors",
                Path.home() / ".local/share/color-schemes/We10XOSDark.colors",
                Path.home() / ".local/share/aurorae/themes/We10XOS",
                Path.home() / ".local/share/aurorae/themes/We10XOSLight",
                Path.home() / ".local/share/fonts/win10-segoe",
            ]:
                if p.exists():
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)

            on_progress("Restoring previous settings…")
            msg = restore_kde_configs()
            if "No backup" in msg:
                reset_to_breeze_defaults()
            if MARKER.exists():
                MARKER.unlink(missing_ok=True)

            on_progress("Done. Log out/in to fully revert.")
            GLib.idle_add(lambda: on_done(True, f"Theme removed. {msg}\nLog out and back in to fully revert."))
        except Exception as e:
            GLib.idle_add(lambda: on_done(False, f"Remove failed: {e}"))

    threading.Thread(target=run, daemon=True).start()


class Win2LinuxWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Win2Linux")
        self.set_default_size(720, 580)
        self.settings = {}
        self._theme_busy = False
        self.load_settings()
        self.build_ui()

    def load_settings(self):
        self.settings = {
            'kbd_swap': SettingItem(
                'kbd_swap',
                'Swap Win+Space ↔ Alt+Shift',
                'Windows uses Win+Space for language switch. Linux default is Super+Space.\n'
                'This swaps them so Alt+Shift switches language (like Windows) and Win+Space does the reverse.\n\n'
                'Under the hood: modifies gsettings keys:\n'
                '  • org.gnome.desktop.wm.keybindings switch-input-source\n'
                '  • org.gnome.desktop.wm.keybindings switch-input-source-backward',
                lambda: self.get_kbd_state(),
                self.set_kbd_swap
            ),
            'kbd_layout': SettingItem(
                'kbd_layout',
                'Add US/IR Keyboard Layout',
                'Adds Persian (IR) and US keyboard layouts for quick switching.\n\n'
                'Under the hood: modifies dconf keys:\n'
                '  • org.gnome.desktop.input-sources sources\n'
                '  • org.gnome.desktop.input-sources mru-sources',
                lambda: self.get_layout_state(),
                self.set_kbd_layout
            ),
            'click_tap': SettingItem(
                'click_tap',
                'Tap to Click (Touchpad)',
                'Enables tapping on touchpad to click (Windows default behavior).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.peripherals.touchpad tap-to-click',
                lambda: self.get_tap_state(),
                self.set_tap_click
            ),
            'natural_scroll': SettingItem(
                'natural_scroll',
                'Natural Scrolling',
                'Makes scrolling direction match touchscreen/mobile (Windows default).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.peripherals.touchpad natural-scroll',
                lambda: self.get_natural_scroll_state(),
                self.set_natural_scroll
            ),
            'accel_profile': SettingItem(
                'accel_profile',
                'Mouse Acceleration: Flat (Windows-like)',
                'Disables mouse acceleration for consistent pointer movement like Windows.\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.peripherals.mouse accel-profile → "flat"',
                lambda: self.get_accel_state(),
                self.set_accel_profile
            ),
            'show_battery': SettingItem(
                'show_battery',
                'Show Battery Percentage',
                'Shows battery percentage in top panel (like Windows taskbar).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.interface show-battery-percentage',
                lambda: self.get_battery_state(),
                self.set_battery_percentage
            ),
            'clock_format': SettingItem(
                'clock_format',
                '12-Hour Clock Format',
                'Switches top panel clock to 12-hour format (Windows default).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.interface clock-format → "12h"',
                lambda: self.get_clock_state(),
                self.set_clock_format
            ),
            'minimize_click': SettingItem(
                'minimize_click',
                'Click Dock Icon to Minimize',
                'Clicking an app icon in the dock minimizes it (Windows taskbar behavior).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.shell.extensions.dash-to-dock click-action → "minimize"',
                lambda: self.get_minimize_state(),
                self.set_minimize_click
            ),
            'focus_hover': SettingItem(
                'focus_hover',
                'Focus Follows Mouse (Hover)',
                'Window focuses when mouse hovers over it (like Windows X-Mouse).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.wm.preferences focus-mode → "sloppy"',
                lambda: self.get_focus_state(),
                self.set_focus_hover
            ),
            'dock_to_bottom': SettingItem(
                'dock_to_bottom',
                'Move Dock to Bottom (Windows taskbar)',
                'Moves Dash to Dock to the bottom edge and keeps it always visible like the Windows taskbar.\n\n'
                'Under the hood: modifies gsettings keys:\n'
                '  • org.gnome.shell.extensions.dash-to-dock dock-position → "BOTTOM"\n'
                '  • org.gnome.shell.extensions.dash-to-dock dock-fixed → true\n'
                '  • org.gnome.shell.extensions.dash-to-dock autohide → false',
                lambda: self.get_dock_state(),
                self.set_dock_to_bottom
            ),
            'clock_show_date': SettingItem(
                'clock_show_date',
                'Show Date in Top Bar',
                'Windows taskbar always shows the date next to the clock.\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.interface clock-show-date → true',
                lambda: self.get_clock_date_state(),
                self.set_clock_date
            ),
            'disable_hot_corner': SettingItem(
                'disable_hot_corner',
                'Disable Hot Corner',
                'Windows has no hot corner — disable the top-left overview trigger.\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.interface enable-hot-corners → false',
                lambda: self.get_hot_corner_state(),
                self.set_hot_corner
            ),
            'center_windows': SettingItem(
                'center_windows',
                'Center New Windows',
                'Windows opens new windows centered on screen.\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.mutter center-new-windows → true',
                lambda: self.get_center_windows_state(),
                self.set_center_windows
            ),
            'detach_dialogs': SettingItem(
                'detach_dialogs',
                'Separate Dialog Windows',
                'Windows shows dialogs as separate windows — not attached to parent.\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.mutter attach-modal-dialogs → false',
                lambda: self.get_detach_dialogs_state(),
                self.set_detach_dialogs
            ),
            'window_buttons': SettingItem(
                'window_buttons',
                'Windows Window Buttons (Min/Max on Right)',
                'Windows has Minimize / Maximize / Close on the right side of the titlebar.\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.desktop.wm.preferences button-layout → ":minimize,maximize,close"',
                lambda: self.get_window_buttons_state(),
                self.set_window_buttons
            ),
            'double_click': SettingItem(
                'double_click',
                'Double-Click to Open Files',
                'Windows requires double-click to open files (GNOME default is single-click on some setups).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.nautilus.preferences click-policy → "double"',
                lambda: self.get_double_click_state(),
                self.set_double_click
            ),
            'edge_tiling': SettingItem(
                'edge_tiling',
                'Window Snap (Edge Tiling)',
                'Windows snaps windows when dragged to screen edges (Aero Snap).\n\n'
                'Under the hood: modifies gsettings key:\n'
                '  • org.gnome.mutter edge-tiling → true',
                lambda: self.get_edge_tiling_state(),
                self.set_edge_tiling
            ),
            'kde_windows_theme': SettingItem(
                'kde_windows_theme',
                'Windows 10 Theme (KDE Plasma)',
                'Dedoimedo guide: makes Plasma look like Windows 10.\n\n'
                'Installs (user-local, reversible):\n'
                '  • We10XOS-kde plasma theme + We10XOSLight colors (github.com/yeyushengfan258/We10XOS-kde)\n'
                '  • Segoe UI fonts → ~/.local/share/fonts/win10-segoe\n'
                '  • Breeze window decorations (Tiny borders; Breeze10 needs manual compile)\n'
                '  • Applies: We10XOSLight colors, Segoe UI 10pt, Breeze decorations\n'
                '  • Optional manual steps: Breeze Twilight global theme, KwinDE icons,\n'
                '    Tiled Menu & Present Windows Button from Discover, Win10 wallpaper\n'
                '  • Backup saved to ~/.config/win2linux/backups/ — Remove restores it\n'
                'Requires: KDE Plasma session. GNOME users can still use the toggles above.',
                theme_is_installed,
                self.install_kde_windows_theme
            ),
        }

    def run_gsettings(self, args):
        try:
            result = subprocess.run(['gsettings'] + args, capture_output=True, text=True, timeout=5)
            return result.stdout.strip(), result.returncode == 0
        except Exception:
            return "", False

    def get_kbd_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.wm.keybindings', 'switch-input-source'])
        return "'<Alt>Shift_L'" in out or "'<Alt>Shift_R'" in out

    def set_kbd_swap(self, active):
        if active:
            self.run_gsettings(['set', 'org.gnome.desktop.wm.keybindings', 'switch-input-source', "['<Alt>Shift_L']"])
            self.run_gsettings(['set', 'org.gnome.desktop.wm.keybindings', 'switch-input-source-backward', "['<Super>space']"])
        else:
            self.run_gsettings(['set', 'org.gnome.desktop.wm.keybindings', 'switch-input-source', "['<Super>space']"])
            self.run_gsettings(['set', 'org.gnome.desktop.wm.keybindings', 'switch-input-source-backward', "['<Shift><Super>space']"])

    def get_layout_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.input-sources', 'sources'])
        return '(\'xkb\', \'ir\')' in out

    def set_kbd_layout(self, active):
        if active:
            self.run_gsettings(['set', 'org.gnome.desktop.input-sources', 'sources', "[('xkb', 'us'), ('xkb', 'ir')]"])
            self.run_gsettings(['set', 'org.gnome.desktop.input-sources', 'mru-sources', "[('xkb', 'us'), ('xkb', 'ir')]"])
        else:
            self.run_gsettings(['set', 'org.gnome.desktop.input-sources', 'sources', "[('xkb', 'us')]"])
            self.run_gsettings(['set', 'org.gnome.desktop.input-sources', 'mru-sources', "[('xkb', 'us')]"])

    def get_tap_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.peripherals.touchpad', 'tap-to-click'])
        return out.lower() == 'true'

    def set_tap_click(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.peripherals.touchpad', 'tap-to-click', str(active).lower()])

    def get_natural_scroll_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.peripherals.touchpad', 'natural-scroll'])
        return out.lower() == 'true'

    def set_natural_scroll(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.peripherals.touchpad', 'natural-scroll', str(active).lower()])

    def get_accel_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.peripherals.mouse', 'accel-profile'])
        return out.strip() == "'flat'"

    def set_accel_profile(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.peripherals.mouse', 'accel-profile', "'flat'" if active else "'default'"])

    def get_battery_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.interface', 'show-battery-percentage'])
        return out.lower() == 'true'

    def set_battery_percentage(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.interface', 'show-battery-percentage', str(active).lower()])

    def get_clock_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.interface', 'clock-format'])
        return out.strip() == "'12h'"

    def set_clock_format(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.interface', 'clock-format', "'12h'" if active else "'24h'"])

    def get_minimize_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.shell.extensions.dash-to-dock', 'click-action'])
        return out.strip() == "'minimize'"

    def set_minimize_click(self, active):
        self.run_gsettings(['set', 'org.gnome.shell.extensions.dash-to-dock', 'click-action', "'minimize'" if active else "'previews'"])

    def get_focus_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.wm.preferences', 'focus-mode'])
        return out.strip() == "'sloppy'"

    def set_focus_hover(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.wm.preferences', 'focus-mode', "'sloppy'" if active else "'click'"])

    def get_dock_state(self):
        out, ok = self.run_gsettings(['get', 'org.gnome.shell.extensions.dash-to-dock', 'dock-position'])
        if not ok or "No such schema" in out or "No such key" in out:
            return False
        return out.strip().strip("'").upper() == "BOTTOM"

    def set_dock_to_bottom(self, active):
        pos = "'BOTTOM'" if active else "'LEFT'"
        ok = self.run_gsettings(['set', 'org.gnome.shell.extensions.dash-to-dock', 'dock-position', pos])[1]
        if ok:
            self.run_gsettings(['set', 'org.gnome.shell.extensions.dash-to-dock', 'dock-fixed', 'true' if active else 'false'])
            self.run_gsettings(['set', 'org.gnome.shell.extensions.dash-to-dock', 'autohide', 'false' if active else 'true'])

    def get_clock_date_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.interface', 'clock-show-date'])
        return out.lower() == 'true'

    def set_clock_date(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.interface', 'clock-show-date', str(active).lower()])

    def get_hot_corner_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.interface', 'enable-hot-corners'])
        return out.lower() == 'false'

    def set_hot_corner(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.interface', 'enable-hot-corners', 'false' if active else 'true'])

    def get_center_windows_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.mutter', 'center-new-windows'])
        return out.lower() == 'true'

    def set_center_windows(self, active):
        self.run_gsettings(['set', 'org.gnome.mutter', 'center-new-windows', str(active).lower()])

    def get_detach_dialogs_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.mutter', 'attach-modal-dialogs'])
        return out.lower() == 'false'

    def set_detach_dialogs(self, active):
        self.run_gsettings(['set', 'org.gnome.mutter', 'attach-modal-dialogs', 'false' if active else 'true'])

    def get_window_buttons_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.desktop.wm.preferences', 'button-layout'])
        return ':minimize,maximize,close' in out

    def set_window_buttons(self, active):
        self.run_gsettings(['set', 'org.gnome.desktop.wm.preferences', 'button-layout', "':minimize,maximize,close'" if active else "'appmenu:close'"])

    def get_double_click_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.nautilus.preferences', 'click-policy'])
        return out.strip().strip("'") == 'double'

    def set_double_click(self, active):
        self.run_gsettings(['set', 'org.gnome.nautilus.preferences', 'click-policy', "'double'" if active else "'single'"])

    def get_edge_tiling_state(self):
        out, _ = self.run_gsettings(['get', 'org.gnome.mutter', 'edge-tiling'])
        return out.lower() == 'true'

    def set_edge_tiling(self, active):
        self.run_gsettings(['set', 'org.gnome.mutter', 'edge-tiling', str(active).lower()])

    def install_kde_windows_theme(self, active):
        pass

    def do_install_theme(self):
        if self._theme_busy:
            return
        if theme_is_installed():
            self.show_toast("Theme already installed — use Remove to reinstall")
            return
        self._theme_busy = True
        self._set_theme_buttons_busy(True, "Installing…")
        def on_progress(msg):
            GLib.idle_add(lambda: self._theme_status.set_label(msg))
        def on_done(ok, msg):
            self._theme_busy = False
            self._set_theme_buttons_busy(False, None)
            self._refresh_theme_row()
            dlg = Adw.MessageDialog(transient_for=self, heading="Windows 10 Theme" if ok else "Install failed", body=msg)
            dlg.add_response("ok", "OK")
            dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED if ok else Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.connect("response", lambda d, r: d.close())
            dlg.present()
            self.show_toast("Theme installed — log out/in to fully apply" if ok else "Install failed")
        install_plasma_theme_threaded(on_progress, on_done)

    def do_remove_theme(self):
        if self._theme_busy:
            return
        if not theme_is_installed():
            self.show_toast("No Windows theme installed")
            return
        confirm = Adw.MessageDialog(transient_for=self, heading="Remove Windows 10 theme?", body="This removes We10XOS files, Segoe fonts, and restores your previous Plasma settings from backup. You'll need to log out/in.")
        confirm.add_response("cancel", "Cancel")
        confirm.add_response("remove", "Remove")
        confirm.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_close_response("cancel")
        def on_resp(d, r):
            d.close()
            if r != "remove":
                return
            self._theme_busy = True
            self._set_theme_buttons_busy(True, "Removing…")
            def on_progress(msg):
                GLib.idle_add(lambda: self._theme_status.set_label(msg))
            def on_done(ok, msg):
                self._theme_busy = False
                self._set_theme_buttons_busy(False, None)
                self._refresh_theme_row()
                dlg = Adw.MessageDialog(transient_for=self, heading="Theme removed" if ok else "Remove failed", body=msg)
                dlg.add_response("ok", "OK")
                dlg.connect("response", lambda dd, rr: dd.close())
                dlg.present()
                self.show_toast("Theme removed" if ok else "Remove failed")
            remove_plasma_theme_threaded(on_progress, on_done)
        confirm.connect("response", on_resp)
        confirm.present()

    def _set_theme_buttons_busy(self, busy, label):
        if hasattr(self, '_btn_install'):
            self._btn_install.set_sensitive(not busy)
            self._btn_remove.set_sensitive(not busy and theme_is_installed())
            if label:
                self._theme_status.set_label(label)

    def _refresh_theme_row(self):
        installed = theme_is_installed()
        if hasattr(self, '_theme_status'):
            self._theme_status.set_label("Installed — log out/in if needed" if installed else ("Plasma not detected — install will still copy files" if not is_plasma() else "Not installed"))
        if hasattr(self, '_btn_remove'):
            self._btn_remove.set_sensitive(not self._theme_busy and installed)
        if hasattr(self, '_btn_install'):
            self._btn_install.set_sensitive(not self._theme_busy and not installed)

    def build_ui(self):
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Win2Linux", subtitle="Windows-like settings for GNOME"))

        self.toast_overlay = Adw.ToastOverlay()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.toast_overlay.set_child(scrolled)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(720)
        clamp.set_tightening_threshold(600)
        scrolled.set_child(clamp)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        main_box.set_hexpand(True)
        clamp.set_child(main_box)

        welcome_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        welcome_box.add_css_class("card")
        welcome_box.set_margin_bottom(12)
        welcome_box.set_margin_top(4)
        icon = Gtk.Image.new_from_icon_name("preferences-desktop-symbolic")
        icon.set_pixel_size(48)
        icon.set_margin_top(12)
        welcome_box.append(icon)
        title = Gtk.Label(label="Welcome to Win2Linux")
        title.add_css_class("title-1")
        title.set_wrap(True)
        title.set_justify(Gtk.Justification.CENTER)
        title.set_halign(Gtk.Align.CENTER)
        title.set_hexpand(True)
        welcome_box.append(title)
        desc = Gtk.Label(label="Configure your GNOME desktop to feel familiar for Windows users. Each toggle shows exactly what system setting it changes.")
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        desc.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        desc.set_justify(Gtk.Justification.CENTER)
        desc.set_halign(Gtk.Align.CENTER)
        desc.set_hexpand(True)
        desc.set_margin_bottom(12)
        welcome_box.append(desc)
        main_box.append(welcome_box)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self.toast_overlay)
        self.set_content(toolbar_view)

        categories = [
            ("Keyboard & Language", ['kbd_swap', 'kbd_layout']),
            ("Touchpad & Mouse", ['click_tap', 'natural_scroll', 'accel_profile']),
            ("Panel & Appearance", ['show_battery', 'clock_format', 'clock_show_date', 'minimize_click', 'dock_to_bottom']),
            ("Window Behavior", ['window_buttons', 'center_windows', 'edge_tiling', 'detach_dialogs', 'focus_hover', 'disable_hot_corner']),
            ("Files", ['double_click']),
        ]

        for cat_name, keys in categories:
            cat_label = Gtk.Label(label=cat_name)
            cat_label.add_css_class("heading")
            cat_label.set_halign(Gtk.Align.START)
            cat_label.set_margin_top(16)
            cat_label.set_margin_bottom(8)
            main_box.append(cat_label)

            for key in keys:
                item = self.settings[key]
                row = self.create_setting_row(item)
                main_box.append(row)

                separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                separator.set_margin_top(4)
                separator.set_margin_bottom(4)
                main_box.append(separator)

        theme_label = Gtk.Label(label="Windows 10 Theme — KDE Plasma")
        theme_label.add_css_class("heading")
        theme_label.set_halign(Gtk.Align.START)
        theme_label.set_margin_top(16)
        theme_label.set_margin_bottom(8)
        main_box.append(theme_label)

        hint = Gtk.Label(label="Dedoimedo guide: We10XOS + Segoe UI + Breeze • User-local & reversible")
        hint.add_css_class("dim-label")
        hint.set_halign(Gtk.Align.START)
        hint.set_margin_bottom(8)
        main_box.append(hint)

        self._theme_row = self.create_theme_row()
        main_box.append(self._theme_row)
        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        main_box.append(Gtk.Label())

    def create_theme_row(self):
        item = self.settings['kde_windows_theme']
        row = Adw.ActionRow()
        row.set_title(item.label)
        row.set_subtitle("We10XOS + Segoe UI + Breeze — from dedoimedo.com/plasma-look-like-win10")

        self._theme_status = Gtk.Label(label="Installed" if theme_is_installed() else "Not installed")
        self._theme_status.add_css_class("dim-label")
        self._theme_status.set_valign(Gtk.Align.CENTER)
        row.add_suffix(self._theme_status)

        self._btn_install = Gtk.Button(label="Install")
        self._btn_install.add_css_class("suggested-action")
        self._btn_install.set_valign(Gtk.Align.CENTER)
        self._btn_install.set_tooltip_text("Download & apply Windows 10 theme (user-local)")
        self._btn_install.connect('clicked', lambda b: self.do_install_theme())
        row.add_suffix(self._btn_install)

        self._btn_remove = Gtk.Button(label="Remove")
        self._btn_remove.add_css_class("destructive-action")
        self._btn_remove.set_valign(Gtk.Align.CENTER)
        self._btn_remove.set_tooltip_text("Remove theme files and restore backup")
        self._btn_remove.connect('clicked', lambda b: self.do_remove_theme())
        row.add_suffix(self._btn_remove)

        info_btn = Gtk.Button()
        info_btn.set_icon_name("dialog-information-symbolic")
        info_btn.add_css_class("flat")
        info_btn.set_valign(Gtk.Align.CENTER)
        info_btn.set_tooltip_text("Show technical details")
        info_btn.connect('clicked', lambda b: self.show_details_dialog(item))
        row.add_suffix(info_btn)

        self._refresh_theme_row()
        return row

    def create_setting_row(self, item: SettingItem):
        row = Adw.ActionRow()
        row.set_title(item.label)
        row.set_subtitle(item.description.split('\n\n')[0] if '\n\n' in item.description else item.description)

        switch = Gtk.Switch()
        switch.set_active(item.current_fn())
        switch.set_valign(Gtk.Align.CENTER)
        item._active = switch.get_active()

        def on_toggle(switch, state):
            item.active = state
            item.apply_fn(state)
            self.show_toast(f"{'Enabled' if state else 'Disabled'}: {item.label}")
            return False

        switch.connect('state-set', on_toggle)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)

        info_btn = Gtk.Button()
        info_btn.set_icon_name("dialog-information-symbolic")
        info_btn.add_css_class("flat")
        info_btn.set_valign(Gtk.Align.CENTER)
        info_btn.set_tooltip_text("Show technical details")
        info_btn.connect('clicked', lambda b: self.show_details_dialog(item))
        row.add_suffix(info_btn)

        return row

    def show_details_dialog(self, item: SettingItem):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=item.label,
            body=item.description,
        )
        dialog.add_response("ok", "Got it")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()

    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        toast.set_timeout(2)
        self.toast_overlay.add_toast(toast)


class Win2LinuxApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.github.win2linux",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = Win2LinuxWindow(self)
        win.present()


def main():
    app = Win2LinuxApp()
    return app.run(None)


if __name__ == "__main__":
    main()
