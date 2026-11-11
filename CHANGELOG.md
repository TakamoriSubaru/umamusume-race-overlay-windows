# Changelog

## 2.6.0

- **New: the analysis board** (a little like Hakuraku). After a race it shows a Table (top speed, stamina left, where an uma ran dry, time tempted or blocked, skills used / brought), line charts of Speed, Stamina, Gap to the leader and Lane, and a Skills timeline on the track. Click an uma to follow her on every page. It is a normal window you can click, and in OBS its own window; it can also change page by itself. Turn it on in the Data tab ("Open it after every race") or open it from the tray menu.

## 2.5.2

- **Points tab, easier sheet setup:** the column and round settings are folded into one "Sheet layout" box (the program finds them by itself). "Fill my sheet with the placings" now has four picture steps, and the secret code is made for you and put inside the copied script, so you do not type it.

## 2.5.1

- Cleaner Look and Help tabs. Fonts are folded away, and Help now says "Everything looks fine" or how many things to look at. The log is folded, and "Copy for support" stays in view.

## 2.5.0

- **Every tab is simpler, with pictures and fewer words:** Home has three picture cards for the version (Tower, Advanced, Tournament) and the start steps as three small picture cards, with a button that copies the window name for OBS. Data, People and Draft have a picture on top that shows what happens. Rarely used options are folded away (live races, the match board look, more colours).

## 2.4.0

- **Cup Score is now called Points, and much easier:** a picture at the top shows what happens (race ends, points added, shown on stream). Then two big choices: *This program counts* (nothing to set up) or *My Google Sheet* (three picture steps: share, copy the link, paste it). Everything else is folded away under short titles.

## 2.3.0

- **Pick your version and get a tutorial:** the first start now asks *Tower* (just the tower), *Advanced* (tower, results board and skill luck board) or *Tournament* (everything), then walks you through a short tutorial: start the game, preview, OBS, the boards, points, Look and People. Change the version any time with *Version* at the top of the Home tab, and open the tutorial again with *Setup guide and tutorial* (Home tab, More).
- Advanced hides the points, standings, match board, Cup Score and Draft. Tower also hides the Data tab and every board.

## 2.2.1

- **Simple version is slimmer:** the menu is a small window with only what you need (status, show overlay, preview, Look, People, Help). The quick start box is hidden.

## 2.2.0

- **Skills spreadsheet from your own race files:** *Data tab > Choose race files... / Choose a folder...* makes a spreadsheet of the skills every uma **brought** (with the level): *Who has what*, *Skill counts* (for example A Kiss for Courage: 2, and who) and *All skills*. The races you play live are kept too, with their own button. The old activated-skills spreadsheets are gone.
- **Always live, no more timers:** the *saved races* mode, its folder choice and the *Start delay* are removed. The overlay always follows the real race clock from Race Overlay's server, so it starts exactly when the race starts. A start script that still says `--watch` simply uses live mode.
- **Simple version:** tick *Simple version* at the top of the Home tab (or pick it in the first-start guide) and you get only the tower, People and Look (and Help). The boards, points, Draft and Data tab are hidden.

## 2.1.2

- **Shorter update windows:** the *New version available* and *Updated* windows are small and list what changed in a few short lines.
- **Skills spreadsheet in the Data tab:** the box *Skills of every race* (save the last race or all races as .xlsx) is now at the top of the *Data* tab instead of its own tab.

## 2.1.1

- **Send placings to your Google Sheet:** after each real race the program can write every player's placing into the *Placing* column of the *Group Stage Round* tab (Cup Score tab, *Send placings to the Google Sheet*), and your own formulas count the points. It needs a small script in the sheet, which the program copies for you (steps in the GUIDE). A placing that is already in the sheet is never overwritten, and previews or old files are never sent.
- **Race data for every race:** the program saves the results and every skill of every uma of each real race (the skills they brought, which ones activated, at what time and distance, and each skill's condition from Race Overlay's umdb.json). *Settings > Data > Skills of every race > Save the last race (.xlsx)* lists every skill of one race with the number of umas that brought it and who (for example *A Kiss for Courage: 2, Varrukas, Phedro*). *Save all races (.xlsx)* makes a spreadsheet of everything with the sheets Races, Runners, Skills and Skill summary. Skills that the server does not list as equipped show "unknown" in the Equipped column.
- **Cup Score reads more sheets:** a tab with the table *Name / Round 1 / Round 2 / Round 3 / Total* (like *Final Rankings Calc*) now works too. The player column can be called *Member*, *Name* or *Player*, and the Round 1, Round 2, Round 3 and Overall views all read from that table.

## 2.0.5

- **Cup Score: share your races.** *Save the races as a file...* and *Add races from a file...* (Cup Score tab, Points counted by this program). If Phedro counts rounds 1 and 2 and you count round 3, he sends you his file and you add it. A race you both counted is only counted once.
- **Player name option everywhere:** the Discord name / in-game name choice now also changes the names on the standings board (before it only changed the tower, the results board and the luck board).
- **What's new window:** the first time you start a newer version, a small window lists what changed (once).
- **Clear zip names:** the zip to download is now called `UmaRaceOverlay-Windows-X.Y.Z-DOWNLOAD-THIS.zip`. The other one is `...-auto-update-only.zip` (only the program's *Update now* button uses it), and the release page says which one to take.

## 2.0.4

- **No uma is missing in People > Umas:** the list now starts with every uma and outfit of the game (from Race Overlay's umdb.json, plus every uma that has a picture), not only the ones you have seen in a race. A new *Add all umas* button adds them again if you add pictures later.

## 2.0.3

- **Same person, one row:** rows that use the same picture file (or the same Discord id) are combined automatically, with the races added up. The other name still finds that player (for example *freakkiem* and *FREAK* become one row).

## 2.0.2

- **Right outfit in the tower:** the picture and name now follow the outfit the uma *wears* in the race, not the card she was trained with. A Summer Special Week shows as Summer Special Week, and Kitasan Black in her New Year outfit shows as New Year.
- **People > Players is a proper list:** columns for the trainer name, the Discord name, the Discord id, the club, the races and the last uma. Click a column title to sort (A-Z by name by default). A search box finds a trainer, Discord name or club. Select one or several trainers (Ctrl or Shift + click) and press *Delete trainer*.
- **Trainer and Discord name are connected:** a pictures zip from the bot now makes one row per player (matched by Discord id), and the Discord name also finds that player. Two players with the same in-game name are both kept, the second as *Name (discord name)*. The live race data only has the in-game name, so for two players with exactly the same name the program uses the first one.
- **The import button moved** from Home > More to People > Players (*Import pictures zip...* and *Save my pictures as a zip...*).
- **More customization (Look > Colours and pictures):** its own font and colour for the tower header, and its own font, size and colour for the racer names. *Same as text colour* goes back to normal. These are saved in *Save my look* too.

## 2.0.1

- **Easier player pictures and clubs:** drag a pictures zip (like the one Poorpel's bot makes) onto the settings window to import it. The message says how many players got a picture and which clubs were found. People > Players has a *Club* column, and *Look > Tower > Club* shows each player's club under their name.

## 2.0.0

A big update, so the version number jumps to 2.0.0.

- **The program tells you when there is a new version, and updates itself.** A few seconds after it starts it looks on GitHub; if there is a newer version a window asks *Update now / Later / Skip this version*. *Update now* downloads a small zip (without the server files), replaces the files, and starts the program again. Your settings, pictures and the Server Files folder are not touched. Turn it off in Home > More > *Tell me when a new version is out*.
- **Uma pictures in other outfits:** a picture named after the uma (or her character id) is her normal outfit and is no longer shown for Halloween, Summer and so on. Those outfits use their own picture (images/uma, Race Overlay's character_thumbs, or the server).
- **The tower header fits big text:** a long track name gets smaller instead of being cut, and the clock moves to the lower line by itself when the track info does not fit (Look > Tower > Clock: *Automatic*, or choose *Next to the track info* / *On the lower line*; *Header size* changes the whole header). Thanks Phedro for the idea.
- **Alts and special outfits show up by themselves** (for example *Summer Maruzensky*, shown as "Maruzensky (Summer)"). The program reads the official outfit names from Race Overlay's `umdb.json` (in `Server Files/resources`, or put a copy in your images folder). You no longer have to name them by hand.
- **Short names for event outfits:** Halloween, Summer, Christmas, New Year, Valentine, Wedding, Autumn, Cheerleader (Rice Shower's *Vampire Makeover!* now shows as *Halloween*). Other outfits show the official card name.
- **The People > Outfits tab is gone**, since the names come by themselves. A name you put in `images/outfits.json` (`"label"`) still wins.
- **Tower, Boards and Look are now one tab (Look)**, with *Colours and pictures*, *Tower* and *Boards* inside it (the same way as People).
- **People > Umas:** two outfits of one uma no longer look the same: *Inari One* and *Inari One Golden Dream* (short names such as *Festival* or *Summer* when the program knows them).
- **Font:** each name in the drop-down is drawn in its own font, there is a live preview line under it, and *More fonts...* is a window with search and a preview.
- 23 outfits have a built-in event name (for example *Inari One Festival*), from a list of the game's alts, so they are named even without `umdb.json`.
- If `umdb.json` is older than the game and does not know an outfit yet, it still says "Alt" until you update `umdb.json` or name it.

## 1.0.14

- **Look tab, Font:** a short drop-down of common fonts (the ones your computer has), with *Default font* first and *More fonts...* for the full list. No more scrolling through every font.
- **Draft tab is now labelled "Draft (WIP)"** (work in progress).
- **New (Boards tab), results board look:**
  - **Row style:** cards (as before), lines, or plain.
  - **Columns:** automatic (two columns above 6 umas), always one, or always two.
  - **Winner:** switch the accent tint on the winner's row on or off.
  - **Top strip / Bottom strip (all boards):** the dark strip and accent bar can be simplified. This also applies to the skill luck, standings and match boards.
- **Save my look / Load a look** (Look tab) now also keeps these.
- **Note:** everything is as before until you change it.

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
