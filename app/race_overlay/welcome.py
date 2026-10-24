"""The welcome guide: shown the first time the program starts (and from Home, 'Setup guide').
Two steps: pick what you want to use, then three things to do next."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QPushButton, QRadioButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from .constants import APP_NAME, APP_VERSION, IS_WINDOWS, PLATFORM, SCRIPT_DIR
from .setups import SETUPS
from .theme import Banner, build_theme_qss


class WelcomeDialog(QDialog):
    def __init__(self, ov):
        super().__init__(None)
        self.ov = ov
        self.chosen = None
        self.setWindowTitle(APP_NAME + " - Welcome")
        icon_path = os.path.join(SCRIPT_DIR, "icon.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(640, 640)
        self.setStyleSheet(build_theme_qss())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(12)
        lay.addWidget(Banner("Welcome", PLATFORM + " edition  ·  version %s" % APP_VERSION))
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)
        self.pages.addWidget(self.page_choose())
        self.pages.addWidget(self.page_done())

    # ----- page 1: what do you want to use? -----------------------------------------------
    def page_choose(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        intro = QLabel("<b>What do you want to show on your stream?</b><br>Pick one. It only switches the right "
                       "boards on, and you can change it any time in the Home tab.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        for st in SETUPS:
            b = QPushButton(st["title"])
            if st["key"] == "results":
                b.setObjectName("primary")
                b.setText(st["title"] + "  (most people)")
            b.clicked.connect(lambda _c=False, k=st["key"]: self.choose(k))
            v.addWidget(b)
            d = QLabel(st["blurb"])
            d.setWordWrap(True)
            d.setContentsMargins(10, 0, 10, 4)
            v.addWidget(d)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tower:"))
        self.rb_full = QRadioButton("Full tower")
        self.rb_small = QRadioButton("Small corner tower (top 5)")
        self.rb_full.setChecked(self.ov.s.get("tower_style") != "compact")
        self.rb_small.setChecked(self.ov.s.get("tower_style") == "compact")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_full)
        grp.addButton(self.rb_small)
        row.addWidget(self.rb_full)
        row.addWidget(self.rb_small)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        skip = QPushButton("Skip, I will set it up myself")
        skip.clicked.connect(self.skip)
        v.addWidget(skip)
        return w

    # ----- page 2: next steps ---------------------------------------------------------------
    def page_done(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        self.lbl_done = QLabel()
        self.lbl_done.setWordWrap(True)
        v.addWidget(self.lbl_done)
        steps = QLabel("<b>1.</b> Press <i>Show preview race</i> to see the tower with made-up umas.<br>"
                       "<b>2.</b> Press <i>Show overlay window</i> (Home tab) so OBS can see it.<br>"
                       "<b>3.</b> In OBS add a <i>Window Capture (" + "Windows 10 1903 and up" + ")</i> source and pick "
                       "<i>" + APP_NAME + "</i>. Boards are separate windows: add them the same way.<br>"
                       "<b>4.</b> Start Uma Musume. The overlay waits for it and shows a green dot when it is ready.")
        steps.setWordWrap(True)
        v.addWidget(steps)
        b1 = QPushButton("Show preview race")
        b1.setObjectName("primary")
        b1.clicked.connect(lambda: self.ov.set_preview(True))
        v.addWidget(b1)
        b2 = QPushButton("Open the settings")
        b2.clicked.connect(self.finish)
        v.addWidget(b2)
        v.addStretch(1)
        return w

    # ----- actions --------------------------------------------------------------------------
    def choose(self, key):
        style = "compact" if self.rb_small.isChecked() else "full"
        self.chosen = key
        self.ov.apply_setup(key, tower_style=style, rebuild=False)
        title = next(s["title"] for s in SETUPS if s["key"] == key)
        extra = ""
        if key == "match":
            extra = "<br>Next, open the <b>Draft</b> tab and type the players of both teams."
        elif key == "points":
            extra = "<br>You can read points from your own Google Sheet in the <b>Points</b> tab."
        self.lbl_done.setText("<b>Done: %s.</b>%s" % (title, extra))
        self.pages.setCurrentIndex(1)

    def skip(self):
        self.finish()

    def finish(self):
        self.close()
        tab = None
        if self.chosen:
            from .setups import get_setup
            tab = (get_setup(self.chosen) or {}).get("tab")
        self.ov.rebuild_settings(tab if tab in ("Draft", "Points") else "Home")
