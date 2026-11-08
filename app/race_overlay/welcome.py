"""The welcome guide: shown the first time the program starts (and from Home, 'Setup guide and tutorial').
Step 1: which version do you want (Tower, Advanced, Tournament). Then a short tutorial for that version."""

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QRadioButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from . import constants as C
from .constants import APP_NAME, APP_VERSION, SCRIPT_DIR
from .theme import Banner, build_theme_qss

PLATFORM = getattr(C, "PLATFORM", "Linux")
WINDOWS = sys.platform == "win32"
CAPTURE = "Window Capture (Windows 10 1903 and up)" if WINDOWS else "Window Capture (Xcomposite)"

# the three versions: key, name, what you get, the ready-made setup that goes with it
LEVELS = (
    ("tower", "Tower", "Just the race tower. Only the Home, Look and People tabs. The easiest.", "tower"),
    ("advanced", "Advanced", "The tower, the results board and the skill luck board (who was lucky with skills). No points.",
     "advanced"),
    ("tournament", "Tournament", "Everything: results, luck and standings boards, points (also from your Google Sheet) "
                             "and the team match (draft).", "all"),
)


class WelcomeDialog(QDialog):
    def __init__(self, ov):
        super().__init__(None)
        self.ov = ov
        self.level = None
        self.steps = []
        self.step = 0
        self.setWindowTitle(APP_NAME + " - Welcome")
        icon_path = os.path.join(SCRIPT_DIR, "icon.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(600, 600)
        self.setStyleSheet(build_theme_qss())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(12)
        lay.addWidget(Banner("Welcome", PLATFORM + " edition  ·  version %s" % APP_VERSION))
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)
        self.pages.addWidget(self.page_choose())
        self.pages.addWidget(self.page_tutorial())

    # ----- page 1: which version? -----------------------------------------------------------
    def page_choose(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        intro = QLabel("<b>Which version do you want?</b><br>You can change it any time in the Home tab.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        for key, name, blurb, _setup in LEVELS:
            b = QPushButton(name)
            if key == "advanced":
                b.setObjectName("primary")
            b.setMinimumHeight(40)
            b.clicked.connect(lambda _c=False, k=key: self.choose(k))
            v.addWidget(b)
            d = QLabel(blurb)
            d.setWordWrap(True)
            d.setContentsMargins(10, 0, 10, 6)
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
        skip.clicked.connect(self.finish)
        v.addWidget(skip)
        return w

    # ----- page 2: the tutorial, one step at a time -----------------------------------------
    def page_tutorial(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color:#9aa;")
        v.addWidget(self.lbl_count)
        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet("font-size:20px; font-weight:bold;")
        self.lbl_title.setWordWrap(True)
        v.addWidget(self.lbl_title)
        self.lbl_text = QLabel()
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        v.addWidget(self.lbl_text)
        self.act_box = QVBoxLayout()
        v.addLayout(self.act_box)
        v.addStretch(1)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(line)
        nav = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.clicked.connect(lambda: self.go(self.step - 1))
        self.btn_next = QPushButton("Next")
        self.btn_next.setObjectName("primary")
        self.btn_next.clicked.connect(lambda: self.go(self.step + 1))
        nav.addWidget(self.btn_back)
        nav.addStretch(1)
        nav.addWidget(self.btn_next)
        v.addLayout(nav)
        return w

    def build_steps(self, level):
        ov = self.ov
        shot = lambda: (ov.set_preview(True))
        steps = [
            ("Start Uma Musume",
             "Start the game as you always do. The overlay waits for it, and a <b>green dot</b> in the Home tab "
             "says when it is ready.<br><br>In the game's graphics settings use <i>Windowed</i> or <i>Borderless "
             "windowed</i>. A true fullscreen game hides the overlay.", []),
            ("See the tower",
             "Press <b>Show preview race</b>: the tower runs with made-up umas, so you can see how it looks. "
             "Then press <b>Show overlay window</b> so OBS can see it.", [
                 ("Show preview race", shot), ("Show overlay window", lambda: ov.set_overlay_visible(True))]),
            ("Put it in OBS",
             "In OBS press <b>+</b> under <i>Sources</i>, choose <b>%s</b> and pick the window named<br>"
             "<b>%s</b>.<br><br>Move and resize the tower in your scene. It slides in when a race starts and "
             "slides out after it." % (CAPTURE, APP_NAME), []),
        ]
        if level in ("advanced", "tournament"):
            names = "<b>%s</b> and <b>%s</b>" % (C.RESULTS_NAME, C.LUCK_NAME)
            acts = [("Show results board (to place it)", lambda: ov.set_board_pinned(not ov.board.pinned)),
                    ("Show skill luck board (to place it)", lambda: ov.set_luck_pinned(not ov.luck.pinned))]
            if level == "tournament":
                names = "<b>%s</b>, <b>%s</b> and <b>%s</b>" % (C.RESULTS_NAME, C.LUCK_NAME, C.STANDINGS_NAME)
                acts.append(("Show standings board (to place it)", lambda: ov.set_standings_pinned(not ov.standings.pinned)))
            steps.append(("The boards",
                          "After a race the <b>results board</b> shows the places and times and the <b>skill luck board</b> "
                          "shows who was lucky with skills" + (", then the <b>standings board</b> adds up the points" if level == "tournament" else "")
                          + ".<br><br>Each board is its own window. Press a button to show it, drag it where you want it, "
                          "then press the button again to hide it. Add each one in OBS like the tower: " + names + ".", acts))
        if level == "tournament":
            steps.append(("Points and standings",
                          "Every race gives points (1st gets the most) and the standings board adds them up. You can also "
                          "read the points from your own Google Sheet and write the placings back to it.<br><br>"
                          "Everything is in the <b>Cup Score</b> tab.",
                          [("Open the Cup Score tab", lambda: self.open_tab("Cup Score"))]))
            steps.append(("Team match (draft)",
                          "Two teams, 4 / 2 / 1 points per race, first to 25. A match board shows the score. Type the "
                          "players of both teams in the <b>Draft</b> tab.",
                          [("Open the Draft tab", lambda: self.open_tab("Draft"))]))
        steps.append(("Make it yours",
                      "The <b>Look</b> tab changes colours, fonts, the size of the tower and the pictures. In the "
                      "<b>People</b> tab you add pictures for your players and umas.",
                      [("Open the Look tab", lambda: self.open_tab("Look")), ("Open the People tab", lambda: self.open_tab("People"))]))
        steps.append(("You are ready",
                      "That is all. To see this tutorial again or to change the version, open the <b>Home</b> tab and press "
                      "<i>Setup guide and tutorial</i>.", []))
        return steps

    def go(self, i):
        if i < 0:
            self.pages.setCurrentIndex(0)
            return
        if i >= len(self.steps):
            self.finish()
            return
        self.step = i
        title, text, acts = self.steps[i]
        self.lbl_count.setText("Step %d of %d" % (i + 1, len(self.steps)))
        self.lbl_title.setText(title)
        self.lbl_text.setText(text)
        while self.act_box.count():
            item = self.act_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for label, fn in acts:
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, f=fn: f())
            self.act_box.addWidget(b)
        self.btn_next.setText("Finish" if i == len(self.steps) - 1 else "Next")

    # ----- actions --------------------------------------------------------------------------
    def choose(self, level):
        style = "compact" if self.rb_small.isChecked() else "full"
        self.level = level
        setup = next(s for k, _n, _b, s in LEVELS if k == level)
        self.ov.set_level(level, apply=False, rebuild=False)
        self.ov.apply_setup(setup, tower_style=style, rebuild=False)
        self.steps = self.build_steps(level)
        self.pages.setCurrentIndex(1)
        self.go(0)

    def open_tab(self, name):
        self.ov.open_settings()
        self.ov.dialog.show_tab(name)

    def finish(self):
        self.close()
        self.ov.rebuild_settings("Home")
