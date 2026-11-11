"""The Menu / Settings window."""

import json
import os
import re
from PyQt6.QtCore import QSize, QTimer, QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .constants import (ANALYSIS_NAME, APP_NAME, APP_VERSION, FROZEN, IS_WINDOWS, LUCK_NAME, MATCH_NAME, PLATFORM, RELEASES_URL, RESULTS_NAME,
                        SCRIPT_DIR, STANDINGS_NAME, STATE_COLORS, THEME_PRESETS)
from . import logbuf
from .diagnostics import LOG_FILES, read_tail, run_checks
from .setups import SETUPS, current_setup
from .theme import Banner, THEME, build_theme_qss
from .updater import (
    Job,
    is_update_path,
    check_update_files,
    download_update,
    fetch_manifest,
    install_update,
    read_update_file,
    version_tuple,
)
from .sheets import VIEWS, is_auto
from .images import export_pictures, find_file_ci, import_pictures
from .util import open_folder


SLIDE_CHOICES = (("auto", "Auto: the side the window is on"),
                 ("left", "Always from the left"),
                 ("right", "Always from the right"),
                 ("off", "No sliding (fade in)"))


class _NameItem(QTableWidgetItem):
    """A table cell that sorts A-Z without caring about capital letters."""

    def __lt__(self, other):
        return self.text().casefold() < other.text().casefold()


class Collapsible(QWidget):
    """A folded section: a title you click to open it. Keeps the less used settings out of the way."""

    def __init__(self, title, open_=False, on_toggle=None):
        super().__init__()
        self._title = title
        self._on_toggle = on_toggle
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.btn = QPushButton()
        self.btn.setObjectName("fold")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.set_open(not self.body.isVisible(), True))
        lay.addWidget(self.btn)
        self.body = QWidget()
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(6, 0, 0, 0)
        lay.addWidget(self.body)
        self.set_open(open_)

    def set_open(self, on, user=False):
        self.body.setVisible(bool(on))
        self.btn.setText(("\u25be  " if on else "\u25b8  ") + self._title)
        if user and self._on_toggle:
            self._on_toggle(bool(on))

    def form(self):
        f = QFormLayout()
        self.body_l.addLayout(f)
        return f


class SettingsDialog(QDialog):
    def __init__(self, ov):
        super().__init__(None)
        self.ov = ov
        self.setWindowTitle(APP_NAME + " - Menu")
        icon_path = os.path.join(SCRIPT_DIR, "icon.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        level = ov.level()
        simple = level == "tower"                  # the Tower version is a small window
        limited = level != "tournament"              # Tower and Advanced: no points, standings, match
        self.resize(500, 520) if simple else self.resize(720, 780)
        self.setStyleSheet(build_theme_qss())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(8 if simple else 12)
        lay.addWidget(Banner("Race Overlay", PLATFORM + " edition  ·  version %s  ·  settings" % APP_VERSION))
        tabs = QTabWidget()
        tabs.setDocumentMode(False)
        lay.addWidget(tabs)
        self.count_job = None
        self._count_again = False

        # ---- Home tab (what most people need: status, show / preview, place the boards)
        mt = QWidget()
        mv = QVBoxLayout(mt)
        self.lbl_state = QLabel()
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setStyleSheet("font-size:15px;")
        mv.addWidget(self.lbl_state)
        from .pointsui import Flow, ModeCard, StepCard
        vrow = QHBoxLayout()
        self.level_cards = {}
        for key, icon, title, sub in (("tower", "tower", "Tower", "Just the tower"),
                                      ("advanced", "boards", "Advanced", "Tower + results + luck"),
                                      ("tournament", "cup", "Tournament", "Everything")):
            card = ModeCard(icon, title, sub)
            card.setChecked(key == level)
            card.clicked.connect(lambda _c=False, k=key: ov.set_level(k))
            self.level_cards[key] = card
            vrow.addWidget(card)
        mv.addLayout(vrow)

        sbx = QGroupBox("Setup")
        sbl = QVBoxLayout(sbx)
        srow = QHBoxLayout()
        self.cmb_setup = QComboBox()
        for st in SETUPS:
            self.cmb_setup.addItem(st["title"], st["key"])
        self.cmb_setup.addItem("Custom (changed by hand)", "")
        cur = current_setup(ov.s)
        self.cmb_setup.setCurrentIndex(self.cmb_setup.findData(cur or ""))
        self.cmb_setup.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_setup.setMinimumContentsLength(10)
        self.btn_setup = QPushButton("Use this setup")
        self.btn_setup.setObjectName("primary")
        self.btn_setup.setMinimumWidth(10)
        srow.addWidget(self.cmb_setup, 1)
        srow.addWidget(self.btn_setup)
        sbl.addLayout(srow)
        self.lbl_setup = QLabel()
        self.lbl_setup.setWordWrap(True)
        sbl.addWidget(self.lbl_setup)

        def on_setup_changed(_i=None):
            key = self.cmb_setup.currentData()
            st = next((x for x in SETUPS if x["key"] == key), None)
            self.btn_setup.setEnabled(st is not None)
            self.lbl_setup.setText(st["blurb"] if st else "You changed boards or options by hand. Pick a setup "
                                   "to switch to a ready-made one.")
        self.cmb_setup.currentIndexChanged.connect(on_setup_changed)
        self.btn_setup.clicked.connect(lambda: ov.apply_setup(self.cmb_setup.currentData()))
        on_setup_changed()
        mv.addWidget(sbx)
        sbx.setVisible(not limited)

        qs = Collapsible("How to start (3 steps)", open_=bool(ov.s.get("quick_start_open", True)),
                         on_toggle=lambda on: ov.set_setting("quick_start_open", on))
        qrow = QHBoxLayout()
        for n, kind, title, sub in ((1, "game", "Start Uma Musume", "a green dot shows when ready"),
                                    (2, "screen", "Show the overlay", "use the button below"),
                                    (3, "capture", "Add it in OBS", "Window Capture, pick the overlay window")):
            qrow.addWidget(StepCard(n, kind, title, sub))
        qs.body_l.addLayout(qrow)

        def copy_name():
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(APP_NAME)
            bcopy.setText("Copied: " + APP_NAME)
        bcopy = QPushButton("Copy the window name for OBS")
        bcopy.setToolTip(APP_NAME)
        bcopy.clicked.connect(copy_name)
        qs.body_l.addWidget(bcopy)
        mv.addWidget(qs)

        row_b = QHBoxLayout()
        self.btn_show = QPushButton("Show overlay window")
        self.btn_show.setObjectName("primary")
        self.btn_show.clicked.connect(lambda: ov.set_overlay_visible(not ov.window_wanted()))
        self.btn_prev2 = QPushButton("Show preview race")
        self.btn_prev2.clicked.connect(lambda: ov.set_preview(not ov.preview))
        row_b.addWidget(self.btn_show)
        row_b.addWidget(self.btn_prev2)
        mv.addLayout(row_b)
        self.note_show = QLabel()
        self.note_show.setWordWrap(True)
        mv.addWidget(self.note_show)

        bx = QGroupBox("Boards")
        bx.setStyleSheet("QGroupBox { margin-top: 4px; padding-top: 12px; } QGroupBox::title { height: 0; padding: 0; background: transparent; }")
        bxl = QVBoxLayout(bx)
        bxt = QLabel("Put each board where you want it on the stream, then press the button again to hide it.")
        bxt.setWordWrap(True)
        bxl.addWidget(bxt)
        row_c = QHBoxLayout()
        self.btn_board = QPushButton("Show results board (to place it)")
        self.btn_board.clicked.connect(lambda: ov.set_board_pinned(not ov.board.pinned))
        self.btn_stand = QPushButton("Show standings board (to place it)")
        self.btn_stand.clicked.connect(lambda: ov.set_standings_pinned(not ov.standings.pinned))
        row_c.addWidget(self.btn_board)
        row_c.addWidget(self.btn_stand)
        bxl.addLayout(row_c)
        self.btn_luck = QPushButton("Show skill luck board (to place it)")
        self.btn_luck.clicked.connect(lambda: ov.set_luck_pinned(not ov.luck.pinned))
        bxl.addWidget(self.btn_luck)
        self.btn_match = QPushButton("Show match board (to place it)")
        self.btn_match.clicked.connect(lambda: ov.set_match_pinned(not ov.mboard.pinned))
        bxl.addWidget(self.btn_match)
        self.btn_test = QPushButton("Replay a saved race (test, no game needed)...")
        self.btn_test.clicked.connect(lambda: ov.test_replay())
        bxl.addWidget(self.btn_test)
        place = Collapsible("Place the boards on screen (before you stream)")
        place.body_l.addWidget(bx)
        mv.addWidget(place)
        place.setVisible(not simple)
        if limited:                                  # Advanced has the results and luck board only
            for btn in (self.btn_stand, self.btn_match):
                btn.setVisible(False)

        more = Collapsible("More: start-up, picture folders, updates")
        mm = more.body_l
        bg = QPushButton("Setup guide and tutorial...")
        bg.setToolTip("Choose Tower, Advanced or Tournament and go through the steps.")
        bg.clicked.connect(ov.show_welcome)
        mm.addWidget(bg)
        self.cb_menu = QCheckBox("Open this menu when the program starts")
        self.cb_menu.setChecked(bool(ov.s.get("open_menu", True)))
        self.cb_menu.toggled.connect(lambda on: ov.set_setting("open_menu", on))
        mm.addWidget(self.cb_menu)
        self.cb_server = QCheckBox("Quitting the overlay also closes the Race Overlay server")
        self.cb_server.setChecked(bool(ov.s.get("stop_server", True)))
        self.cb_server.toggled.connect(lambda on: ov.set_setting("stop_server", on))
        self.cb_server.setToolTip("Only the server that this program (or the start script) started is closed.")
        mm.addWidget(self.cb_server)
        self.cb_autoupd = QCheckBox("Tell me when a new version is out")
        self.cb_autoupd.setChecked(bool(ov.s.get("auto_update_check", True)))
        self.cb_autoupd.toggled.connect(lambda on: ov.set_setting("auto_update_check", on))
        self.cb_autoupd.setToolTip("Looks on GitHub a few seconds after the program starts (and every 6 hours). If there is a new version a window asks if you want it; you choose.")
        mm.addWidget(self.cb_autoupd)

        if IS_WINDOWS:
            rbx = QGroupBox("Race Overlay (live race data)")
            rl = QVBoxLayout(rbx)
            cb_ro = QCheckBox("Start Race Overlay's server when Uma Musume runs")
            cb_ro.setChecked(bool(ov.s.get("start_race_overlay", True)))
            cb_ro.toggled.connect(lambda on: ov.set_setting("start_race_overlay", on))
            rl.addWidget(cb_ro)
            rl.addWidget(QLabel("Folder with <i>Race Overlay.exe</i> (empty = look for it in Documents, Downloads, Desktop):"))
            rrow = QHBoxLayout()
            self.ed_ro = QLineEdit(ov.s.get("race_overlay_dir", ""))
            self.ed_ro.setPlaceholderText("C:\\Users\\you\\Documents\\Race Overlay")
            self.ed_ro.setMinimumWidth(100)
            self.lbl_ro = QLabel()
            self.lbl_ro.setWordWrap(True)

            def ro_apply():
                from .diagnostics import find_race_overlay
                ov.set_setting("race_overlay_dir", self.ed_ro.text().strip())
                found = find_race_overlay(self.ed_ro.text().strip())
                self.lbl_ro.setText("Found: %s (restart the overlay to use a new folder)" % found if found
                                    else "Race Overlay.exe not found there, so the overlay gets no live race data.")

            def ro_choose():
                d = QFileDialog.getExistingDirectory(self, "Folder with Race Overlay.exe",
                                                     self.ed_ro.text().strip() or os.path.expanduser("~"))
                if d:
                    self.ed_ro.setText(d)
                    ro_apply()
            self.ed_ro.editingFinished.connect(ro_apply)
            bro = QPushButton("Choose...")
            bro.clicked.connect(ro_choose)
            rrow.addWidget(self.ed_ro, 1)
            rrow.addWidget(bro)
            rl.addLayout(rrow)
            rl.addWidget(self.lbl_ro)
            ro_apply_label = ro_apply
            QTimer.singleShot(0, ro_apply_label)
            mm.addWidget(rbx)

        box = QGroupBox("Where to put the pictures")
        bl = QVBoxLayout(box)
        for title, path, hint in (
                ("Uma faces", ov.thumbs.uma,
                 "Easiest: use the People tab. Or name the file with the card id, chara id or uma name, "
                 "e.g. 100101.png or Special Week.png. Without a picture of yours the face from Race Overlay is used."),
                ("Player pictures", ov.thumbs.players,
                 "Easiest: use the People tab. Or name the file after the trainer, e.g. Takamori.png")):
            lab = QLabel("<b>%s</b><br>%s<br><i>%s</i>" % (title, path, hint))
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            bl.addWidget(lab)
            bo = QPushButton("Open folder")
            bo.clicked.connect(lambda _=False, pth=path: open_folder(pth))
            bl.addWidget(bo)
        mm.addWidget(box)

        ubox = QGroupBox("Updates  (current version %s)" % APP_VERSION)
        ul = QVBoxLayout(ubox)
        self.lbl_update = QLabel("Update from a file you downloaded, or check online if you have an update link.")
        self.lbl_update.setWordWrap(True)
        ul.addWidget(self.lbl_update)
        bu = QPushButton("Update from file...  (.zip or race_overlay_native.py)")
        bu.clicked.connect(self.update_from_file)
        ul.addWidget(bu)
        ur = QHBoxLayout()
        self.ed_url = QLineEdit(ov.s.get("update_url", ""))
        self.ed_url.setPlaceholderText("Update link (https://.../latest.json)")
        self.ed_url.editingFinished.connect(lambda: ov.set_setting("update_url", self.ed_url.text().strip()))
        self.btn_check = QPushButton("Check online")
        self.btn_check.clicked.connect(self.check_online)
        ur.addWidget(self.ed_url, 1)
        ur.addWidget(self.btn_check)
        ul.addLayout(ur)
        self.btn_install = QPushButton("Install the new version")
        self.btn_install.setVisible(False)
        self.btn_install.clicked.connect(self.install_online)
        ul.addWidget(self.btn_install)
        mm.addWidget(ubox)
        self.pending = None
        self.job = None
        mv.addWidget(more)
        if simple:
            mv.setSpacing(6)

        mv.addStretch(1)
        bq = QPushButton("Quit the overlay program")
        bq.setObjectName("danger")
        bq.clicked.connect(ov.quit_app)
        mv.addWidget(bq)
        tabs.addTab(self.scrolled(mt), "Home")

        # ---- Data tab (the skills spreadsheet, and the server)
        rt = QWidget()
        rv = QVBoxLayout(rt)
        kbox = QGroupBox("Race Overlay server")
        kl = QVBoxLayout(kbox)
        kn = QLabel("Live races come from the Race Overlay server (the <i>Server Files</i> folder). It only works while "
                    "Uma Musume is running. To test without the game use <i>Show preview race</i> in the Home tab.")
        kn.setWordWrap(True)
        kl.addWidget(kn)
        rv.addWidget(kbox)
        self._data_layout = rv                      # the skills box is added here (built with the Points tab)
        rv.addStretch(1)
        tabs.addTab(self.scrolled(rt), "Data")

        # ---- Look tab
        look = QWidget()                  # Look: pictures, colours, text
        lv = QVBoxLayout(look)
        g_sets = QGroupBox("Colour sets (click one)")
        self.grid_sets = QGridLayout(g_sets)
        lv.addWidget(g_sets)
        g_cols = QGroupBox("Colours, text and pictures")
        lg = QVBoxLayout(g_cols)
        f = QFormLayout()
        lg.addLayout(f)
        fc = QFormLayout()                # colours
        lg.addLayout(fc)
        lv.addWidget(g_cols)
        ff = QFormLayout()                # fonts and racer text: folded away
        fold_font = Collapsible("Fonts and racer text")
        fold_font.body_l.addLayout(ff)
        lv.addWidget(fold_font)
        g_pod = QGroupBox("Podium, picture shape and rows")
        fx = QFormLayout(g_pod)
        fold_pod = Collapsible("More colours: podium, picture shape, rows")
        g_pod.setStyleSheet("QGroupBox { border: none; margin-top: 0; padding-top: 0; } QGroupBox::title { height: 0; padding: 0; background: transparent; }")
        fold_pod.body_l.addWidget(g_pod)
        lv.addWidget(fold_pod)
        g_my = QGroupBox("My look")
        gmv = QHBoxLayout(g_my)
        lv.addWidget(g_my)
        lv.addStretch(1)
        tower = QWidget()                 # Tower: the race window itself
        tv = QVBoxLayout(tower)
        ft = QFormLayout()
        tv.addLayout(ft)
        tv.addStretch(1)
        boards = QWidget()                # Boards: results board and skill luck board
        bv = QVBoxLayout(boards)
        gres = QGroupBox("Results board")
        fr = QFormLayout(gres)
        bv.addWidget(gres)
        gluck = QGroupBox("Skill luck board")
        fl = QFormLayout(gluck)
        bv.addWidget(gluck)
        bv.addStretch(1)
        s = ov.s

        self.cb_top = QCheckBox("Keep the overlay above all other windows")
        self.cb_top.setChecked(bool(s.get("on_top", True)))
        self.cb_top.toggled.connect(lambda on: ov.set_setting("on_top", on))
        ft.addRow("Always on top", self.cb_top)

        self.cb_hide = QCheckBox("Hide the window until a race starts")
        self.cb_hide.setChecked(bool(s.get("auto_hide", True)))
        self.cb_hide.toggled.connect(lambda on: ov.set_setting("auto_hide", on))
        self.cb_hide.setToolTip("The window is hidden when no race runs and shows (without taking focus from the game)\nwhen a race starts. Use 'Show overlay window' in the Home tab to place it.")
        ft.addRow("Before the race", self.cb_hide)

        self.cmb_slide = QComboBox()
        for _v, text in SLIDE_CHOICES:
            self.cmb_slide.addItem(text)
        self.cmb_slide.setCurrentIndex(next((i for i, (v, _t) in enumerate(SLIDE_CHOICES)
                                             if v == s.get("slide", "auto")), 0))
        self.cmb_slide.activated.connect(lambda i: ov.set_setting("slide", SLIDE_CHOICES[i][0]))
        ft.addRow("Slides in from", self.cmb_slide)

        self.cb_title = QCheckBox("Show the window title bar")
        self.cb_title.setChecked(bool(s.get("title_bar", False)))
        self.cb_title.toggled.connect(lambda on: ov.set_setting("title_bar", on))
        self.cb_title.setToolTip("Off = clean window: drag to move it, pull the edges to resize it.")
        ft.addRow("Title bar", self.cb_title)

        self.cmb_names = QComboBox()                      # what the rows say
        self._name_modes = [("both", "Trainer and uma name"), ("trainer", "Trainer name only"),
                            ("uma", "Uma name only")]
        self.cmb_names.addItems([t for _, t in self._name_modes])
        self.cmb_names.setCurrentIndex(next((i for i, (m, _t) in enumerate(self._name_modes)
                                             if m == s.get("names", "both")), 0))
        self.cmb_names.activated.connect(lambda i: ov.set_setting("names", self._name_modes[i][0]))
        self.cmb_names.setToolTip("Used in the tower, the results board and the skill luck board.")
        ft.addRow("Names shown", self.cmb_names)

        self.cmb_avatar = QComboBox()
        self._pic_modes = [m for m, _ in ov.PICTURE_CHOICES]
        self.cmb_avatar.addItems([t for _, t in ov.PICTURE_CHOICES])
        self.cmb_avatar.setCurrentIndex(self._pic_modes.index(ov.picture_mode()))
        self.cmb_avatar.currentIndexChanged.connect(
            lambda i: ov.set_setting("pictures", self._pic_modes[i]))
        f.addRow("Pictures", self.cmb_avatar)

        self.chips = {}
        for n, (name, preset) in enumerate(THEME_PRESETS.items()):
            chip = QPushButton(name.replace(" (default)", ""))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip("Sets the background, text and accent colours in one go. You can still change each colour below.")
            chip.setStyleSheet("QPushButton{background-color:%s;color:%s;border:2px solid %s;border-radius:9px;"
                               "padding:6px 4px;font-weight:700;}QPushButton:hover{border-color:%s;}"
                               % (preset["bg"], preset["text_color"], preset["accent"], preset["text_color"]))
            chip.clicked.connect(lambda _=False, nm=name: self.on_theme(nm))
            self.grid_sets.addWidget(chip, n // 3, n % 3)
            self.chips[name] = chip

        self.pod_btns = []
        for k, label in enumerate(("1st place colour", "2nd place colour", "3rd place colour")):
            b = QPushButton()
            key = "podium_%d" % (k + 1)
            b.clicked.connect(lambda _=False, key=key, b=b: self.pick(key, b))
            fx.addRow(label, b)
            self.pod_btns.append((key, b))
        self._shapes = [("circle", "Circle"), ("rounded", "Rounded square"), ("square", "Square")]
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems([t for _, t in self._shapes])
        self.cmb_shape.setCurrentIndex(next((i for i, (m, _t) in enumerate(self._shapes)
                                             if m == s.get("picture_shape", "circle")), 0))
        self.cmb_shape.activated.connect(lambda i: ov.set_setting("picture_shape", self._shapes[i][0]))
        fx.addRow("Picture shape", self.cmb_shape)
        self._rowstyles = [("default", "Lines (top 3 underlined)"), ("cards", "Cards"), ("plain", "Plain")]
        self.cmb_rowstyle = QComboBox()
        self.cmb_rowstyle.addItems([t for _, t in self._rowstyles])
        self.cmb_rowstyle.setCurrentIndex(next((i for i, (m, _t) in enumerate(self._rowstyles)
                                                if m == s.get("row_style", "default")), 0))
        self.cmb_rowstyle.activated.connect(lambda i: ov.set_setting("row_style", self._rowstyles[i][0]))
        fx.addRow("Tower row style", self.cmb_rowstyle)

        btn_save = QPushButton("Save my look...")
        btn_save.setToolTip("Saves colours, text, pictures and row style to a small file you can share or keep.")
        btn_save.clicked.connect(self.save_look)
        btn_load = QPushButton("Load a look...")
        btn_load.clicked.connect(self.load_look)
        gmv.addWidget(btn_save)
        gmv.addWidget(btn_load)

        self.btn_bg = QPushButton()
        self.btn_bg.clicked.connect(lambda: self.pick("bg", self.btn_bg))
        fc.addRow("Background colour", self.btn_bg)

        self.sl_op = QSlider(Qt.Orientation.Horizontal)
        self.sl_op.setRange(0, 100)
        self.sl_op.setValue(int(float(s.get("bg_opacity", 1.0)) * 100))
        self.sl_op.valueChanged.connect(lambda v: ov.set_setting("bg_opacity", v / 100.0))
        fc.addRow("Background opacity\n(--transparent / --chroma)", self.sl_op)

        self.btn_tc = QPushButton()
        self.btn_tc.clicked.connect(lambda: self.pick("text_color", self.btn_tc))
        fc.addRow("Text colour", self.btn_tc)

        self.btn_sc = QPushButton()
        self.btn_sc.clicked.connect(lambda: self.pick("sub_color", self.btn_sc))
        fc.addRow("Small text colour", self.btn_sc)

        self.btn_ac = QPushButton()
        self.btn_ac.clicked.connect(lambda: self.pick("accent", self.btn_ac))
        fc.addRow("Accent colour\n(results board)", self.btn_ac)

        row = QHBoxLayout()
        self.sl_size = QSlider(Qt.Orientation.Horizontal)
        self.sl_size.setRange(60, 140)
        self.sl_size.setValue(int(float(s.get("text_scale", 1.0)) * 100))
        self.lbl_size = QLabel()
        self.sl_size.valueChanged.connect(self.on_size)
        row.addWidget(self.sl_size)
        row.addWidget(self.lbl_size)
        f.addRow("Text size", row)

        self.lbl_fontprev = QLabel("Preview:  1st  Inari One  +0.41  12:34.5")
        self.lbl_fontprev.setStyleSheet("padding:6px 10px; border:1px solid #3a3a5a; border-radius:8px;")
        self.cmb_font = QComboBox()
        self.cmb_font.setMaxVisibleItems(25)
        self.fill_fonts(s.get("font", ""))
        self.cmb_font.activated.connect(self.on_font)
        self.cmb_font.setToolTip("A short list of common fonts. \"More fonts...\" shows every font on this computer.")
        ff.addRow("Font", self.cmb_font)
        ff.addRow("", self.lbl_fontprev)

        # the header and the racers can have their own font, size and colour
        self.role_cmb, self.role_btn = {}, {}
        for key, label in (("header_font", "Header font"), ("racer_font", "Racer font")):
            cmb = QComboBox()
            cmb.setMaxVisibleItems(25)
            cmb.activated.connect(lambda _i, k=key: self.on_role_font(k))
            cmb.setToolTip("The font of the tower header (track info) or of the racer names. \"Same as the main font\" follows Font above.")
            self.role_cmb[key] = cmb
            self.fill_role_font(key, s.get(key, ""))
            ff.addRow(label, cmb)
        self.sl_racer = QSlider(Qt.Orientation.Horizontal)
        self.sl_racer.setRange(60, 160)
        self.sl_racer.setValue(int(float(s.get("racer_scale", 1.0)) * 100))
        self.lbl_racer = QLabel("%d%%" % self.sl_racer.value())
        self.sl_racer.valueChanged.connect(self.on_racer_size)
        rrow = QHBoxLayout()
        rrow.addWidget(self.sl_racer)
        rrow.addWidget(self.lbl_racer)
        ff.addRow("Racer text size", rrow)
        for key, label in (("header_color", "Header colour"), ("racer_color", "Racer colour")):
            b = QPushButton()
            b.clicked.connect(lambda _c=False, k=key: self.pick_role(k))
            rb = QPushButton("Same as text colour")
            rb.clicked.connect(lambda _c=False, k=key: self.pick_role(k, reset=True))
            self.role_btn[key] = b
            crow = QHBoxLayout()
            crow.addWidget(b, 1)
            crow.addWidget(rb)
            ff.addRow(label, crow)
            self.swatch_role(key)

        self.cb_arrows = QCheckBox("Show an arrow when a uma gains or loses a place")
        self.cb_arrows.setChecked(bool(s.get("rank_arrows", True)))
        self.cb_arrows.toggled.connect(lambda on: ov.set_setting("rank_arrows", on))
        ft.addRow("Position arrows", self.cb_arrows)

        self.sp_rows = QSpinBox()
        self.sp_rows.setRange(0, 18)
        self.sp_rows.setSpecialValueText("All of them")
        self.sp_rows.setSuffix(" rows")
        self.sp_rows.setValue(int(s.get("max_rows", 0) or 0))
        self.sp_rows.valueChanged.connect(lambda v: ov.set_setting("max_rows", int(v)))
        self.sp_rows.setToolTip("Show only the first places in the tower. The window height follows the number of rows.")
        ft.addRow("Rows in the tower", self.sp_rows)

        self.cmb_style = QComboBox()
        self.cmb_style.addItem("Full tower", "full")
        self.cmb_style.addItem("Small corner tower (top umas only)", "compact")
        self.cmb_style.setCurrentIndex(1 if s.get("tower_style") == "compact" else 0)
        self.cmb_style.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_style.setMinimumContentsLength(10)
        self.cmb_style.currentIndexChanged.connect(lambda _i: (
            ov.set_setting("tower_style", self.cmb_style.currentData()),
            self.sp_crow.setEnabled(self.cmb_style.currentData() == "compact")))
        self.cmb_style.setToolTip("The small tower shows only the first umas, with name and gap. When the race ends, "
                                  "the results board comes in as usual.")
        ft.addRow("Tower style", self.cmb_style)

        self.sp_crow = QSpinBox()
        self.sp_crow.setRange(2, 10)
        self.sp_crow.setSuffix(" umas")
        self.sp_crow.setValue(int(s.get("compact_rows", 5) or 5))
        self.sp_crow.valueChanged.connect(lambda v: ov.set_setting("compact_rows", int(v)))
        self.sp_crow.setEnabled(s.get("tower_style") == "compact")
        ft.addRow("Small tower shows", self.sp_crow)

        self.cmb_corner = QComboBox()
        self.cmb_corner.addItem("Choose a corner...", "")
        for key, text in (("top-left", "Top left"), ("top-right", "Top right"),
                          ("bottom-left", "Bottom left"), ("bottom-right", "Bottom right")):
            self.cmb_corner.addItem(text, key)
        self.cmb_corner.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_corner.setMinimumContentsLength(10)
        self.cmb_corner.currentIndexChanged.connect(
            lambda _i: self.cmb_corner.currentData() and ov.snap_to_corner(self.cmb_corner.currentData()))
        self.cmb_corner.setToolTip("Moves the overlay window to that corner of the screen. You can still drag it.")
        ft.addRow("Move window to", self.cmb_corner)

        grow = QGroupBox("What the tower shows")
        fg = QFormLayout(grow)

        def combo(key, choices, tip=""):
            cb = QComboBox()
            cb.addItems([t for _v, t in choices])
            cb.setCurrentIndex(next((i for i, (v, _t) in enumerate(choices) if v == s.get(key)), 0))
            cb.activated.connect(lambda i: ov.set_setting(key, choices[i][0]))
            cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(10)
            if tip:
                cb.setToolTip(tip)
            return cb

        def check(key, text, default, tip=""):
            c = QCheckBox(text)
            c.setChecked(bool(s.get(key, default)))
            c.toggled.connect(lambda on: ov.set_setting(key, on))
            if tip:
                c.setToolTip(tip)
            return c

        self.cmb_header = combo("tower_header", [("both", "Track info and clock"), ("clock", "Clock only"),
                                                 ("none", "No header")])
        fg.addRow("Header", self.cmb_header)
        hrow = QHBoxLayout()
        self.sl_hsize = QSlider(Qt.Orientation.Horizontal)
        self.sl_hsize.setRange(60, 160)
        self.sl_hsize.setValue(int(float(s.get("header_scale", 1.0)) * 100))
        self.lbl_hsize = QLabel("%d%%" % self.sl_hsize.value())
        self.sl_hsize.valueChanged.connect(self.on_header_size)
        hrow.addWidget(self.sl_hsize)
        hrow.addWidget(self.lbl_hsize)
        fg.addRow("Header size", hrow)
        self.cmb_hclock = combo("header_clock", [("auto", "Automatic (lower when the track info does not fit)"),
                                                 ("right", "Next to the track info"),
                                                 ("below", "On the lower line (more room for the track info)")],
                                "When a big header text does not fit, put the clock lower so the track info can be wider.")
        fg.addRow("Clock", self.cmb_hclock)
        self.cmb_gap = combo("row_gap", [("both", "Seconds and length"), ("time", "Seconds only"),
                                         ("length", "Length only"), ("none", "No gap")],
                             "The gap to the uma ahead, on the right of every row.")
        fg.addRow("Gap", self.cmb_gap)
        fg.addRow("Gate number", check("row_gate", "Show the gate number", True, "Full tower only."))
        fg.addRow("Running style", check("row_style", "Show F / P / L / E", True, "Full tower only."))
        fg.addRow("Players only", check("players_only", "Hide umas without a trainer name (NPCs)", False,
                                        "Only when somebody in the race has a trainer name."))
        fg.addRow("Club", check("show_club", "Show each player's club under the name (from the pictures zip)", False,
                                "The clubs come with the zip of player pictures (People > Players > Import pictures from a zip)."))
        fg.addRow("Player name", combo("name_source", [("ingame", "In-game name (the trainer name)"), ("discord", "Discord name")],
                                       "Discord names come from the pictures zip (People > Players). A player without one shows the in-game name."))
        fg.addRow("Club tags", check("strip_tags", "Show CLUB｜Name as Name", False,
                                     "Used in the tower, the results board and the skill luck board."))
        fg.addRow("Team colour", check("tower_team_color", "Stripe for the players of a draft team", True,
                                       "Needs Team match mode (Draft tab)."))
        tv.insertWidget(1, grow)

        self.cb_board = QCheckBox("After each race")
        self.cb_board.setChecked(bool(s.get("results_board", True)))
        self.cb_board.toggled.connect(lambda on: ov.set_setting("results_board", on))
        self.cb_board.setToolTip("A second window ('" + RESULTS_NAME + "') with the final places.\n"
                                 "Add it as its own window source in OBS. Use 'Show results board' in the Home tab to place it.")
        fr.addRow("Show", self.cb_board)

        self.sp_board = QDoubleSpinBox()
        self.sp_board.setRange(0.0, 120.0)
        self.sp_board.setDecimals(0)
        self.sp_board.setSingleStep(1.0)
        self.sp_board.setSpecialValueText("Until the next race")
        self.sp_board.setSuffix(" seconds")
        self.sp_board.setValue(float(s.get("results_seconds", 10.0)))
        self.sp_board.valueChanged.connect(lambda v: ov.set_setting("results_seconds", float(v)))
        fr.addRow("Stays", self.sp_board)
        self.cb_luck = QCheckBox("After the results (luckiest / unluckiest)")
        self.cb_luck.setChecked(bool(s.get("luck_board", False)))
        self.cb_luck.setToolTip("Needs the race data to list each player's skills: saved races do. "
                                "In OBS it is its own window: " + LUCK_NAME + ".")
        self.cb_luck.toggled.connect(lambda on: ov.set_setting("luck_board", on))
        fl.addRow("Show", self.cb_luck)
        self.sp_luck = QSpinBox()
        self.sp_luck.setRange(1, 5)
        self.sp_luck.setSuffix(" players")
        self.sp_luck.setValue(int(s.get("luck_rows", 3)))
        self.sp_luck.valueChanged.connect(lambda v: ov.set_setting("luck_rows", int(v)))
        fl.addRow("Players per side", self.sp_luck)

        self.cb_prev = QCheckBox("Show a preview race (to see your changes)")
        self.cb_prev.toggled.connect(ov.set_preview)
        f.addRow("Preview", self.cb_prev)

        btn_reset = QPushButton("Reset look to defaults")
        btn_reset.clicked.connect(self.reset)
        fc.addRow("", btn_reset)

        # new options for the boards
        ed_rt = QLineEdit(s.get("results_title", ""))
        ed_rt.setPlaceholderText("RACE RESULTS")
        ed_rt.editingFinished.connect(lambda: (ov.set_setting("results_title", ed_rt.text().strip()), ov.board.update()))
        fr.addRow("Title", ed_rt)
        cmb_det = QComboBox()
        for key, text in (("both", "Finish time and gap"), ("time", "Finish time only"), ("none", "Names only")):
            cmb_det.addItem(text, key)
        cmb_det.setCurrentIndex(max(0, cmb_det.findData(s.get("results_details", "both"))))
        cmb_det.currentIndexChanged.connect(lambda _i: (ov.set_setting("results_details", cmb_det.currentData()), ov.board.update()))
        fr.addRow("Each row shows", cmb_det)

        def board_combo(form, label, key, choices, after):
            cb = QComboBox()
            for k, text in choices:
                cb.addItem(text, k)
            cb.setCurrentIndex(max(0, cb.findData(str(s.get(key)))))
            cb.currentIndexChanged.connect(lambda _i: (ov.set_setting(key, cb.currentData()), after()))
            form.addRow(label, cb)
            return cb

        def refit_results():
            if ov.board.entries:
                ov.board.set_data(ov.board.entries, ov.board.footer)
            for b in (ov.board, ov.luck, ov.standings, ov.mboard):
                b.update()
        self.cmb_rstyle = board_combo(fr, "Row style", "results_style",
                                      (("cards", "Cards"), ("lines", "Lines"), ("plain", "Plain")), refit_results)
        self.cmb_rcols = board_combo(fr, "Columns", "results_columns",
                                     (("auto", "Automatic (2 columns above 6 umas)"), ("1", "One column"),
                                      ("2", "Two columns")), refit_results)
        cb_win = QCheckBox("Tint the winner's row in the accent colour")
        cb_win.setChecked(bool(s.get("results_winner", True)))
        cb_win.toggled.connect(lambda on: (ov.set_setting("results_winner", on), refit_results()))
        fr.addRow("Winner", cb_win)
        self.cmb_bhead = board_combo(fr, "Top strip (all boards)", "board_header",
                                     (("band", "Dark strip and accent bar"), ("line", "Accent bar only"),
                                      ("plain", "Title only")), refit_results)
        self.cmb_bfoot = board_combo(fr, "Bottom strip (all boards)", "board_footer",
                                     (("band", "Dark strip"), ("plain", "Text only")), refit_results)
        ed_lt = QLineEdit(s.get("luck_title", ""))
        ed_lt.setPlaceholderText("SKILL LUCK")
        ed_lt.editingFinished.connect(lambda: (ov.set_setting("luck_title", ed_lt.text().strip()), ov.luck.update()))
        fl.addRow("Title", ed_lt)
        sp_ls = QDoubleSpinBox()
        sp_ls.setRange(0.0, 120.0)
        sp_ls.setDecimals(0)
        sp_ls.setSpecialValueText("Until the next race")
        sp_ls.setSuffix(" seconds")
        sp_ls.setValue(float(s.get("luck_seconds", 10.0)))
        sp_ls.valueChanged.connect(lambda v: ov.set_setting("luck_seconds", float(v)))
        fl.addRow("Stays", sp_ls)
        bnote = QLabel("<i>The standings board has its own settings in the Points tab. Each board is its own window "
                       "in OBS. Drag a board to move it, pull its edges to resize it.</i>")
        bnote.setWordWrap(True)
        bv.insertWidget(0, bnote)

        gtime = QGroupBox("When the boards come in")
        tl = QVBoxLayout(gtime)
        tn = QLabel("After a race the results board comes in first. Every other board can come in <b>one after "
                    "the other</b> or <b>together with the results board</b>, so you can show all of them at once. "
                    "Put each board in its own place in OBS. The seconds are extra waiting time.")
        tn.setWordWrap(True)
        tl.addWidget(tn)
        tf = QFormLayout()
        sp_rd = QDoubleSpinBox()
        sp_rd.setRange(0.0, 60.0)
        sp_rd.setDecimals(1)
        sp_rd.setSingleStep(0.5)
        sp_rd.setSuffix(" seconds later")
        sp_rd.setValue(float(s.get("results_delay", 0.0)))
        sp_rd.valueChanged.connect(lambda x: ov.set_setting("results_delay", float(x)))
        tf.addRow("Results board", sp_rd)
        self.timing = {}
        for key, label in (("luck", "Skill luck board"), ("match", "Match board"), ("standings", "Standings board")):
            row = QHBoxLayout()
            cmb = QComboBox()
            cmb.addItem("After the one before", "after")
            cmb.addItem("Together with the results", "with")
            cmb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            cmb.setMinimumContentsLength(10)
            cmb.setCurrentIndex(max(0, cmb.findData(s.get(key + "_when", "after"))))
            cmb.currentIndexChanged.connect(lambda _i, k=key, c=cmb: ov.set_setting(k + "_when", c.currentData()))
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 120.0)
            sp.setDecimals(1)
            sp.setSingleStep(0.5)
            sp.setPrefix("+ ")
            sp.setSuffix(" s")
            sp.setValue(float(s.get(key + "_delay", 0.0)))
            sp.valueChanged.connect(lambda x, k=key: ov.set_setting(k + "_delay", float(x)))
            row.addWidget(cmb, 1)
            row.addWidget(sp)
            tf.addRow(label, row)
            self.timing[key] = cmb
        tl.addLayout(tf)
        prow = QHBoxLayout()
        b_all = QPushButton("Show all at once")
        b_one = QPushButton("One after the other")

        def set_all(when):
            for k, c in self.timing.items():
                c.setCurrentIndex(c.findData(when))
        b_all.clicked.connect(lambda: set_all("with"))
        b_one.clicked.connect(lambda: set_all("after"))
        for b in (b_all, b_one):
            b.setMinimumWidth(10)
            prow.addWidget(b)
        tl.addLayout(prow)
        bv.insertWidget(1, gtime)
        look_tabs = QTabWidget()          # Look: colours, Tower and Boards as inner tabs (like People)
        look_tabs.addTab(self.scrolled(look), "Colours and pictures")
        look_tabs.addTab(self.scrolled(tower), "Tower")
        look_tabs.addTab(self.scrolled(boards), "Boards")
        tabs.addTab(look_tabs, "Look")
        if simple:
            look_tabs.setTabVisible(2, False)          # no boards in the simple version

        # ---- People tab (Players, Umas as inner tabs)
        people = QTabWidget()
        pl = QWidget()
        v = QVBoxLayout(pl)
        from .pointsui import Flow
        v.addWidget(Flow((("flag", "Race happens"), ("person", "Players saved here"), ("image", "Pick a picture"))))
        srow = QHBoxLayout()
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("Search a trainer, Discord name or club...")
        self.ed_find.setClearButtonEnabled(True)
        self.ed_find.textChanged.connect(self.filter_players)
        srow.addWidget(self.ed_find, 1)
        self.lbl_count = QLabel()
        srow.addWidget(self.lbl_count)
        v.addLayout(srow)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Trainer", "Discord name", "Discord id", "Club", "Races", "Last uma", "Picture"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)   # Ctrl/Shift for several
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(True)                # click a column title to sort
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(40)
        for col, width in enumerate((112, 98, 104, 88, 46, 96)):
            self.table.setColumnWidth(col, width)
        self.table.setToolTip("Click a column title to sort. Ctrl or Shift + click to pick several trainers.")
        v.addWidget(self.table, 1)
        br = QHBoxLayout()
        for text, fn in (("Choose picture...", self.choose_file), ("Paste link...", self.paste_link),
                         ("Remove picture", self.remove_pic), ("Add trainer...", self.add_trainer),
                         ("Delete trainer", self.delete_trainers)):
            b = QPushButton(text)
            if text.startswith("Choose"):
                b.setObjectName("primary")
            b.clicked.connect(fn)
            br.addWidget(b)
        v.addLayout(br)
        prow = QHBoxLayout()
        bimp = QPushButton("Import pictures zip...")
        bimp.setToolTip("The zip of player pictures from Poorpel's bot, or a zip a friend made with 'Save my pictures as a zip'. "
                        "You can also drag the zip onto this window.")
        bimp.setObjectName("primary")
        bimp.clicked.connect(self.import_pics)
        bexp = QPushButton("Save my pictures as a zip...")
        bexp.clicked.connect(self.export_pics)
        prow.addWidget(bimp)
        prow.addWidget(bexp)
        v.addLayout(prow)
        people.addTab(pl, "Players")

        # ---- Umas tab (the uma pictures)
        ut = QWidget()
        uv = QVBoxLayout(ut)
        uinfo = QLabel("Every uma that appears in a race is collected here. Choose your own picture for her, or "
                       "remove it to go back to the default face. Your pictures are kept in "
                       "<i>images/uma</i> and only change this program.")
        uinfo.setWordWrap(True)
        uv.addWidget(uinfo)
        self.cb_default_faces = QCheckBox("Use the faces from Race Overlay when I have not chosen a picture")
        self.cb_default_faces.setChecked(bool(ov.s.get("default_faces", True)))
        self.cb_default_faces.toggled.connect(ov.set_default_faces)
        uv.addWidget(self.cb_default_faces)
        self.utable = QTableWidget(0, 4)
        self.utable.setHorizontalHeaderLabels(["Face", "Uma", "Card id", "Picture"])
        self.utable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.utable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.utable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.utable.horizontalHeader().setStretchLastSection(True)
        self.utable.verticalHeader().setVisible(False)
        self.utable.verticalHeader().setDefaultSectionSize(46)
        self.utable.setIconSize(QSize(40, 40))
        self.utable.setAlternatingRowColors(True)
        self.utable.setShowGrid(False)
        self.utable.setColumnWidth(0, 56)
        self.utable.setColumnWidth(1, 190)
        self.utable.setColumnWidth(2, 80)
        uv.addWidget(self.utable, 1)
        ubr = QHBoxLayout()
        for text, fn in (("Choose picture...", self.choose_uma_file), ("Use default face", self.remove_uma_pic),
                         ("Add uma...", self.add_uma), ("Add all umas", self.add_all_umas), ("Open folder", lambda: open_folder(ov.thumbs.uma))):
            b = QPushButton(text)
            if text.startswith("Choose"):
                b.setObjectName("primary")
            b.clicked.connect(fn)
            ubr.addWidget(b)
        uv.addLayout(ubr)
        people.addTab(ut, "Umas")
        self._uma_pix_count = -1

        tabs.addTab(people, "People")

        self.build_standings_tab(tabs)
        self.build_draft_tab(tabs)

        # ---- Help tab: checks and the log, so you do not need a terminal
        stt = QWidget()
        sv = QVBoxLayout(stt)
        self.lbl_checks = QLabel()
        self.lbl_checks.setWordWrap(True)
        self.lbl_checks.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_checks.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_sum = QLabel()                       # one line: all good or n things to look at
        self.lbl_sum.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_sum.setStyleSheet("font-size:15px;font-weight:700;padding:8px 4px;")
        sv.addWidget(self.lbl_sum)
        sv.addWidget(self.lbl_checks)
        srow = QHBoxLayout()
        self.cmb_log = QComboBox()
        self.cmb_log.addItem("Log: this program", None)
        for title, path in LOG_FILES:
            self.cmb_log.addItem("Log: " + title, path)
        self.cmb_log.currentIndexChanged.connect(lambda _i: self.refresh_status())
        self.cb_fixme = QCheckBox("Hide Wine noise")
        self.cb_fixme.setChecked(True)
        self.cb_fixme.setVisible(not IS_WINDOWS)       # Wine messages do not exist on Windows
        self.cb_fixme.toggled.connect(lambda _on: self.refresh_status())
        btn_again = QPushButton("Check again")
        btn_again.clicked.connect(lambda: self.refresh_status())
        self.btn_copy = QPushButton("Copy for support")
        self.btn_copy.setObjectName("primary")
        self.btn_copy.clicked.connect(self.copy_status)
        sv.addWidget(self.btn_copy)
        srow.addWidget(self.cmb_log, 1)
        srow.addWidget(self.cb_fixme)
        srow.addWidget(btn_again)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.txt_log.setMinimumHeight(260)
        fold_log = Collapsible("Log (for support)")
        fold_log.body_l.addLayout(srow)
        fold_log.body_l.addWidget(self.txt_log)
        sv.addWidget(fold_log)
        sv.addStretch(1)
        tabs.addTab(stt, "Help")
        self._tabs = tabs
        self._status_tab = stt
        if limited:                                  # Tower: Home, Look, People, Help. Advanced: also Data
            hidden = ("Data", "Points", "Draft") if simple else ("Points", "Draft")
            for i in range(tabs.count()):
                if tabs.tabText(i).replace(" (WIP)", "") in hidden:
                    tabs.setTabVisible(i, False)
        tabs.currentChanged.connect(lambda _i: self.refresh_status() if tabs.currentWidget() is stt else None)
        self.refresh_umas()

        self.sync_widgets()
        self.poll()
        self.timer = QTimer(self)      # keeps the preview tick-box and trainer list up to date
        self.timer.timeout.connect(self.poll)
        self.timer.start(1500)

    @staticmethod
    def scrolled(widget):
        """A tab that scrolls on small screens instead of squeezing its contents."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setWidget(widget)
        return sa

    # ---- standings tab
    def build_analysis_box(self):
        """The analysis board box (shown in the Data tab)."""
        ov, s = self.ov, self.ov.s
        from .pointsui import Flow
        box = QGroupBox("Analysis board")
        l = QVBoxLayout(box)
        l.addWidget(Flow((("flag", "Race ends"), ("chart", "Charts and numbers"), ("screen", "Your screen or stream"))))
        info = QLabel("Speed, stamina, gaps and skills of every uma, like Hakuraku.")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        info.setToolTip("Pages: Table, Speed, Stamina, Gap, Lane, Skills. Click an uma to follow her on every page. "
                        "In OBS it is its own window: " + ANALYSIS_NAME + ".")
        l.addWidget(info)
        b_open = QPushButton("Open the analysis board")
        b_open.setObjectName("primary")
        b_open.clicked.connect(lambda: ov.analysis.open_now())
        l.addWidget(b_open)
        cb = QCheckBox("Open it after every race")
        cb.setChecked(bool(s.get("analysis_board", False)))
        cb.toggled.connect(lambda on: ov.set_setting("analysis_board", on))
        l.addWidget(cb)
        cb2 = QCheckBox("Change page by itself")
        cb2.setChecked(bool(s.get("analysis_auto", True)))
        cb2.toggled.connect(lambda on: (ov.set_setting("analysis_auto", on), ov.analysis.cb_auto.setChecked(on)))
        l.addWidget(cb2)
        f = QFormLayout()
        sp1 = QDoubleSpinBox()
        sp1.setRange(0, 600)
        sp1.setDecimals(0)
        sp1.setSuffix(" seconds")
        sp1.setSpecialValueText("until the next race")
        sp1.setValue(float(s.get("analysis_seconds", 30.0)))
        sp1.valueChanged.connect(lambda v: ov.set_setting("analysis_seconds", float(v)))
        f.addRow("Stays open", sp1)
        sp2 = QDoubleSpinBox()
        sp2.setRange(2, 120)
        sp2.setDecimals(0)
        sp2.setSuffix(" seconds")
        sp2.setValue(float(s.get("analysis_page_seconds", 8.0)))
        sp2.valueChanged.connect(lambda v: ov.set_setting("analysis_page_seconds", float(v)))
        f.addRow("Next page after", sp2)
        l.addLayout(f)
        b_copy = QPushButton("Copy the window name for OBS")
        b_copy.setToolTip(ANALYSIS_NAME)
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(ANALYSIS_NAME))
        l.addWidget(b_copy)
        return box

    def build_skills_box(self):
        """The skills spreadsheet box (shown in the Data tab)."""
        ov, s = self.ov, self.ov.s
        from .pointsui import Flow
        dbox = QGroupBox("Skills spreadsheet")
        dl = QVBoxLayout(dbox)
        dl.addWidget(Flow((("paste", "Your race files"), ("sheet", "Spreadsheet of skills"))))
        di = QLabel("Shows the skills every uma <b>brought</b>, with the level.")
        di.setToolTip("Sheets: Who has what (one row per uma), Skill counts (how many umas brought each skill, and who) and "
                      "All skills (one row per skill, to filter). Skill names come from Race Overlay's umdb.json. "
                      "A race saved twice counts once.")
        di.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        dl.addWidget(di)
        db = QHBoxLayout()
        for text, fn in (("Choose race files...", self.skills_from_files), ("Choose a folder...", self.skills_from_folder)):
            b = QPushButton(text)
            b.setObjectName("primary")
            b.setMinimumWidth(10)
            b.clicked.connect(fn)
            db.addWidget(b)
        dl.addLayout(db)
        live = Collapsible("My live races")
        self.cb_rdata = QCheckBox("Keep the races I play live")
        self.cb_rdata.setChecked(bool(s.get("race_data", True)))
        self.cb_rdata.setToolTip("Only races that really happen are kept (not previews or old files). Everything stays on this computer.")
        self.cb_rdata.toggled.connect(lambda on: ov.set_setting("race_data", on))
        live.body_l.addWidget(self.cb_rdata)
        self.lbl_rdata = QLabel()
        self.lbl_rdata.setWordWrap(True)
        live.body_l.addWidget(self.lbl_rdata)
        db2 = QHBoxLayout()
        for text, fn in (("Spreadsheet of my live races...", self.skills_from_live), ("Delete the kept live races", self.clear_race_data)):
            b = QPushButton(text)
            b.setMinimumWidth(10)
            b.clicked.connect(fn)
            db2.addWidget(b)
        live.body_l.addLayout(db2)
        dl.addWidget(live)
        return dbox

    def build_standings_tab(self, tabs):
        from .pointsui import Flow, ModeCard, StepCard
        ov, s = self.ov, self.ov.s
        st = QWidget()
        v = QVBoxLayout(st)
        v.setSpacing(10)
        v.addWidget(Flow((("flag", "Race ends"), ("count", "Points added"), ("screen", "Shown on stream"))))

        # where do the points come from? (the card buttons fill this hidden list)
        self.cmb_smode = QComboBox(st)
        self.cmb_smode.addItem("This program counts", "local")
        self.cmb_smode.addItem("My Google Sheet", "sheet")
        self.cmb_smode.setCurrentIndex(1 if s.get("standings_mode") == "sheet" else 0)
        self.cmb_smode.currentIndexChanged.connect(
            lambda _i: (ov.set_setting("standings_mode", self.cmb_smode.currentData()), ov.standings.refresh(True)))
        self.cmb_smode.hide()
        cards = QHBoxLayout()
        self.card_local = ModeCard("count", "This program counts", "Nothing to set up")
        self.card_sheet = ModeCard("sheet", "My Google Sheet", "The board follows your sheet")
        for i, card in enumerate((self.card_local, self.card_sheet)):
            card.clicked.connect(lambda _c=False, i=i: self.cmb_smode.setCurrentIndex(i))
            cards.addWidget(card)
        v.addLayout(cards)

        # --- counted by this program
        sbox = QWidget()
        sl = QVBoxLayout(sbox)
        sl.setContentsMargins(0, 0, 0, 0)
        self.lbl_book = QLabel()
        self.lbl_book.setStyleSheet("font-size:16px;font-weight:700;")
        self.lbl_book.setToolTip("Players are matched by trainer name. Replays, previews and old race files never give points, "
                                 "and the same race is never counted twice. 1st place gets as many points as there are players, the last gets 1.")
        sl.addWidget(self.lbl_book)
        r2 = QHBoxLayout()
        b_undo = QPushButton("Undo last race")
        b_undo.clicked.connect(self.undo_race)
        b_clr = QPushButton("New bracket")
        b_clr.clicked.connect(self.clear_scores)
        b_clr.setToolTip("Delete all counted points and start again")
        for b in (b_undo, b_clr):
            b.setMinimumWidth(10)
            r2.addWidget(b)
        sl.addLayout(r2)
        share = Collapsible("Save or share the races")
        r3 = QHBoxLayout()
        b_exp = QPushButton("Save as .csv...")
        b_exp.clicked.connect(self.export_scores)
        b_sv = QPushButton("Save the races as a file...")
        b_sv.setToolTip("All races counted here, in one file. Send it to a friend who counts the other rounds.")
        b_sv.clicked.connect(self.save_races_file)
        b_ld = QPushButton("Add races from a file...")
        b_ld.setToolTip("Adds the races of a file a friend saved. A race you both counted is only counted once.")
        b_ld.clicked.connect(self.load_races_file)
        for b in (b_exp, b_sv, b_ld):
            b.setMinimumWidth(10)
            r3.addWidget(b)
        share.body_l.addLayout(r3)
        sl.addWidget(share)
        v.addWidget(sbox)

        # --- from my Google Sheet
        sheetw = QWidget()
        bl2 = QVBoxLayout(sheetw)
        bl2.setContentsMargins(0, 0, 0, 0)
        bl2.setSpacing(8)
        steps = QHBoxLayout()
        for n, kind, title, sub in ((1, "share", "Share the sheet", "Anyone with the link can view"),
                                    (2, "link", "Copy the link", "from the address bar"),
                                    (3, "paste", "Paste it below", "then press Connect")):
            steps.addWidget(StepCard(n, kind, title, sub))
        bl2.addLayout(steps)
        row = QHBoxLayout()
        self.ed_sheet = QLineEdit(s.get("standings_sheet", ""))
        self.ed_sheet.setPlaceholderText("Google Sheets link or file path")
        self.ed_sheet.setMinimumWidth(100)
        self.ed_sheet.editingFinished.connect(self.apply_sheet)
        row.addWidget(self.ed_sheet)
        bc = QPushButton("Connect")
        bc.setObjectName("primary")
        bc.clicked.connect(self.apply_sheet)
        row.addWidget(bc)
        bf = QPushButton("File...")
        bf.clicked.connect(self.choose_sheet_file)
        row.addWidget(bf)
        bl2.addLayout(row)
        self.lbl_sheet = QLabel("")
        self.lbl_sheet.setWordWrap(True)
        bl2.addWidget(self.lbl_sheet)
        cols = Collapsible("Columns (only if the automatic way fails)")
        f = cols.form()
        self.ed_tab = QLineEdit(s.get("standings_tab", ""))
        self.ed_tab.setPlaceholderText("first tab")
        self.ed_tab.setMinimumWidth(60)
        self.ed_tab.editingFinished.connect(self.apply_sheet)
        f.addRow(".xlsx tab name", self.ed_tab)
        self.ed_cols = {}
        for key, label, default in (("standings_name_col", "Column with the player", "B"),
                                    ("standings_score_col", "Column with the points", "D"),
                                    ("standings_uma_col", "Column with the uma (optional)", "C")):
            ed = QLineEdit(str(s.get(key, default)))
            ed.setMaximumWidth(70)
            ed.editingFinished.connect(self.apply_sheet)
            self.ed_cols[key] = ed
            f.addRow(label, ed)
        self.sp_first = QSpinBox()
        self.sp_first.setRange(1, 999)
        self.sp_first.setValue(int(s.get("standings_first_row", 4)))
        self.sp_first.valueChanged.connect(lambda _v: self.apply_sheet())
        f.addRow("First row with a player", self.sp_first)
        rbox = Collapsible("Rounds (when your sheet has several)")
        rl = rbox.body_l
        rf = QFormLayout()
        self.cmb_view = QComboBox()
        for key, text in VIEWS:
            self.cmb_view.addItem(text, key)
        self.cmb_view.setCurrentIndex(max(0, self.cmb_view.findData(s.get("standings_view", "plain"))))
        self.cmb_view.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_view.setMinimumContentsLength(10)
        self.cmb_view.currentIndexChanged.connect(lambda _i: self.apply_view())
        rf.addRow("Show", self.cmb_view)
        self.ed_blocks = QLineEdit("auto" if is_auto(s.get("standings_round_blocks")) else str(s.get("standings_round_blocks")))
        self.ed_blocks.setMinimumWidth(60)
        self.ed_blocks.setToolTip("auto = found by the headers Trainer / Uma / Score. Or type the player, uma and points column of round 1; then round 2; then round 3, for example B,C,D; G,H,I; L,M,N")
        self.ed_blocks.editingFinished.connect(self.apply_rounds)
        rf.addRow("Round 1; 2; 3 (player, uma, points)", self.ed_blocks)
        self.ed_total = QLineEdit("auto" if is_auto(s.get("standings_total_cols")) else str(s.get("standings_total_cols")))
        self.ed_total.setMinimumWidth(60)
        self.ed_total.setToolTip("auto = found by the headers Member / Round 1 / 2 / 3. Or type the player, round 1, round 2 and round 3 column, for example Q,R,S,T")
        self.ed_total.editingFinished.connect(self.apply_rounds)
        rf.addRow("Final Rankings (player, 1, 2, 3)", self.ed_total)
        rl.addLayout(rf)
        lay_fold = Collapsible("Sheet layout (only if the board looks wrong)")
        lay_hint = QLabel("The program finds the columns and rounds by itself. Change these only when the board is wrong.")
        lay_hint.setWordWrap(True)
        lay_hint.setStyleSheet("color:%s;" % THEME["sub"])
        lay_fold.body_l.addWidget(lay_hint)
        lay_fold.body_l.addWidget(cols)
        lay_fold.body_l.addWidget(rbox)
        bl2.addWidget(lay_fold)
        wbox = Collapsible("Fill my sheet with the placings (optional)")
        wl = wbox.body_l
        wg = QGridLayout()
        wg.setSpacing(8)
        for i, (n, kind, title, sub) in enumerate((
                (1, "paste", "Copy the script", "press the button below"),
                (2, "sheet", "Paste it in your sheet", "Extensions > Apps Script > Save"),
                (3, "share", "Deploy as Web app", "Who has access: Anyone"),
                (4, "link", "Paste the link here", "then press Test the link"))):
            wg.addWidget(StepCard(n, kind, title, sub), i // 2, i % 2)
        wl.addLayout(wg)
        b_script = QPushButton("Copy the script")
        b_script.setObjectName("primary")
        b_script.clicked.connect(self.copy_sheet_script)
        wl.addWidget(b_script)
        wf = QFormLayout()
        self.ed_wurl = QLineEdit(str(s.get("sheet_write_url", "")))
        self.ed_wurl.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self.ed_wurl.editingFinished.connect(lambda: ov.set_setting("sheet_write_url", self.ed_wurl.text().strip()))
        wf.addRow("Web app link", self.ed_wurl)
        self.cmb_wround = QComboBox()
        for k in (1, 2, 3):
            self.cmb_wround.addItem("Round %d  (tab Group Stage Round %d)" % (k, k), k)
        self.cmb_wround.setCurrentIndex(max(0, min(2, int(s.get("sheet_write_round", 1)) - 1)))
        self.cmb_wround.currentIndexChanged.connect(lambda _i: ov.set_setting("sheet_write_round", self.cmb_wround.currentData()))
        wf.addRow("Round", self.cmb_wround)
        self.cb_wauto = QCheckBox("Send every finished race by itself")
        self.cb_wauto.setChecked(bool(s.get("sheet_write_auto", False)))
        self.cb_wauto.setToolTip("Only races that really happen are sent (not previews or old files). A placing that is already "
                                 "in the sheet is never overwritten.")
        self.cb_wauto.toggled.connect(lambda on: ov.set_setting("sheet_write_auto", on))
        wf.addRow("", self.cb_wauto)
        wl.addLayout(wf)
        wb = QHBoxLayout()
        for text, fn in (("Test the link", self.test_sheet_link), ("Send the last race now", self.send_sheet_now)):
            b = QPushButton(text)
            b.setMinimumWidth(10)
            b.clicked.connect(fn)
            wb.addWidget(b)
        wl.addLayout(wb)
        self.lbl_wstat = QLabel(ov.sheet_status or "Nothing sent yet.")
        self.lbl_wstat.setWordWrap(True)
        wl.addWidget(self.lbl_wstat)
        wsec = Collapsible("Secret code (made for you)")
        self.ed_wsec = QLineEdit(str(s.get("sheet_write_secret", "")))
        self.ed_wsec.setPlaceholderText("made when you press Copy the script")
        self.ed_wsec.editingFinished.connect(lambda: ov.set_setting("sheet_write_secret", self.ed_wsec.text().strip()))
        wsec.body_l.addWidget(self.ed_wsec)
        wl.addWidget(wsec)
        bl2.addWidget(wbox)
        v.addWidget(sheetw)

        # --- what is shown on stream
        obox = QGroupBox("On stream")
        ol = QVBoxLayout(obox)
        cb1 = QCheckBox("Points on the results board")
        cb1.setChecked(bool(s.get("scoring", True)))
        cb1.toggled.connect(lambda on: ov.set_setting("scoring", on))
        ol.addWidget(cb1)
        cb2 = QCheckBox("Show the standings board after the results")
        cb2.setChecked(bool(s.get("standings_board", True)))
        cb2.toggled.connect(lambda on: ov.set_setting("standings_board", on))
        ol.addWidget(cb2)
        erow = QHBoxLayout()
        erow.addWidget(QLabel("Show it after every"))
        sp_every = QSpinBox()
        sp_every.setRange(0, 99)
        sp_every.setSpecialValueText("never (only by hand)")
        sp_every.setSuffix(" race(s)")
        sp_every.setValue(int(s.get("standings_every", 1)))
        sp_every.valueChanged.connect(lambda x: (ov.set_setting("standings_every", int(x)),
                                                 ov.cfg.__setitem__("races_since_standings", 0)))
        erow.addWidget(sp_every)
        erow.addStretch(1)
        ol.addLayout(erow)
        bnow = QPushButton("Show / hide the standings now")
        bnow.setToolTip("Add the window named " + STANDINGS_NAME + " to OBS as a source.")
        bnow.clicked.connect(lambda: ov.show_standings_now())
        ol.addWidget(bnow)
        v.addWidget(obox)

        lbox = Collapsible("Look of the board: title, borders, avatars, pages")
        lf = lbox.form()
        ed_title = QLineEdit(s.get("standings_title", "STANDINGS"))
        ed_title.setPlaceholderText("STANDINGS")
        ed_title.editingFinished.connect(lambda: ov.set_setting("standings_title", ed_title.text().strip() or "STANDINGS"))
        lf.addRow("Title", ed_title)
        cb_zero = QCheckBox("Do not show players with 0 points (sheet)")
        cb_zero.setChecked(bool(s.get("standings_hide_zero", True)))
        cb_zero.toggled.connect(lambda on: (ov.set_setting("standings_hide_zero", on), ov.standings.apply_raw()))
        lf.addRow("Zero points", cb_zero)
        ed_border = QLineEdit(str(s.get("standings_border_values", "9,8,7")))
        ed_border.setMaximumWidth(120)
        ed_border.setToolTip("Single rounds: players with this many points get a gold, silver and bronze border")
        ed_border.editingFinished.connect(lambda: ov.set_setting("standings_border_values", ed_border.text().strip()))
        lf.addRow("Border: gold, silver, bronze points", ed_border)
        sp_top = QSpinBox()
        sp_top.setRange(0, 50)
        sp_top.setSpecialValueText("Off")
        sp_top.setSuffix(" players")
        sp_top.setValue(int(s.get("standings_top_n", 10)))
        sp_top.setToolTip("Rounds added up (and points counted by this program): the best players get a gold border")
        sp_top.valueChanged.connect(lambda x: ov.set_setting("standings_top_n", int(x)))
        lf.addRow("Gold border for the top", sp_top)
        cmb_lay = QComboBox()
        cmb_lay.addItem("Portrait (one column)", "portrait")
        cmb_lay.addItem("Landscape (two columns)", "landscape")
        cmb_lay.setCurrentIndex(1 if s.get("standings_layout") == "landscape" else 0)
        cmb_lay.currentIndexChanged.connect(lambda _i: ov.set_setting("standings_layout", cmb_lay.currentData()))
        lf.addRow("Shape", cmb_lay)
        cb_av = QCheckBox("Show a picture for every player")
        cb_av.setChecked(bool(s.get("standings_avatars", True)))
        cb_av.setToolTip("Uses the picture you chose in the People tab (Players). Without one: the first letter.")
        cb_av.toggled.connect(lambda on: ov.set_setting("standings_avatars", on))
        lf.addRow("Avatars", cb_av)
        sp_rows = QSpinBox()
        sp_rows.setRange(3, 20)
        sp_rows.setSuffix(" players")
        sp_rows.setValue(int(s.get("standings_rows", 8)))
        sp_rows.valueChanged.connect(lambda x: (ov.set_setting("standings_rows", int(x)), ov.standings.refresh(False)))
        lf.addRow("Per page", sp_rows)
        sp_page = QDoubleSpinBox()
        sp_page.setRange(2.0, 60.0)
        sp_page.setDecimals(0)
        sp_page.setSuffix(" seconds")
        sp_page.setValue(float(s.get("standings_page_seconds", 6.0)))
        sp_page.valueChanged.connect(lambda x: ov.set_setting("standings_page_seconds", float(x)))
        lf.addRow("Next page after", sp_page)
        v.addWidget(lbox)
        v.addStretch(1)

        def sync_smode(*_a):
            sheet = self.cmb_smode.currentData() == "sheet"
            sheetw.setVisible(sheet)
            sbox.setVisible(not sheet)
            self.card_sheet.setChecked(sheet)
            self.card_local.setChecked(not sheet)
        self.cmb_smode.currentIndexChanged.connect(sync_smode)
        sync_smode()
        sc = self.scrolled(st)
        self._stand_tab = sc
        self.update_book_label()
        tabs.addTab(sc, "Points")
        self._data_layout.insertWidget(0, self.build_skills_box())      # in the Data tab, at the top
        self._data_layout.insertWidget(1, self.build_analysis_box())
        self.update_race_data_label()

    # ---- draft tab (team match)
    def build_draft_tab(self, tabs):
        ov, s = self.ov, self.ov.s
        m = ov.match
        dt = QWidget()
        v = QVBoxLayout(dt)
        from .pointsui import Flow
        v.addWidget(Flow((("team", "Two teams"), ("flag", "Race"), ("count", "4 / 2 / 1 points"), ("cup", "First to 25"))))
        intro = QLabel("Add the players of both teams below. Players on no team never score.")
        intro.setToolTip("After every race the best placed team players score for their team (1st 4 points, 2nd 2, 3rd 1: you can change it). "
                         "The next team player takes the placement of a player on no team. The first team to reach the target wins. "
                         "In OBS the board is its own window.")
        intro.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(intro)

        cb = QCheckBox("Team match mode")
        cb.setToolTip("Points go to the teams. Single-player points and standings pause.")
        cb.setChecked(bool(s.get("match_mode", False)))
        cb.toggled.connect(lambda on: ov.set_setting("match_mode", on))
        v.addWidget(cb)
        cb2 = QCheckBox("Show the match board after the results")
        cb2.setToolTip("It stays until the next race.")
        cb2.setChecked(bool(s.get("match_board", True)))
        cb2.toggled.connect(lambda on: ov.set_setting("match_board", on))
        v.addWidget(cb2)

        rf = QFormLayout()
        sp_t = QSpinBox()
        sp_t.setRange(1, 999)
        sp_t.setSuffix(" points")
        sp_t.setValue(int(m.target))
        sp_t.valueChanged.connect(lambda x: (m.set_rules(target=int(x)), ov.mboard.refresh()))
        rf.addRow("First team to reach", sp_t)
        ed_p = QLineEdit(",".join(str(x) for x in m.points))
        ed_p.setMaximumWidth(140)
        ed_p.setToolTip("Points for the 1st, 2nd, 3rd ... team player, for example 4,2,1")
        ed_p.editingFinished.connect(lambda: (m.set_rules(points=ed_p.text()),
                                              ed_p.setText(",".join(str(x) for x in m.points)),
                                              self.update_match_label()))
        rf.addRow("Points for 1st, 2nd, 3rd", ed_p)
        v.addLayout(rf)

        self._team_edits = []
        for i in range(2):
            box = QGroupBox("Team %d" % (i + 1))
            bl = QVBoxLayout(box)
            top = QHBoxLayout()
            ed_n = QLineEdit(m.teams[i]["name"])
            ed_n.setPlaceholderText("Team name")
            ed_n.setMinimumWidth(80)
            btn_c = QPushButton()
            btn_c.setMaximumWidth(110)
            self.swatch(btn_c, m.teams[i]["color"])
            top.addWidget(ed_n, 1)
            top.addWidget(btn_c)
            bl.addLayout(top)
            pl = QHBoxLayout()
            col1, col2 = QVBoxLayout(), QVBoxLayout()
            col1.addWidget(QLabel("Players (trainer names, one per line)"))
            ed_pl = QPlainTextEdit("\n".join(m.teams[i]["players"]))
            ed_pl.setFixedHeight(92)
            col1.addWidget(ed_pl)
            b_add = QPushButton("Add a player seen in a race...")
            col1.addWidget(b_add)
            col2.addWidget(QLabel("Drafted umas (one per line)"))
            ed_pk = QPlainTextEdit("\n".join(m.teams[i]["picks"]))
            ed_pk.setFixedHeight(92)
            col2.addWidget(ed_pk)
            b_pk = QPushButton("Add a uma...")
            col2.addWidget(b_pk)
            pl.addLayout(col1)
            pl.addLayout(col2)
            bl.addLayout(pl)
            v.addWidget(box)

            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(500)

            def save(i=i, ed_n=ed_n, ed_pl=ed_pl, ed_pk=ed_pk):
                m.set_team(i, name=ed_n.text(), players=ed_pl.toPlainText(), picks=ed_pk.toPlainText())
                ov.mboard.refresh()
                self.update_match_label()
            timer.timeout.connect(save)
            for w in (ed_n, ed_pl, ed_pk):
                w.textChanged.connect(lambda *_a, t=timer: t.start())
            btn_c.clicked.connect(lambda _c=False, i=i, b=btn_c: self.pick_team_color(i, b))
            b_add.clicked.connect(lambda _c=False, ed=ed_pl: self.add_seen_player(ed))
            b_pk.clicked.connect(lambda _c=False, ed=ed_pk: self.add_seen_uma(ed))
            self._team_edits.append((ed_n, ed_pl, ed_pk))

        sbox = QGroupBox("Score")
        sl = QVBoxLayout(sbox)
        self.lbl_match = QLabel()
        self.lbl_match.setWordWrap(True)
        sl.addWidget(self.lbl_match)
        r1 = QHBoxLayout()
        b_undo = QPushButton("Undo last race")
        b_undo.clicked.connect(self.match_undo)
        b_adj = QPushButton("Add or take points...")
        b_adj.setToolTip("A ruling by hand: a remake, a penalty, a disconnect that was ruled on.")
        b_adj.clicked.connect(self.match_adjust)
        b_new = QPushButton("New match")
        b_new.setToolTip("Forget all races and rulings. The teams, players and drafted umas stay.")
        b_new.clicked.connect(self.match_new)
        b_exp = QPushButton("Save as .csv...")
        b_exp.clicked.connect(self.match_export)
        for b in (b_undo, b_adj, b_new, b_exp):
            b.setMinimumWidth(10)
            r1.addWidget(b)
        sl.addLayout(r1)
        self.lbl_match.setToolTip("Players are matched by trainer name (capital letters do not matter). Replays, previews and "
                                  "old race files never give points, and the same race is never counted twice.")
        v.addWidget(sbox)

        gl = QGroupBox("Board")
        gf = QFormLayout(gl)
        ed_bt = QLineEdit(s.get("match_title", ""))
        ed_bt.setPlaceholderText("TEAM MATCH")
        ed_bt.editingFinished.connect(lambda: (ov.set_setting("match_title", ed_bt.text().strip()), ov.mboard.update()))
        gf.addRow("Title", ed_bt)
        cb_rc = QCheckBox("Show the points of every race")
        cb_rc.setChecked(bool(s.get("match_show_races", True)))
        cb_rc.toggled.connect(lambda on: (ov.set_setting("match_show_races", on), ov.mboard.refresh()))
        gf.addRow("Race by race", cb_rc)
        cb_pk = QCheckBox("Show the drafted umas")
        cb_pk.setChecked(bool(s.get("match_show_picks", True)))
        cb_pk.toggled.connect(lambda on: (ov.set_setting("match_show_picks", on), ov.mboard.refresh()))
        gf.addRow("Drafted umas", cb_pk)
        sp_ms = QDoubleSpinBox()
        sp_ms.setRange(0.0, 300.0)
        sp_ms.setDecimals(0)
        sp_ms.setSpecialValueText("Until the next race")
        sp_ms.setSuffix(" seconds")
        sp_ms.setValue(float(s.get("match_seconds", 0.0)))
        sp_ms.valueChanged.connect(lambda x: ov.set_setting("match_seconds", float(x)))
        gf.addRow("Stays", sp_ms)
        fold_board = Collapsible("Look of the match board")
        gl.setStyleSheet("QGroupBox { border: none; margin-top: 0; padding-top: 0; } QGroupBox::title { height: 0; padding: 0; background: transparent; }")
        fold_board.body_l.addWidget(gl)
        v.addWidget(fold_board)
        v.addStretch(1)
        sc = self.scrolled(dt)
        self._draft_tab = sc
        self.update_match_label()
        tabs.addTab(sc, "Draft (WIP)")

    def pick_team_color(self, i, btn):
        c = QColorDialog.getColor(QColor(self.ov.match.teams[i]["color"]), self, "Team colour")
        if c.isValid():
            self.ov.match.set_team(i, color=c.name())
            self.swatch(btn, c.name())
            self.ov.mboard.refresh()

    def add_seen_player(self, ed):
        names = [n for n, _d in self.ov.players.rows()]
        if not names:
            QMessageBox.information(self, "No players yet", "Players show up here after the overlay has seen a race. "
                                    "You can also type the trainer names, one per line.")
            return
        name, ok = QInputDialog.getItem(self, "Add a player", "Trainer seen in a race:", names, 0, False)
        if ok and name:
            ed.setPlainText((ed.toPlainText().rstrip() + "\n" + name).strip())

    def add_seen_uma(self, ed):
        names = sorted({r[2] for r in self.ov.umas.rows() if r[2]})
        if names:
            name, ok = QInputDialog.getItem(self, "Add a uma", "Uma:", names, 0, True)
        else:
            name, ok = QInputDialog.getText(self, "Add a uma", "Uma name:")
        if ok and name.strip():
            ed.setPlainText((ed.toPlainText().rstrip() + "\n" + name.strip()).strip())

    def update_match_label(self):
        m = self.ov.match
        a, b = m.totals()
        w = m.winner()
        text = "<b>%s</b> %d &nbsp;:&nbsp; %d <b>%s</b> &nbsp; (first to %d)" % (
            m.teams[0]["name"], a, b, m.teams[1]["name"], m.target)
        if w is not None:
            text += "<br><b>%s wins!</b>" % m.teams[w]["name"]
        rows = m.race_rows()
        text += "<br>" + (", ".join("%s %+d / %+d" % (lab, da, db) if lab == "Ruling" else "%s %d / %d" % (lab, da, db)
                                    for lab, da, db in rows) if rows else "No race scored yet.")
        if not m.ready():
            text += "<br><i>Add at least one player to each team, or nobody will score.</i>"
        if not self.ov.s.get("match_mode", False):
            text += "<br><b>Team match mode is OFF: no race is scored. Tick it above.</b>"
        note = getattr(self.ov, "match_note", "")
        if note:
            text += "<br>Last race: " + note
        self.lbl_match.setText(text)

    def match_undo(self):
        if self.ov.match.undo_last():
            self.ov.mboard.refresh()
        self.update_match_label()

    def match_adjust(self):
        m = self.ov.match
        team, ok = QInputDialog.getItem(self, "Add or take points", "Team:", [t["name"] for t in m.teams], 0, False)
        if not ok:
            return
        pts, ok = QInputDialog.getInt(self, "Add or take points", "Points (negative takes away):", 1, -999, 999)
        if not ok or pts == 0:
            return
        note, _ok = QInputDialog.getText(self, "Add or take points", "Reason (optional):")
        m.adjust([t["name"] for t in m.teams].index(team), pts, note)
        self.ov.mboard.refresh()
        self.update_match_label()

    def match_new(self):
        if QMessageBox.question(self, "New match", "Forget all races and rulings of this match?\n"
                                "The teams, players and drafted umas stay.") == QMessageBox.StandardButton.Yes:
            self.ov.match.new_match()
            self.ov.mboard.refresh()
            self.update_match_label()

    def match_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save the match as .csv", "match.csv", "CSV (*.csv)")
        if path:
            self.ov.match.export_csv(path)

    def apply_sheet(self):
        ov = self.ov
        ov.s["standings_sheet"] = self.ed_sheet.text().strip()
        ov.s["standings_tab"] = self.ed_tab.text().strip()
        for k, ed in self.ed_cols.items():
            ov.s[k] = ed.text().strip().upper()
        ov.s["standings_first_row"] = int(self.sp_first.value())
        ov.save_settings()
        if ov.s.get("standings_mode") != "sheet":
            self.cmb_smode.setCurrentIndex(1)        # reading a sheet only makes sense in sheet mode
        ov.standings.refresh(True)
        self.set_sheet_status("Reading...")

    def set_sheet_status(self, text):
        """Green when the sheet was read, red when something needs fixing."""
        text = text or ""
        if text.startswith("OK"):
            css = "color:#6ee7b7;font-weight:700;"
        elif text and text != "Reading...":
            css = "color:#ff9aa8;font-weight:700;"
        else:
            css = ""
        self.lbl_sheet.setStyleSheet(css)
        self.lbl_sheet.setText(text)

    def apply_view(self):
        self.ov.set_standings_view(self.cmb_view.currentData())
        self.cmb_smode.blockSignals(True)
        self.cmb_smode.setCurrentIndex(1)
        self.cmb_smode.blockSignals(False)
        self.set_sheet_status("Reading...")

    def apply_rounds(self):
        ov = self.ov
        ov.s["standings_round_blocks"] = self.ed_blocks.text().strip().upper()
        ov.s["standings_total_cols"] = self.ed_total.text().strip().upper()
        ov.save_settings()
        ov.standings.refresh(True)
        ov.standings.apply_raw()
        self.set_sheet_status("Reading...")

    def choose_sheet_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the score file", os.path.expanduser("~"),
                                              "Score files (*.csv *.xlsx *.xlsm);;All files (*)")
        if path:
            self.ed_sheet.setText(path)
            self.apply_sheet()

    def update_book_label(self):
        b = self.ov.book
        if not b.races:
            self.lbl_book.setText("No race counted yet")
        else:
            self.lbl_book.setText("%d race%s counted  \u00b7  %d players" % (len(b.races), "" if len(b.races) == 1 else "s", len(b.totals())))

    def undo_race(self):
        self.ov.book.undo_last()
        self.ov.standings.refresh(True)
        self.update_book_label()

    def race_log(self):
        from .racedata import RaceLog
        if self.ov.racelog is None:
            from .constants import CONFIG_DIR
            self.ov.racelog = RaceLog(os.path.join(CONFIG_DIR, "race-data.jsonl"))
        return self.ov.racelog

    def update_race_data_label(self):
        n = self.race_log().count()
        self.lbl_rdata.setText("%d live race%s kept so far." % (n, "" if n == 1 else "s") if n else "No live race kept yet.")

    def make_skills_sheet(self, records, files=None):
        """Ask where to save, then write the spreadsheet of the skills the umas brought."""
        from .racedata import export_skills_xlsx, load_skills
        if not records:
            QMessageBox.information(self, "Skills spreadsheet", "No race found there.\nChoose race files (.json) saved by horseACT."
                                    if files is not None else "No live race is kept yet. Play a race first.")
            return
        start = os.path.join(self.ov.s.get("saved_races_dir") or os.path.expanduser("~"), "skills.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Save the spreadsheet", start, "Spreadsheet (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        skills = load_skills(self.ov.umdb_paths())
        try:
            export_skills_xlsx(path, records, skills)
        except OSError as e:
            QMessageBox.warning(self, "Skills spreadsheet", "Could not save the file:\n%s" % e)
            return
        umas = sum(len(r["runners"]) for r in records)
        known = sum(1 for r in records for u in r["runners"] if u.get("equipped"))
        note = ""
        if not skills:
            note += "\n\nNo umdb.json was found, so the skill names are missing (only the numbers)."
        if known < umas:
            note += "\n\n%d of %d umas had no skill list in the race data." % (umas - known, umas)
        QMessageBox.information(self, "Skills spreadsheet", "Saved %d race%s (%d umas) to:\n%s%s"
                                % (len(records), "" if len(records) == 1 else "s", umas, path, note))

    def _read_records(self, paths):
        from PyQt6.QtWidgets import QApplication
        from .racedata import records_from_paths
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            recs, n = records_from_paths(paths)
        finally:
            QApplication.restoreOverrideCursor()
        return recs, n

    def skills_from_files(self):
        start = self.ov.s.get("saved_races_dir") or os.path.expanduser("~")
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose your race files", start, "Race files (*.json);;All files (*)")
        if not paths:
            return
        self.ov.set_setting("saved_races_dir", os.path.dirname(paths[0]))
        recs, n = self._read_records(paths)
        self.make_skills_sheet(recs, n)

    def skills_from_folder(self):
        start = self.ov.s.get("saved_races_dir") or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Choose the folder with your race files (the folders inside are searched too)", start)
        if not folder:
            return
        self.ov.set_setting("saved_races_dir", folder)
        recs, n = self._read_records([folder])
        self.make_skills_sheet(recs, n)

    def skills_from_live(self):
        self.make_skills_sheet(self.race_log().records())

    def clear_race_data(self):
        if QMessageBox.question(self, "Delete", "Delete all saved race data? This cannot be undone.") != QMessageBox.StandardButton.Yes:
            return
        self.race_log().clear()
        self.update_race_data_label()

    def update_sheet_status(self):
        self.lbl_wstat.setText(self.ov.sheet_status or "Nothing sent yet.")

    def copy_sheet_script(self):
        import secrets
        from .sheetwrite import APPS_SCRIPT
        code = self.ed_wsec.text().strip()
        if not code:                                   # make the secret for the person, no typing needed
            code = secrets.token_hex(6)
            self.ed_wsec.setText(code)
            self.ov.set_setting("sheet_write_secret", code)
        QApplication.clipboard().setText(APPS_SCRIPT.replace('var SECRET = "CHANGE-ME";', 'var SECRET = "%s";' % code))
        QMessageBox.information(self, "Script copied", "The script is copied and your secret code is already inside.\n\n"
                                "1. In your Google Sheet: Extensions > Apps Script. Delete what is there, paste (Ctrl+V), Save.\n"
                                "2. Deploy > New deployment > Web app. Execute as: Me. Who has access: Anyone.\n"
                                "3. Copy the Web app link and paste it in the Web app link box.")

    def test_sheet_link(self):
        from . import sheetwrite
        self.ov.set_setting("sheet_write_url", self.ed_wurl.text().strip())
        try:
            res = sheetwrite.ping(self.ed_wurl.text())
        except Exception as e:
            self.lbl_wstat.setText("The link does not work: %s" % e)
            return
        self.lbl_wstat.setText("The link works." if res.get("ok") else "The link answered, but not like the script.")

    def send_sheet_now(self):
        for key, ed in (("sheet_write_url", self.ed_wurl), ("sheet_write_secret", self.ed_wsec)):
            self.ov.set_setting(key, ed.text().strip())
        self.ov.sheet_send()

    def save_races_file(self):
        if not self.ov.book.races:
            QMessageBox.information(self, "Races", "No race is counted yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save the races", os.path.expanduser("~/cup-races.json"), "Races file (*.json)")
        if path:
            try:
                self.ov.book.export_races(path)
            except OSError as e:
                QMessageBox.warning(self, "Races", "Could not save the file:\n%s" % e)

    def load_races_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add races from a file", os.path.expanduser("~"), "Races file (*.json)")
        if not path:
            return
        try:
            added, skipped = self.ov.book.import_races(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Races", "Could not read the file:\n%s" % e)
            return
        self.ov.standings.refresh(True)
        self.update_book_label()
        QMessageBox.information(self, "Races", "%d race%s added%s." % (added, "" if added == 1 else "s",
                                (", %d already counted or not valid (skipped)" % skipped) if skipped else ""))

    def export_scores(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save the points", os.path.expanduser("~/standings.csv"), "CSV (*.csv)")
        if path:
            self.ov.book.export_csv(path)

    def clear_scores(self):
        if QMessageBox.question(self, "New bracket", "Delete all counted points and start again?") == \
                QMessageBox.StandardButton.Yes:
            self.ov.book.clear()
            self.ov.standings.refresh(True)
            self.update_book_label()


    # ---- updates
    def ask_install(self, files, source, restart=True):
        try:
            new_ver = check_update_files(files)
        except ValueError as e:
            QMessageBox.warning(self, "Update", str(e))
            return False
        if version_tuple(new_ver) < version_tuple(APP_VERSION):
            q = "%s contains version %s, which is OLDER than your version %s.\nInstall it anyway?" % (source, new_ver, APP_VERSION)
        elif version_tuple(new_ver) == version_tuple(APP_VERSION):
            q = "%s is the same version as yours (%s).\nInstall it anyway?" % (source, new_ver)
        else:
            q = "Update from version %s to %s?" % (APP_VERSION, new_ver)
        q += "\n\nFiles: " + ", ".join(sorted(n for n in files if is_update_path(n)))
        q += "\nYour pictures and settings are kept. The old files are backed up first."
        if QMessageBox.question(self, "Update", q) != QMessageBox.StandardButton.Yes:
            return False
        if FROZEN:
            QMessageBox.information(self, "Update", "This Windows program is a packaged .exe, so it cannot replace "
                                    "its own files.\n\nDownload the new zip from the GitHub releases page, unzip it, "
                                    "and start it. Your pictures and settings are kept.")
            QDesktopServices.openUrl(QUrl(RELEASES_URL))
            return False
        try:
            replaced, backup = install_update(files, SCRIPT_DIR)
        except OSError as e:
            QMessageBox.warning(self, "Update", "Could not write the files:\n%s" % e)
            return False
        self.lbl_update.setText("Updated to %s (%d files). Backup: %s" % (new_ver, len(replaced), backup))
        if restart:
            QMessageBox.information(self, "Update", "Updated to version %s.\nThe program restarts now." % new_ver)
            self.ov.restart_now()
        return True

    def update_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the new version", os.path.expanduser("~"),
                                              "Update (*.zip *.py)")
        if not path:
            return
        try:
            files = read_update_file(path)
        except Exception as e:
            QMessageBox.warning(self, "Update", "Could not read that file:\n%s" % e)
            return
        self.ask_install(files, os.path.basename(path))

    def run_job(self, fn, on_done):
        self.job = Job(fn)
        self.job.done.connect(on_done)
        self.job.failed.connect(self.job_failed)
        self.job.start()

    def job_failed(self, msg):
        self.btn_check.setEnabled(True)
        self.lbl_update.setText("Update problem: " + msg)

    def check_online(self):
        url = self.ed_url.text().strip()
        self.ov.set_setting("update_url", url)
        if not url:
            QMessageBox.information(self, "Update link", "Paste the update link (latest.json) first.")
            return
        self.btn_check.setEnabled(False)
        self.btn_install.setVisible(False)
        self.lbl_update.setText("Checking...")
        self.run_job(lambda: fetch_manifest(url), self.on_manifest)

    def on_manifest(self, m):
        self.btn_check.setEnabled(True)
        ver = str(m.get("version"))
        if version_tuple(ver) > version_tuple(APP_VERSION):
            self.pending = m
            notes = m.get("notes", "")
            self.lbl_update.setText("New version %s is available.%s" % (ver, ("\n" + notes) if notes else ""))
            self.btn_install.setText("Install version %s" % ver)
            self.btn_install.setVisible(True)
        else:
            self.lbl_update.setText("You have the newest version (%s)." % APP_VERSION)

    def install_online(self):
        if not self.pending:
            return
        m = self.pending
        if FROZEN:                      # the packaged program updates itself with a helper
            self.ov.autoupdate.install(m)
            return
        self.btn_install.setEnabled(False)
        self.lbl_update.setText("Downloading...")

        def got(files):
            self.btn_install.setEnabled(True)
            if self.ask_install(files, "The download"):
                self.btn_install.setVisible(False)
            else:
                self.lbl_update.setText("Update cancelled.")
        self.run_job(lambda: download_update(m), got)

    # ---- look helpers
    def swatch(self, btn, color):
        btn.setText(color)
        c = QColor(color)
        fg = "#000000" if c.lightness() > 128 else "#ffffff"
        btn.setStyleSheet("background-color:%s;color:%s;border:2px solid rgba(255,255,255,90);border-radius:10px;"
                          "padding:6px;font-weight:700;" % (color, fg))

    def sync_widgets(self):
        s = self.ov.s
        self.swatch(self.btn_bg, s["bg"])
        self.swatch(self.btn_tc, s["text_color"])
        self.swatch(self.btn_sc, s["sub_color"])
        self.swatch(self.btn_ac, s.get("accent") or "#f5c518")
        for key in getattr(self, "role_btn", {}):
            self.swatch_role(key)
            self.fill_role_font(key.replace("color", "font"), s.get(key.replace("color", "font"), ""))
        if hasattr(self, "sl_racer"):
            self.sl_racer.setValue(int(float(s.get("racer_scale", 1.0)) * 100))
        for key, b in self.pod_btns:
            self.swatch(b, s.get(key) or "#ffffff")
        self.lbl_size.setText("%d%%" % int(float(s["text_scale"]) * 100))

    def pick(self, key, btn):
        c = QColorDialog.getColor(QColor(self.ov.s[key]), self, "Choose colour")
        if c.isValid():
            self.ov.set_setting(key, c.name())
            self.swatch(btn, c.name())

    def swatch_role(self, key):
        v = self.ov.s.get(key) or ""
        b = self.role_btn[key]
        self.swatch(b, v or self.ov.s["text_color"])
        if not v:
            b.setText("Same as text colour")

    def pick_role(self, key, reset=False):
        if reset:
            self.ov.set_setting(key, "")
        else:
            c = QColorDialog.getColor(QColor(self.ov.s.get(key) or self.ov.s["text_color"]), self, "Choose colour")
            if not c.isValid():
                return
            self.ov.set_setting(key, c.name())
        self.swatch_role(key)

    def on_racer_size(self, v):
        self.lbl_racer.setText("%d%%" % v)
        self.ov.set_setting("racer_scale", v / 100.0)

    def fill_role_font(self, key, current):
        have = {f.lower(): f for f in QFontDatabase.families()}
        names = [have[n.lower()] for n in self.COMMON_FONTS if n.lower() in have]
        if current and current.lower() not in [n.lower() for n in names]:
            names.insert(0, current)
        cmb = self.role_cmb[key]
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItem("Same as the main font", "")
        for n in names:
            cmb.addItem(n, n)
            cmb.setItemData(cmb.count() - 1, QFont(n, 12), Qt.ItemDataRole.FontRole)
        cmb.addItem("More fonts...", "__more__")
        cmb.setCurrentIndex(max(0, cmb.findData(current or "")))
        cmb.blockSignals(False)

    def on_role_font(self, key):
        cmb = self.role_cmb[key]
        data = cmb.currentData()
        if data == "__more__":
            cur = self.ov.s.get(key, "")
            data = self.pick_font(cur) or cur
            self.fill_role_font(key, data)
        self.ov.set_setting(key, data or "")

    def on_theme(self, name):
        self.ov.apply_theme(name)
        self.sync_widgets()

    def save_look(self):
        from .constants import LOOK_KEYS
        path, _ = QFileDialog.getSaveFileName(self, "Save my look", "my-look.json", "Look files (*.json)")
        if not path:
            return
        data = {k: self.ov.s.get(k) for k in LOOK_KEYS}
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as e:
            QMessageBox.warning(self, "Save my look", "Could not save the file:\n%s" % e)

    def load_look(self):
        from .constants import LOOK_KEYS
        path, _ = QFileDialog.getOpenFileName(self, "Load a look", "", "Look files (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("not a look file")
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Load a look", "This is not a look file:\n%s" % e)
            return
        hexre = re.compile(r"^#[0-9a-fA-F]{6}$")
        shapes = {"picture_shape": ("circle", "rounded", "square"),
                  "row_style": ("default", "cards", "plain"),
                  "names": ("both", "trainer", "uma"),
                  "board_header": ("band", "line", "plain"),
                  "board_footer": ("band", "plain"),
                  "results_style": ("cards", "lines", "plain"),
                  "results_columns": ("auto", "1", "2")}
        for k in LOOK_KEYS:
            if k not in data:
                continue
            v = data[k]
            if k in ("bg", "text_color", "sub_color", "accent", "podium_1", "podium_2", "podium_3"):
                ok = isinstance(v, str) and hexre.match(v)
            elif k in shapes:
                ok = v in shapes[k]
            elif k in ("header_color", "racer_color"):
                ok = isinstance(v, str) and (v == "" or hexre.match(v))
            elif k in ("header_font", "racer_font"):
                ok = isinstance(v, str)
            elif k == "racer_scale":
                ok = isinstance(v, (int, float)) and not isinstance(v, bool) and 0.6 <= float(v) <= 1.6
            elif k in ("bg_opacity", "text_scale"):
                ok = isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 2.0
            elif k == "font":
                ok = isinstance(v, str)
            elif k == "results_winner":
                ok = isinstance(v, bool)
            elif k == "pictures":
                ok = isinstance(v, str) and v in [m for m, _ in self.ov.PICTURE_CHOICES]
            else:
                ok = False
            if ok:
                self.ov.set_setting(k, v)
        self.ov.rebuild_settings("Look")

    def on_header_size(self, v):
        self.lbl_hsize.setText("%d%%" % v)
        self.ov.set_setting("header_scale", v / 100.0)

    def on_size(self, v):
        self.lbl_size.setText("%d%%" % v)
        self.ov.set_setting("text_scale", v / 100.0)

    COMMON_FONTS = ("Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Georgia", "Calibri", "Consolas",
                    "Courier New", "Ubuntu", "Ubuntu Sans", "DejaVu Sans", "Noto Sans", "Roboto", "Open Sans",
                    "Liberation Sans", "Cantarell", "Inter", "Comic Sans MS", "Impact")

    def fill_fonts(self, current):
        """The font drop-down: Default, the common fonts this computer has, the current one, More fonts..."""
        have = {f.lower(): f for f in QFontDatabase.families()}
        names = [have[n.lower()] for n in self.COMMON_FONTS if n.lower() in have]
        if current and current.lower() not in [n.lower() for n in names]:
            names.insert(0, current)
        self.cmb_font.blockSignals(True)
        self.cmb_font.clear()
        self.cmb_font.addItem("Default font", "")
        for n in names:
            self.cmb_font.addItem(n, n)
            self.cmb_font.setItemData(self.cmb_font.count() - 1, QFont(n, 12), Qt.ItemDataRole.FontRole)   # each name in its own font
        self.cmb_font.addItem("More fonts...", "__more__")
        i = self.cmb_font.findData(current or "")
        self.cmb_font.setCurrentIndex(max(0, i))
        self.cmb_font.blockSignals(False)
        self.show_font_preview(current)

    def show_font_preview(self, name):
        f = QFont(name) if name else QFont(QApplication.font())
        f.setPointSize(14)
        f.setBold(True)
        self.lbl_fontprev.setFont(f)

    def pick_font(self, current):
        """Every font on this computer: type to search, each name is drawn in its own font, with a preview."""
        dlg = QDialog(self)
        dlg.setWindowTitle("More fonts")
        dlg.resize(420, 520)
        v = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("Type to search...")
        lst = QListWidget()
        prev = QLabel("1st  Inari One  +0.41  12:34.5")
        prev.setMinimumHeight(44)
        prev.setStyleSheet("padding:6px 10px; border:1px solid #3a3a5a; border-radius:8px;")
        for fam in sorted(set(QFontDatabase.families()), key=str.lower):
            it = QListWidgetItem(fam)
            it.setFont(QFont(fam, 12))
            lst.addItem(it)
            if fam == current:
                lst.setCurrentItem(it)

        def show(it, *_):
            if it is not None:
                pf = QFont(it.text())
                pf.setPointSize(16)
                pf.setBold(True)
                prev.setFont(pf)

        def narrow(text):
            for i in range(lst.count()):
                lst.item(i).setHidden(text.lower() not in lst.item(i).text().lower())

        lst.currentItemChanged.connect(show)
        lst.itemDoubleClicked.connect(lambda *_: dlg.accept())
        search.textChanged.connect(narrow)
        show(lst.currentItem())
        row = QHBoxLayout()
        ok, cancel = QPushButton("Use this font"), QPushButton("Cancel")
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        for w in (search, lst, prev):
            v.addWidget(w, 1 if w is lst else 0)
        v.addLayout(row)
        if dlg.exec() and lst.currentItem() is not None:
            return lst.currentItem().text()
        return None

    def on_font(self, *_):
        data = self.cmb_font.currentData()
        if data == "__more__":
            cur = self.ov.s.get("font", "")
            name = self.pick_font(cur)
            data = name or cur
            self.fill_fonts(data)
        self.ov.set_setting("font", data or "")
        self.show_font_preview(data or "")

    def reset(self):
        self.ov.reset_settings()
        s = self.ov.s
        self.cb_top.setChecked(s["on_top"])
        self.cb_hide.setChecked(bool(s.get("auto_hide", True)))
        self.cmb_slide.setCurrentIndex(0)
        self.cb_title.setChecked(s["title_bar"])
        self.cmb_avatar.setCurrentIndex(0)
        self.sl_op.setValue(int(s["bg_opacity"] * 100))
        self.sl_size.setValue(int(s["text_scale"] * 100))
        self.fill_fonts("")
        self.cb_arrows.setChecked(bool(s["rank_arrows"]))
        self.sp_rows.setValue(int(s["max_rows"]))
        self.cmb_style.setCurrentIndex(0)
        self.sp_crow.setValue(int(s["compact_rows"]))
        self.cmb_shape.setCurrentIndex(0)
        for cb in (self.cmb_rstyle, self.cmb_rcols, self.cmb_bhead, self.cmb_bfoot):
            cb.setCurrentIndex(0)
        self.cmb_rowstyle.setCurrentIndex(0)
        self.sync_widgets()

    def show_tab(self, name):
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i).replace(" (WIP)", "") == name:
                self._tabs.setCurrentIndex(i)
                return

    def poll(self):
        ov = self.ov
        dot = STATE_COLORS.get("green" if ov.racing else ov.state, "#f1c40f")
        if ov.racing:
            dot = "#3498db"
        self.lbl_state.setText('<span style="color:%s">&#9679;</span> %s' % (dot, ov.status_summary().replace("\n", " ")))
        if ov.auto_hide_active():
            self.btn_show.setText("Done placing: hide the window" if ov.pinned else "Show overlay window (to place it)")
            self.note_show.setText("Hidden until a race starts, then the tower slides in. Press the button to place the window.")
        else:
            self.btn_show.setText("Hide overlay window" if ov.isVisible() else "Show overlay window")
            self.note_show.setText("OBS can only see the window while it is shown.")
        self.btn_prev2.setText("Stop preview" if ov.preview else "Show preview race")
        self.btn_board.setText("Done placing: hide the results board" if ov.board.pinned
                               else "Show results board (to place it)")
        self.btn_stand.setText("Done placing: hide the standings board" if ov.standings.pinned
                               else "Show standings board (to place it)")
        self.btn_luck.setText("Done placing: hide the skill luck board" if ov.luck.pinned
                              else "Show skill luck board (to place it)")
        self.btn_match.setText("Done placing: hide the match board" if ov.mboard.pinned
                               else "Show match board (to place it)")
        if self.isVisible() and self._tabs.currentWidget() is self._draft_tab:
            self.update_match_label()
        if self.isVisible() and self._tabs.currentWidget() is self._stand_tab:
            self.set_sheet_status(ov.standings.status or "")
            self.update_book_label()
        self.cb_prev.blockSignals(True)
        self.cb_prev.setChecked(self.ov.preview)
        self.cb_prev.blockSignals(False)
        if self.isVisible() and self.ov.players.reload_if_changed():
            self.refresh_players()
        if self.isVisible() and self._tabs.currentWidget() is self._status_tab:
            self.refresh_status()
        if self.isVisible() and len(self.ov.pix) != self._uma_pix_count:
            self.refresh_umas()           # new faces have finished loading

    # ---- players helpers
    def selected(self):
        keys = self.selected_all()
        if not keys:
            QMessageBox.information(self, "Pick a trainer", "Click a trainer in the list first.")
            return None
        return keys[0]

    def selected_all(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]

    def filter_players(self, *_):
        text = self.ed_find.text().strip().lower()
        shown = 0
        for r in range(self.table.rowCount()):
            hay = " ".join((self.table.item(r, c).text() if self.table.item(r, c) else "") for c in (0, 1, 2, 3)).lower()
            hide = bool(text) and text not in hay
            self.table.setRowHidden(r, hide)
            shown += 0 if hide else 1
        self.lbl_count.setText("%d trainers" % shown if not text else "%d of %d" % (shown, self.table.rowCount()))

    def delete_trainers(self):
        keys = self.selected_all()
        if not keys:
            QMessageBox.information(self, "Pick a trainer", "Click a trainer in the list first (Ctrl or Shift + click for several).")
            return
        shown = ", ".join(keys[:5]) + (" ..." if len(keys) > 5 else "")
        if QMessageBox.question(self, "Delete trainers", "Delete %d trainer%s from the list?\n%s\n\nThe picture files stay in your "
                                "folder. A trainer that races again is added again." % (len(keys), "" if len(keys) == 1 else "s", shown)
                                ) != QMessageBox.StandardButton.Yes:
            return
        self.ov.players.remove_keys(keys)
        self.refresh_players()

    def refresh_players(self):
        keep = set(self.selected_all())
        rows = self.ov.players.rows()
        self.table.setSortingEnabled(False)               # fill first, sort after
        self.table.setRowCount(len(rows))
        for i, (name, d) in enumerate(rows):
            img = d.get("image", "")
            if not img:
                shown = "(uma face)"
            elif img.lower().startswith(("http://", "https://")):
                shown = "link: " + img
            else:
                shown = "file: " + os.path.basename(img)
            races = QTableWidgetItem()
            races.setData(Qt.ItemDataRole.DisplayRole, int(d.get("seen", 0)))       # a number: sorts as a number
            cells = (_NameItem(name), _NameItem(d.get("discord_name") or (d.get("aliases") or [""])[0]),
                     _NameItem(str(d.get("discord_id", ""))), _NameItem(d.get("club", "")),
                     races, _NameItem(d.get("last_uma", "")), _NameItem(shown))
            for c, it in enumerate(cells):
                it.setToolTip(it.text())
                self.table.setItem(i, c, it)
        self.table.setSortingEnabled(True)
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0) and self.table.item(r, 0).text() in keep:
                self.table.selectRow(r)
        self.filter_players()

    def choose_file(self):
        name = self.selected()
        if not name:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture for " + name, os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if path:
            self.ov.set_player_image_file(name, path)
            self.refresh_players()

    def paste_link(self):
        name = self.selected()
        if not name:
            return
        url, ok = QInputDialog.getText(self, "Picture link", "Link to a picture of %s (https://...):" % name)
        if ok and url.strip().lower().startswith(("http://", "https://")):
            self.ov.set_player_image_url(name, url.strip())
            self.refresh_players()
        elif ok:
            QMessageBox.warning(self, "Not a link", "The link must start with http:// or https://")

    def remove_pic(self):
        name = self.selected()
        if name:
            self.ov.clear_player_image(name)
            self.refresh_players()

    # ---- status tab
    CHECK_COLORS = {"ok": "#2ecc71", "bad": "#ff5c6c", "warn": "#f1c40f", "info": "#9aa0b4"}

    def log_text(self, max_lines=400):
        path = self.cmb_log.currentData()
        if path is None:
            return "\n".join(logbuf.lines()[-max_lines:])
        text = read_tail(path, max_lines, self.cb_fixme.isChecked())
        return text or "(no log yet: %s)" % path

    def refresh_status(self):
        rows = []
        for state, title, hint in run_checks(self.ov):
            line = '<span style="color:%s">&#9679;</span> %s' % (self.CHECK_COLORS.get(state, "#9aa0b4"), title)
            if hint:
                line += '<br><span style="color:#9aa0b4">&nbsp;&nbsp;&nbsp;&nbsp;%s</span>' % hint
            rows.append(line)
        html = "<br>".join(rows)
        _chk = run_checks(self.ov)
        _n = sum(1 for st, _t, _h in _chk if st in ("bad", "warn"))
        self.lbl_sum.setText('<span style="color:#2ecc71">&#10004;</span> Everything looks fine' if not _n else
                             '<span style="color:#f1c40f">&#9888;</span> %d thing%s to look at' % (_n, "" if _n == 1 else "s"))
        if html != getattr(self, "_checks_html", None):
            self._checks_html = html
            self.lbl_checks.setText(html)
        text = self.log_text()
        if text == getattr(self, "_log_shown", None):
            return
        self._log_shown = text
        sb = self.txt_log.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        keep = sb.value()
        self.txt_log.setPlainText(text)
        sb.setValue(sb.maximum() if at_bottom else keep)

    def copy_status(self):
        parts = ["%s %s" % (APP_NAME, APP_VERSION)]
        for state, title, hint in run_checks(self.ov):
            parts.append("[%s] %s%s" % (state, title, (" - " + hint) if hint else ""))
        parts.append("")
        parts.append("--- %s ---" % self.cmb_log.currentText())
        parts.append(self.log_text(80))
        QApplication.clipboard().setText("\n".join(parts))
        self.btn_copy.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.btn_copy.setText("Copy for support"))

    # ---- share pictures
    def import_pics(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the pictures zip", os.path.expanduser("~"),
                                              "Zip (*.zip)")
        if path:
            self.import_zip(path)

    def import_zip(self, path):
        from .images import LAST_PACK
        LAST_PACK["players"], LAST_PACK["clubs"], LAST_PACK["same_names"] = 0, [], []
        try:
            n = import_pictures(path, self.ov.images_dir)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Pictures", str(e))
            return
        clubs = LAST_PACK["clubs"]
        extra = ""
        if LAST_PACK["players"]:
            extra = "\n%d players got their picture." % LAST_PACK["players"]
            if clubs:
                extra += "\n%d clubs found: %s%s." % (len(clubs), ", ".join(clubs[:8]), ", ..." if len(clubs) > 8 else "")
                if not self.ov.s.get("show_club", False):
                    extra += "\n(Look > Tower > Club shows them in the tower.)"
        if LAST_PACK.get("same_names"):
            extra += "\n\n%d in-game names belong to two players (%s): both are listed, the first one is used in the race." % (
                len(LAST_PACK["same_names"]), ", ".join(LAST_PACK["same_names"][:5]))
        QMessageBox.information(self, "Pictures", "%d pictures were added to:\n%s\n%s\n\nThe program restarts now so "
                                "that it can use them." % (n, self.ov.images_dir, extra))
        from .updater import restart_program
        restart_program()

    # drag a pictures zip onto this window to import it
    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(".zip") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".zip"):
                e.acceptProposedAction()
                QTimer.singleShot(0, lambda p=u.toLocalFile(): self.import_zip(p))
                return

    def export_pics(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save my pictures as a zip",
                                              os.path.join(os.path.expanduser("~"), "my-pictures.zip"), "Zip (*.zip)")
        if not path:
            return
        try:
            n = export_pictures(self.ov.images_dir, path)
        except OSError as e:
            QMessageBox.warning(self, "Pictures", str(e))
            return
        QMessageBox.information(self, "Pictures", "%d pictures saved in:\n%s\n\nSend this zip to a friend "
                                "privately. Do not put it on GitHub: the uma pictures are Cygames' art." % (n, path))

    # ---- uma pictures helpers
    def add_all_umas(self, silent=False):
        """Every uma of the game list (umdb.json) and every uma that has a picture here, so none is missing."""
        ov = self.ov
        items = dict(ov.outfits.titles.all_cards())
        names = {}
        for card, e in ov.umas.data.items():
            names[int(e.get("chara_id") or int(card) // 100)] = e.get("name", "")
        for card, chara in ov.thumbs.all_cards().items():
            items.setdefault(card, names.get(chara) or ov.outfits.titles.charas.get(chara, "") or "Uma %d" % chara)
        n = ov.umas.add_many(items)
        if n or not silent:
            self.refresh_umas()
        if not silent:
            QMessageBox.information(self, "Umas", "%d umas were added (%d in the list now).%s" % (
                n, len(ov.umas.data), "" if items else "\n\nNo umdb.json and no uma pictures were found, so there was nothing to add."))

    def refresh_umas(self):
        ov = self.ov
        if not getattr(self, "_umas_filled", False):          # the first time: put every known uma in the list
            self._umas_filled = True
            ov.umas.add_many({c: n for c, n in dict(ov.outfits.titles.all_cards()).items()})
        keep = None
        r = self.utable.currentRow()
        if r >= 0 and self.utable.item(r, 2):
            keep = self.utable.item(r, 2).text()
        rows = ov.umas.rows()
        self.utable.setRowCount(len(rows))
        for i, (card, chara, name, seen) in enumerate(rows):
            key = "c:%d" % card
            if key not in ov.pix and key not in ov.pix_pending:
                ov.want_img(key, {"kind": "uma", "card_id": card, "chara_id": chara, "name": name})
            face = QTableWidgetItem()
            pm = ov.pix.get(key)
            if pm is not None and not pm.isNull():
                face.setIcon(QIcon(pm))
            own = ov.uma_own_picture(card)
            shown = "mine: " + os.path.basename(own) if own else ("default" if ov.thumbs.use_default else "(none)")
            self.utable.setItem(i, 0, face)
            for c, text in enumerate((ov.uma_full_name(card, chara, name), str(card), shown), start=1):
                self.utable.setItem(i, c, QTableWidgetItem(text))
            if str(card) == keep:
                self.utable.selectRow(i)
        self._uma_pix_count = len(ov.pix)

    def selected_uma(self):
        r = self.utable.currentRow()
        it = self.utable.item(r, 2) if r >= 0 else None
        if it is None:
            QMessageBox.information(self, "Pick a uma", "Click a uma in the list first.")
            return None, ""
        return int(it.text()), self.utable.item(r, 1).text()

    def choose_uma_file(self):
        card, name = self.selected_uma()
        if not card:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture for " + name, os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if path:
            self.ov.set_uma_image_file(card, path)
            self.refresh_umas()

    def remove_uma_pic(self):
        card, _ = self.selected_uma()
        if card:
            self.ov.clear_uma_image(card)
            self.refresh_umas()

    def add_uma(self):
        text, ok = QInputDialog.getText(self, "Add uma", "Card id (a number like 100101):")
        if not ok or not text.strip().isdigit():
            if ok:
                QMessageBox.warning(self, "Not a number", "The card id is a number, for example 100101.")
            return
        card = int(text.strip())
        name, ok = QInputDialog.getText(self, "Add uma", "Name of the uma:")
        if ok and name.strip():
            self.ov.umas.add(card, name.strip())
            self.refresh_umas()

    def add_trainer(self):
        name, ok = QInputDialog.getText(self, "Add trainer", "Trainer name (exactly as shown in the race):")
        if ok and name.strip():
            self.ov.players.add(name.strip())
            self.refresh_players()

    def closeEvent(self, ev):
        if self.ov.preview:
            self.ov.set_preview(False)
        ev.accept()
