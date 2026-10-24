"""Command line options and program start."""

import argparse
import os
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from . import logbuf
from .config import load_config, save_config
from .constants import APP_NAME, APP_VERSION, IS_WINDOWS, SCRIPT_DIR
from .overlay_widget import OverlayWidget
from .sources import DemoThread, SseThread, WatchThread, choose_source


def main():
    ap = argparse.ArgumentParser(description=APP_NAME + " - race tower for OBS on Windows")
    ap.add_argument("--version", action="version", version=APP_NAME + " " + APP_VERSION)
    ap.add_argument("--server", default="http://127.0.0.1:5315", help="Race Overlay server URL")
    ap.add_argument("--demo", metavar="RACE.json", help="replay a saved horseACT race instead of live data")
    ap.add_argument("--watch", nargs="?", const="", default=None, metavar="FOLDER",
                    help="watch a folder of saved races and play the newest JSON automatically "
                         "(FOLDER is remembered; omit it next time to reuse the saved one)")
    ap.add_argument("--ignore-existing", action="store_true",
                    help="with --watch: do not play the race files that are already in the folder at startup")
    ap.add_argument("--game-linked", action="store_true",
                    help="only work while Uma Musume is running")
    ap.add_argument("--quit-with-game", action="store_true",
                    help="with --game-linked: close the overlay a few seconds after the game closes")
    ap.add_argument("--game-match", default="umamusume",
                    help="text to look for in running process names (default: umamusume)")
    ap.add_argument("--images-dir", default="",
                    help="folder for custom pictures (default: images/ next to this script)")
    ap.add_argument("--demo-speed", type=float, default=1.0, help="demo playback speed (default 1.0)")
    ap.add_argument("--thumbs-dir", default="", help="optional local folder with chara_stand_*.webp thumbnails")
    ap.add_argument("--chroma", action="store_true", help="solid green background for OBS Chroma Key")
    ap.add_argument("--chroma-color", default="#00ff00", help="chroma color (default #00ff00)")
    ap.add_argument("--transparent", action="store_true", help="transparent window (may not capture on all setups)")
    ap.add_argument("--frameless", action="store_true", help="no title bar (drag with left mouse, Esc closes)")
    ap.add_argument("--on-top", action="store_true", help="keep the window above others (already the default)")
    ap.add_argument("--bg", default=None, help="panel color (otherwise the Settings window value is used)")
    ap.add_argument("--bg-opacity", type=float, default=None, help="panel opacity 0-1 (otherwise the Settings window value)")
    ap.add_argument("--show", action="store_true", help="always show the overlay window at start")
    ap.add_argument("--no-tray", action="store_true", help="do not use a tray icon (overlay window always shown)")
    ap.add_argument("--hold", action="store_true", help="keep the finished tower on screen until the next race")
    ap.add_argument("--hide-after", type=float, default=3.0, help="seconds to keep the tower after the race ends")
    ap.add_argument("--no-autosize", action="store_true", help="do not resize the window to fit the horses")
    ap.add_argument("--reset-window", action="store_true", help="ignore the saved window position/size")
    ap.add_argument("--no-game-link", dest="game_linked", action="store_false",
                    help="Windows: work even when Uma Musume is not running (game-linked is the default there)")
    if IS_WINDOWS:
        ap.set_defaults(game_linked=True)      # nobody types options on Windows: wait for the game by default
    args = ap.parse_args()
    logbuf.install()          # remembers what the program prints, for the Help tab

    if IS_WINDOWS:                              # own taskbar icon and grouping, not "python"
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RaceOverlayNative.Umamusume")
        except Exception:
            pass
    app = QApplication(sys.argv)
    icon_path = os.path.join(SCRIPT_DIR, "icon.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    cfg = load_config()
    w = OverlayWidget(args, cfg)
    kind, folder = choose_source(args, w.s, cfg)
    if kind == "watch":
        if not folder and args.watch is not None and not w.s.get("source"):
            print("No folder saved yet. Use: --watch \"/path/to/Saved races\"")
            sys.exit(1)
        if folder:
            cfg["watch_dir"] = folder
            save_config(cfg)
        src = WatchThread(folder, args.demo_speed, args.ignore_existing,
                          args.game_match if args.game_linked else "", args.quit_with_game,
                          subfolders=bool(w.s.get("watch_subfolders", True)))
    elif kind == "demo":
        src = DemoThread(args.demo, args.demo_speed)
    else:
        src = SseThread(args.server, args.game_match if args.game_linked else "", args.quit_with_game)
    w.source_kind = kind
    w.attach(src)
    if IS_WINDOWS and kind == "live":
        from .winserver import ServerStarter      # starts Race Overlay's server once the game runs
        w.server_starter = ServerStarter(lambda k, d=None: w.s.get(k, d), args.game_match)
        w.server_starter.start()
    first_run = "settings" not in cfg
    if first_run:
        w.save_settings()
    app.setQuitOnLastWindowClosed(False)
    tray_ok = False if args.no_tray else w.setup_tray()
    hidden_until_race = w.auto_hide_active()
    if args.show or not tray_ok:
        w.show()
        w.s["show_overlay"] = True
    elif w.s.get("show_overlay") and not hidden_until_race:
        w.show()
    if tray_ok and first_run:
        QTimer.singleShot(500, w.show_welcome)           # the welcome guide: what do you want to use?
    elif tray_ok and w.s.get("open_menu", True):
        QTimer.singleShot(500, w.open_settings)
    if tray_ok and not w.isVisible():
        w.tray.showMessage(APP_NAME + " is running",
                           ("The overlay is hidden until a race starts, then it slides in. "
                            "Use 'Show overlay window' in the menu to place it.") if hidden_until_race else
                           "Click the icon for the menu. Press 'Show overlay window' to show the overlay.",
                           QSystemTrayIcon.MessageIcon.Information, 6000)
    code = app.exec()
    sys.exit(code)
