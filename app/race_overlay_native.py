#!/usr/bin/env python3
"""Umamusume Race Overlay (Windows) - start file.

The program itself lives in the folder "race_overlay" next to this file.
Run it with:  python3 race_overlay_native.py   (or use start_auto.sh / the desktop icon)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from race_overlay.main import main
except ModuleNotFoundError:
    if not os.path.isdir(os.path.join(HERE, "race_overlay")):
        sys.exit("The folder 'race_overlay' is missing next to race_overlay_native.py.\n"
                 "This version needs it. Download the full zip from GitHub and copy the whole folder.")
    raise

def report_crash():
    """Windows has no terminal: write the problem to a file and show it in a message box."""
    import traceback
    text = traceback.format_exc()
    try:
        folder = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "race-overlay-native")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "crash.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if os.environ.get("CI"):          # a build machine must never wait for a click
            return
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "The overlay stopped with an error.\n\nPlease send this file:\n%s\n\n%s"
                                         % (path, text[-600:]), "Umamusume Race Overlay", 0x10)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        if sys.platform == "win32":
            report_crash()
        raise
