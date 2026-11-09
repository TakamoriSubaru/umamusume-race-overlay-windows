#!/usr/bin/env python3
"""Smoke test: starts the whole program without a screen (Qt "offscreen"), shows a made-up race, every settings
tab and every board, and checks that nothing crashes. No game, no real files, no real player names.

    python smoke_test.py

It is also run by the Windows build on GitHub, so a Windows problem shows up before a release."""
import os
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
home = tempfile.mkdtemp()
for var in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
    os.environ[var] = home
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = ["smoke_test", "--show", "--no-tray", "--no-game-link"]

from PyQt6.QtWidgets import QApplication            # noqa: E402
from race_overlay import main as mn                  # noqa: E402
from race_overlay import overlay_widget as ow        # noqa: E402
from race_overlay.constants import APP_NAME, PLATFORM  # noqa: E402

inst = []
orig_init = ow.OverlayWidget.__init__


def init(self, *a, **k):
    orig_init(self, *a, **k)
    inst.append(self)


ow.OverlayWidget.__init__ = init
result = {"ok": False}


def fake_exec():
    w = inst[0]
    app = QApplication.instance()

    def pump(sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            app.processEvents()
            w.tick()
            time.sleep(0.03)

    assert w.windowTitle() == APP_NAME, w.windowTitle()
    assert "(%s)" % PLATFORM in APP_NAME
    w.set_preview(True)                                  # a made-up race
    pump(1.0)
    assert w.horses, "the preview race has no umas"
    assert not w.grab().isNull()
    w.set_preview(False)

    w.open_settings()                                    # every settings tab
    d = w.dialog
    for i in range(d._tabs.count()):
        d._tabs.setCurrentIndex(i)
        pump(0.1)
        assert not d.grab().isNull(), d._tabs.tabText(i)

    w.show_welcome()                                     # the first-run guide and every setup
    pump(0.1)
    assert not w.welcome.grab().isNull()
    w.welcome.close()
    from race_overlay.setups import SETUPS
    for st in SETUPS:
        w.apply_setup(st["key"], rebuild=False)

    def tabs_now():
        return [w.dialog._tabs.tabText(i) for i in range(w.dialog._tabs.count()) if w.dialog._tabs.isTabVisible(i)]
    w.set_level("tower")                                 # Tower: Home, Look, People, Help only
    pump(0.3)
    assert tabs_now() == ["Home", "Look", "People", "Help"], tabs_now()
    w.set_level("advanced")                              # Advanced: results and luck board, no points
    pump(0.3)
    assert "Data" in tabs_now() and "Points" not in tabs_now(), tabs_now()
    assert w.s["results_board"] and w.s["luck_board"] and not w.s["scoring"]
    w.set_level("tournament")
    pump(0.3)
    assert "Points" in tabs_now(), tabs_now()
    for lv, n in (("tower", 5), ("advanced", 6), ("tournament", 8)):      # the tutorial of every version
        w.show_welcome()
        w.welcome.choose(lv)
        assert len(w.welcome.steps) == n, (lv, len(w.welcome.steps))
        for i in range(n):
            w.welcome.go(i)
            assert not w.welcome.grab().isNull()
        w.welcome.close()
    w.set_level("tournament", rebuild=False)

    entries, footer = w.sample_results()                 # every board, with made-up data
    w.board.set_pinned(True, (entries, footer))
    w.set_standings_pinned(True)
    w.set_luck_pinned(True)
    w.set_match_pinned(True)
    pump(0.5)
    for b in (w.board, w.standings, w.luck, w.mboard):
        assert not b.grab().isNull(), b.NAME
    for b in (w.board, w.standings, w.luck, w.mboard):
        b.set_pinned(False)

    from race_overlay.diagnostics import find_race_overlay, run_checks    # the Help tab checks
    find_race_overlay("")
    run_checks(w)

    print("smoke test OK (%s)" % PLATFORM)
    result["ok"] = True
    return 0


mn.QApplication.exec = lambda self=None: fake_exec()
try:
    mn.main()
except SystemExit:
    pass
sys.exit(0 if result["ok"] else 1)
