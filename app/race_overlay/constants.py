"""Names, version, layout numbers, colours, default settings."""

import os
import sys
import tempfile


IS_WINDOWS = sys.platform == "win32"
PLATFORM = "Windows"                                 # shown in the window names (this is the Windows project)
REPO = "TakamoriSubaru/umamusume-race-overlay-windows"
RELEASES_URL = "https://github.com/%s/releases/latest" % REPO
FROZEN = bool(getattr(sys, "frozen", False))         # True in the packaged Windows program (.exe)
TMP_DIR = tempfile.gettempdir() if IS_WINDOWS else "/tmp"     # logs and the "server started" marker


APP_NAME = "Umamusume Race Overlay (%s)" % PLATFORM


STANDINGS_NAME = "Umamusume Standings (%s)" % PLATFORM     # window name of the standings board (pick it in OBS)
MATCH_NAME = "Umamusume Match (%s)" % PLATFORM            # window name of the team match board (pick it in OBS)
LUCK_NAME = "Umamusume Skill Luck (%s)" % PLATFORM        # window name of the skill luck board (pick it in OBS)
RESULTS_NAME = "Umamusume Race Results (%s)" % PLATFORM   # window name of the results board (pick it in OBS)


APP_VERSION = "2.3.0"


SLIDE_SECONDS = 0.45       # how long the tower takes to slide in / out


BASE_W = 310


ROW_H = 48


HEADER_H = 66


FOOT_PAD = 8

# the compact "corner" tower (Look tab: Tower style)
COMPACT_W = 250
COMPACT_ROW_H = 34
COMPACT_HEADER_H = 36
CLOCK_HEADER_H = 34          # the header when only the clock is shown


STYLE_COLOR = {1: "#5ca1e5", 2: "#a6db24", 3: "#ffdf31", 4: "#ffb538"}


STYLE_LABEL = {1: "F", 2: "P", 3: "L", 4: "E"}


WAKU_COLORS = ["#ffffff", "#453b33", "#f86a6a", "#5ea2e9",
               "#ffdd33", "#74d27c", "#ffb432", "#f381a2"]


WAKU_DARK = {0, 4}


PODIUM = ["#d4a017", "#a8a8b8", "#b87040"]


if IS_WINDOWS:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "race-overlay-native")
else:
    CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "race-overlay-native")


CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
if FROZEN:      # the packaged Windows program: icon.png and the images folder sit next to the .exe
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(PACKAGE_DIR)   # the program folder (next to race_overlay_native.py)


def _default_images_dir():
    """Where your pictures live. The packaged Windows program keeps them in the settings folder, so a new
    version never loses them. An 'images' folder next to the .exe (version 1.0.0) is still used if it has files."""
    if not FROZEN:
        return os.path.join(SCRIPT_DIR, "images")
    old = os.path.join(SCRIPT_DIR, "images")
    new = os.path.join(CONFIG_DIR, "images")
    if not os.path.isdir(new) and os.path.isdir(old) and any(os.scandir(old)):
        return old
    return new


IMAGES_DIR = _default_images_dir()


IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


TRACK_NAMES = {10001: "Sapporo", 10002: "Hakodate", 10003: "Niigata", 10004: "Fukushima",
               10005: "Nakayama", 10006: "Tokyo", 10007: "Chukyo", 10008: "Kyoto",
               10009: "Hanshin", 10010: "Kokura"}


DEFAULT_SETTINGS = {
    "on_top": True,            # keep the overlay above other windows
    "title_bar": False,        # False = clean window without the title bar
    "show_overlay": False,     # is the overlay window shown? (remembered between starts)
    "stop_server": True,       # quitting the overlay also closes the Race Overlay server the start script started
    "open_menu": True,         # open the Menu window when the program starts
    "auto_update_check": True,   # tell me (a window) when a new version is out; checked when the program starts
    "race_data": True,           # save the results and skills of every race (race-data.jsonl)
    "sheet_write_url": "",       # the Web app link of the Apps Script in the Google Sheet
    "sheet_write_secret": "",    # the secret code written in that script
    "sheet_write_round": 1,      # which "Group Stage Round N" tab gets the placings
    "sheet_write_auto": False,   # send every counted race by itself
    "seen_version": "",          # the last version whose "What's new" window was shown
    "update_skip": "",           # a version number you chose "Skip this version" for
    "update_url": "https://github.com/TakamoriSubaru/umamusume-race-overlay-windows/releases/latest/download/latest.json",  # "Check online" link
    "default_faces": True,     # use the faces found in Race Overlay when you have not chosen a picture
    "row_gate": True,          # tower row: the gate number badge (full tower)
    "row_style": True,         # tower row: the running style badge F / P / L / E (full tower)
    "row_gap": "both",         # tower row: "both" (seconds and length), "time", "length" or "none"
    "header_scale": 1.0,       # size of the tower header (track info + clock) on its own, 1.0 = normal
    "header_font": "",         # font of the tower header ("" = the main font)
    "header_color": "",        # colour of the header text ("" = the text colour)
    "racer_font": "",          # font of the names in the tower rows ("" = the main font)
    "racer_scale": 1.0,        # size of the names in the tower rows on their own, 1.0 = normal
    "racer_color": "",         # colour of the names in the tower rows ("" = the text colour)
    "header_clock": "auto",    # "auto" = lower line only when the track info does not fit, "right" = next to the track info, "below" = on the lower line
    "tower_header": "both",    # "both" = track info and clock, "clock" = clock only, "none"
    "players_only": False,     # tower: hide umas that have no trainer name (NPCs)
    "show_club": False,        # a small "· Club" after the uma line (clubs come from a player pictures zip)
    "name_source": "ingame",   # which name of a player is shown: "ingame" (the trainer name of the race) or "discord" (his Discord name, from the pictures zip)
    "strip_tags": False,       # names: "CLUB｜Name" shows as "Name"
    "tower_team_color": True,  # tower: a team colour stripe for the players of a draft team
    "podium_1": "#d4a017",     # colour of 1st place (tower rank, results board)
    "podium_2": "#a8a8b8",     # 2nd
    "podium_3": "#b87040",     # 3rd
    "picture_shape": "circle", # "circle", "rounded" or "square"
    "row_style": "default",    # tower rows: "default" (podium lines), "cards" (a card behind every row) or "plain"
    "names": "both",           # what the rows say: "both" = trainer and uma, "trainer" = trainer only, "uma" = uma only
    "pictures": "both",        # "both" = uma image + small player picture, "uma" = uma image only,
                               # "player" = player picture in the big circle (uma image if the player has none)
    "bg": "#090912",
    "bg_opacity": 1.0,
    "text_color": "#ffffff",
    "sub_color": "#9898b8",
    "text_scale": 1.0,
    "font": "",                # "" = default font
    # --- saved races (Data tab) - these are NOT touched by "Reset look to defaults"
    "saved_races_dir": "",     # the folder you last picked race files from (for the file windows)
    "simple_mode": False,      # (kept in step with level) True for the Tower version
    "level": "",               # "tower", "advanced" or "tournament" ("" = tournament: everything)
    # --- when the overlay shows
    "auto_hide": True,         # window is hidden until a race starts, hidden again after it
    "slide": "auto",           # slide in from: "auto" (the side the window is on), "left", "right", "off"
    # --- tower
    "tower_style": "full",     # "full" = the whole tower, "compact" = a small corner tower with only the top umas
    "compact_rows": 5,         # compact tower: how many umas are shown
    "rank_arrows": True,       # small up / down arrow when a uma gains or loses a place
    "max_rows": 0,             # show only the top N umas in the tower (0 = all of them)
    "accent": "#f5c518",       # accent colour (results board title line and track name)
    # --- results board (the window that shows after the race)
    "results_board": True,     # show the results board after each race
    "results_seconds": 10.0,   # how long it stays (0 = until the next race starts)
    # --- points and standings board (Points tab)
    "scoring": True,           # give points after every race: 1st = number of players, last = 1
    "standings_board": True,   # show the standings board after the results board, until the next race
    "standings_mode": "local", # "local" = points counted by this program, "sheet" = read from a sheet
    "standings_sheet": "",     # Google Sheets link, or a .csv / .xlsx file
    "standings_tab": "",       # .xlsx only: name of the sheet tab ("" = the first one)
    "standings_name_col": "B", # sheet columns (letters) and the first row with a player
    "standings_score_col": "D",
    "standings_uma_col": "C",
    "standings_first_row": 4,
    "standings_view": "plain", # sheet: "plain" = the columns above, or r1 / r2 / r3 / r12 / r123 (rounds)
    "standings_round_blocks": "auto",   # round views: "auto" finds the tables by their headers, or type the player, uma, points columns of round 1; 2; 3
    "standings_total_cols": "auto",     # combined views: "auto", or the player, round 1, round 2, round 3 columns (Q,R,S,T)
    "standings_layout": "portrait",   # "portrait" = one column, "landscape" = two columns side by side
    "standings_avatars": True,        # a picture for every player (from the People tab (Players), else a letter)
    "standings_every": 1,             # show the standings after every N races (0 = only when I show them)
    "start_race_overlay": True,       # Windows: start Race Overlay's server when Uma Musume runs
    "race_overlay_dir": "",           # Windows: the folder with Race Overlay.exe ("" = look for it)
    "race_overlay_start": "server",   # Windows: "server" (only server.exe), "app" (the whole program) or "both"
    "results_delay": 0.0,             # extra seconds before the results board comes in
    "luck_when": "after",             # "after" = once the board before it has gone, "with" = together with the results board
    "luck_delay": 0.0,                # extra seconds for the luck board
    "match_when": "after",
    "match_delay": 0.0,
    "standings_when": "after",
    "standings_delay": 0.0,
    "match_mode": False,              # team match (draft): points go to teams, not to single players
    "match_board": True,              # show the match board after the results board
    "match_seconds": 0.0,             # how long the match board stays (0 = until the next race)
    "match_title": "",                # own title for the match board ("" = TEAM MATCH)
    "match_show_races": True,         # match board: the points of every race (off = only the score)
    "match_show_picks": True,         # match board: the umas each team drafted
    "luck_board": False,              # show the skill luck board (luckiest / unluckiest) after the results board
    "results_title": "",              # own title for the results board ("" = RACE RESULTS)
    "board_header": "band",           # all boards: top strip "band" (strip + accent bar), "line" (accent line) or "plain"
    "board_footer": "band",           # all boards: bottom strip "band" or "plain"
    "results_style": "cards",         # results board rows: "cards", "lines" or "plain"
    "results_columns": "auto",        # results board: "auto" (one column up to 6 umas), "1" or "2"
    "results_winner": True,           # results board: the winner's row is tinted in the accent colour
    "results_details": "both",        # results board: "both" (time + gap), "time", "none"
    "luck_title": "",                 # own title for the luck board ("" = SKILL LUCK)
    "luck_seconds": 10.0,             # how long the luck board stays (0 = until the next race)
    "luck_rows": 3,                   # players shown on each side of the luck board
    "quick_start_open": True,         # Home tab: quick start box open
    "standings_hide_zero": True,        # sheet: players with 0 points are not shown
    "standings_border_values": "9,8,7",  # single rounds: this many points = gold, silver, bronze border
    "standings_top_n": 10,     # combined views and local points: the best N players get a gold border (0 = off)
    "standings_title": "STANDINGS",
    "standings_rows": 8,       # players per page
    "standings_page_seconds": 6.0,   # time per page while it cycles through everybody
    "standings_refresh": 60,   # sheet: seconds between reloads
}


KEEP_ON_RESET = ("simple_mode", "level", "saved_races_dir", "auto_hide",
                 "update_url", "auto_update_check", "update_skip", "seen_version",
                 "race_data", "sheet_write_url", "sheet_write_secret", "sheet_write_round", "sheet_write_auto", "open_menu", "stop_server", "show_overlay", "results_board", "results_seconds", "default_faces",
                 "scoring", "standings_board", "standings_mode", "standings_sheet", "standings_tab",
                 "standings_name_col", "standings_score_col", "standings_uma_col", "standings_first_row",
                 "standings_view", "standings_round_blocks", "standings_total_cols", "standings_border_values",
                 "standings_top_n", "standings_hide_zero", "standings_layout", "standings_avatars", "standings_every",
                 "standings_title", "standings_rows", "standings_page_seconds", "standings_refresh", "quick_start_open", "luck_board",
                 "luck_seconds", "match_mode", "match_board", "match_seconds", "match_title", "match_show_races", "match_show_picks",
                 "start_race_overlay", "race_overlay_dir", "race_overlay_start",
                 "results_delay", "luck_when", "luck_delay", "match_when", "match_delay", "standings_when", "standings_delay")


# Colour sets for the Look tab. Each one only changes colours.
THEME_PRESETS = {
    "Midnight (default)":       {"bg": "#090912", "text_color": "#ffffff", "sub_color": "#9898b8", "accent": "#f5c518"},
    "Charcoal and gold":        {"bg": "#14161a", "text_color": "#ffffff", "sub_color": "#a9adb5", "accent": "#f5c518"},
    "Sakura":                   {"bg": "#2a1722", "text_color": "#fff0f6", "sub_color": "#e0a3bd", "accent": "#ff7eb6"},
    "Mint":                     {"bg": "#0f2421", "text_color": "#effff9", "sub_color": "#8fcfbf", "accent": "#4fe3b5"},
    "Daylight":                 {"bg": "#f3f4f8", "text_color": "#1a1a28", "sub_color": "#5a5a72", "accent": "#c0392b"},
    "High contrast":            {"bg": "#000000", "text_color": "#ffffff", "sub_color": "#d0d0d0", "accent": "#ffff00"},
    "Ocean":                    {"bg": "#0a1a2b", "text_color": "#eaf6ff", "sub_color": "#8fb4d4", "accent": "#3fb8ff"},
    "Sunset":                   {"bg": "#2a1218", "text_color": "#fff3ec", "sub_color": "#e0a58f", "accent": "#ff8a3d"},
    "Forest":                   {"bg": "#101d14", "text_color": "#f0fff2", "sub_color": "#93bf9c", "accent": "#7bd35a"},
    "Grape":                    {"bg": "#1b1030", "text_color": "#f6eeff", "sub_color": "#b9a2dc", "accent": "#b57bff"},
    "Neon":                     {"bg": "#05050a", "text_color": "#f2fffb", "sub_color": "#7fe9d5", "accent": "#00ffd0"},
    "Paper":                    {"bg": "#efe9dc", "text_color": "#2b261d", "sub_color": "#7a705e", "accent": "#b5651d"},
    "Ice":                      {"bg": "#e8f1f8", "text_color": "#12263a", "sub_color": "#56708a", "accent": "#1b7fd1"},
    "Mono":                     {"bg": "#1b1b1b", "text_color": "#f2f2f2", "sub_color": "#9a9a9a", "accent": "#ffffff"},
}


# the settings that make up "my look" (Save my look / Load a look in the Look tab)
LOOK_KEYS = ("bg", "bg_opacity", "text_color", "sub_color", "accent", "text_scale", "font",
             "header_scale", "header_font", "header_color", "racer_font", "racer_scale", "racer_color", "header_clock", "show_club", "name_source", "podium_1", "podium_2", "podium_3", "picture_shape", "row_style", "pictures", "names",
             "board_header", "board_footer", "results_style", "results_columns", "results_winner")


ARROW_SECONDS = 2.5        # how long a position-change arrow stays
ARROW_AFTER = 3.0          # race seconds before arrows start (the gates opening shuffles everyone)


STATE_COLORS = {"green": "#2ecc71", "yellow": "#f1c40f", "red": "#e74c3c"}
