"""Ready-made setups: one click switches the right boards on and the others off, so nobody has to find
twenty checkboxes. Each setup lists every setting it touches, so changing from one setup to another is clean.
Looks (colours, fonts, window position) and your folders are never touched."""

# the settings every setup sets, so that nothing of the setup before is left over
_OFF = {"results_board": False, "luck_board": False, "standings_board": False, "scoring": False,
        "match_mode": False,
        "luck_when": "after", "match_when": "after", "standings_when": "after"}

SETUPS = [
    {"key": "tower", "title": "Just the tower",
     "blurb": "The race tower while the race runs. Nothing after the race.",
     "settings": dict(_OFF), "tab": "Home"},
    {"key": "results", "title": "Tower and results",
     "blurb": "The tower, then a results board with the final places and times.",
     "settings": dict(_OFF, results_board=True), "tab": "Home"},
    {"key": "points", "title": "Points for every player",
     "blurb": "Results board, then a standings board. Every race gives points; the standings add them up. "
              "Can also read your own Google Sheet (Points tab).",
     "settings": dict(_OFF, results_board=True, scoring=True, standings_board=True), "tab": "Points"},
    {"key": "match", "title": "Team match (draft)",
     "blurb": "Two teams, 4 / 2 / 1 points per race, first to 25. A match board shows the score. "
              "Next: type the teams in the Draft tab.",
     "settings": dict(_OFF, results_board=True, match_mode=True, match_board=True), "tab": "Draft"},
    {"key": "all", "title": "Everything at once",
     "blurb": "Results, skill luck and standings boards all come in together after the race.",
     "settings": dict(_OFF, results_board=True, luck_board=True, scoring=True, standings_board=True,
                      luck_when="with", standings_when="with"), "tab": "Boards"},
]


def get_setup(key):
    for s in SETUPS:
        if s["key"] == key:
            return s
    return None


def current_setup(settings):
    """The key of the setup the settings match right now, or None when they were changed by hand."""
    for s in SETUPS:
        if all(settings.get(k, None) == v for k, v in s["settings"].items()):
            return s["key"]
    return None
