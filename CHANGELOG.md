# Changelog

## 1.0.13

- **The server files folder is now called `Server Files`.** Releases that include the server put it in a folder with that name next to the program.
- The program also finds a `Server Files` folder next to the program, in Documents, and anywhere it looked before. The old names (`server`, `Race Overlay`) still work.
- `Server Files/` is kept out of GitHub by `.gitignore`.

## 1.0.12

- **Fix: the Race Overlay server is closed when you close the overlay.**
  - It is closed whichever way you end the program: Quit in the menu, the window's close button, Ctrl+C, or closing its terminal.
  - On Windows it closes what the program started, together with anything it started.
  - Only `server.exe` is closed. A Race Overlay window you opened yourself stays open.

## 1.0.11

- **Cup Score tab, easier to use:**
  - The choice *Counted by this program* / *My Google Sheet* is now at the top, with a short explanation of both.
  - Google Sheet setup is **3 numbered steps** and a **Connect** button next to the link.
  - A **green / red status line** tells you if the sheet was read (and names the first players it found) or what to fix: not shared, wrong link, no internet.
- **Note:** how the sheet is read has not changed.

## 1.0.10

- **Settings window, more compact:** the tabs are smaller and sit in one tight row.
- **Tabs renamed:** *Race data* is now **Data**, and *Points* is now **Cup Score**. Nothing else changed; every setting is where it was.

## 1.0.9

- **New (Look tab), more ways to make it yours:**
  - **Colour sets are clickable chips** now, and there are 14 of them (new: Ocean, Sunset, Forest, Grape, Neon, Paper, Ice, Mono).
  - **Podium colours:** choose the colour of 1st, 2nd and 3rd place (tower rank and results board).
  - **Picture shape:** circle, rounded square or square.
  - **Tower row style:** lines (the top 3 underlined, as before), cards (a soft card behind every row, top 3 outlined) or plain.
  - **Save my look / Load a look:** keep your colours, text, pictures and row style in a small file, share it, load it back.
  - The Look tab is split into clearer boxes.
- **Note:** everything is as before until you change it.

## 1.0.8

- **New (Tower tab, *What the tower shows*):**
  - **Header:** track info and clock, clock only, or no header.
  - **Gap:** seconds and length, seconds only, length only, or no gap.
  - **Gate number** and **Running style (F / P / L / E)** can each be switched off (full tower). The names use the room that frees up.
  - **Players only:** umas without a trainer name (NPCs) are left out of the tower, and the window gets shorter.
  - **Club tags:** `CLUB｜Name` shows as `Name` in the tower, the results board and the skill luck board.
  - **Team colour:** with Team match mode on, the players of a draft team get a thin stripe in their team colour (full and small tower).
- **Note:** everything is as before until you change it.

## 1.0.7

- **Changed:** the server files are now **built in**. There is one download, `race-overlay-windows-X.Y.Z.zip`, and the `server` folder (Race Overlay) is already inside next to `UmaRaceOverlay.exe`. Unzip, start the program, start the game. The separate `-full` zip is gone.

## 1.0.6

- **Fixed:** in the small tower, when only one name is shown (Names shown: trainer only or uma only) the running style badge (F / P / L / E) is now centred in the row, level with the name. Before it sat higher than the name.

## 1.0.5

- **New:** a **full zip** (`race-overlay-windows-X.Y.Z-full.zip`) next to the plain one. It also holds the server files (Race Overlay) in a folder called `server` next to `UmaRaceOverlay.exe`, so the overlay finds the server by itself and nobody has to get anything else. Use the full zip when you have it; the plain zip is the program alone.

## 1.0.4

- **New:** match board **Race by race** switch (Draft tab, *Board*). Off = the board shows only the two team scores with their progress bars (and the drafted umas if you keep them on). Both switches off gives the smallest board.

## 1.0.3

- **New:** **Names shown** (Look tab): *Trainer and uma name*, *Trainer name only* or *Uma name only*. It changes the tower (full and small), the results board and the skill luck board. With one name, it is centred in the row.
- **Fixed (team match / draft):** players are now found even when the name is spelled a little differently: capitals, spaces, full-width letters and a club tag in front (`CLUB｜Name`, `[CLUB] Name`) no longer matter. Before, a player typed as `Name` was never found when the game said `CLUB｜Name`, so nothing scored.
- **New (team match):** the Draft tab now says why the last race did or did not score (*Counted*, *Team match mode is OFF*, *nobody in this race is on a team* with the names it saw, *a saved file that was already there when the program started*, *already scored*).
- **Fixed (server):** if the Race Overlay folder is not found, the overlay no longer gives up. It keeps looking every few seconds, so you can drop the folder in or choose it in the Home tab without a restart. The search also looks inside folders next to the program, in Documents, Downloads and Desktop (a few levels deep, any folder name), and the Help tab explains that Race Overlay is a separate program that must be there.
- **Fixed:** the live status text no longer mentions a Linux log file on Windows.

## 1.0.2

- **Fixed:** the uma faces are now also found when Race Overlay is in a folder you chose yourself (Home tab, *More*). Before, only the automatic places (Documents, Downloads, Desktop) were searched for its `resources\\character_thumbs` folder, so faces were missing with saved races.

## 1.0.1

- **New:** **Import pictures from a zip...** and **Save my pictures as a zip...** (Home tab, *More*). Make a zip of your uma and player pictures and send it to a friend privately; the friend imports it and the program restarts with the pictures. Existing pictures are kept and lists are merged.
- **Changed:** the pictures now live in `%APPDATA%\\race-overlay-native\\images`, so a new version never loses them and you no longer copy a folder when updating. An `images` folder next to the `.exe` (version 1.0.0) is still used until you import a zip.
- **Note:** the release itself never contains pictures (uma art belongs to Cygames, player pictures are private).

## 1.0.0

- **First release of the Windows version.** It is the Linux overlay (version 1.9.6) made into its own project for Windows, built as `UmaRaceOverlay.exe` by GitHub for every release (`race-overlay-windows-X.Y.Z.zip`). The Linux version continues in its own repository.
- **Includes:** the race tower (full or small corner), results board, points and standings board, skill luck board, team match (draft) board, the welcome guide with ready-made setups, and every setting tab.
- **Windows:** the overlay starts the original Race Overlay's server by itself once Uma Musume is running, tries again until it has found the game, and closes it when you quit. The folder with `Race Overlay.exe` is found automatically (Documents, Downloads, Desktop) or chosen in the Home tab (*More*).
- **Windows:** settings and logs live in `%APPDATA%\race-overlay-native`; a crash is written to `crash.log` there and shown in a message box.
- **Windows:** window names end in *(Windows)*, for example *Umamusume Race Overlay (Windows)*.
- **Note:** not tested on a real PC with the game yet. The packaged program cannot replace its own files; to update, download the new zip and copy your `images` folder into it.
