# Install and use guide (Windows)

For streamers who want the Uma Musume race tower and boards in OBS. No Python and no installer needed.

## 1. Download

1. Open the **[latest release](../../releases/latest)**.
2. Under **Assets**, click **`UmaRaceOverlay-Windows-X.Y.Z-DOWNLOAD-THIS.zip`**. It has everything, including the server. (Do not click "Source code".)
3. Right click the zip, **Extract All...**, and choose a folder such as `Documents`.
   Do not start the program from inside the zip.

## 2. Race Overlay (needed for live races: this is the server)

**Nothing to do here:** the zip you downloaded already has the server files inside, in the `Server Files` folder next to `UmaRaceOverlay.exe`. Skip to step 3.

The overlay reads live race data from the separate community tool **Race Overlay** (not included here).
Put its folder (the one with `Race Overlay.exe` and `resources`) **next to `UmaRaceOverlay.exe`**, or in your **Documents**, **Downloads** or **Desktop** folder. The overlay finds it in a few seconds (no restart) and starts its server when Uma Musume runs. The Help tab says what it sees.
Without it you can still use saved race files (see step 5).

## 3. Start it

1. Open the extracted folder and double click **`UmaRaceOverlay.exe`**.
2. If Windows says **Windows protected your PC**: click **More info**, then **Run anyway**. (The program is not signed.)
3. A welcome guide opens. Pick what you want to show (*Tower and results* suits most people) and the tower size.
4. Press **Show preview race** to see the tower with made-up umas.

## 4. Add it to OBS

1. In OBS: **Sources +**, **Window Capture**.
2. Set **Capture Method** to **Windows 10 (1903 and up)**.
3. Window: **Umamusume Race Overlay (Windows)**.
4. The boards are separate windows. Add one more Window Capture for each board you use:
   *Umamusume Race Results (Windows)*, *Umamusume Standings (Windows)*, *Umamusume Skill Luck (Windows)*, *Umamusume Match (Windows)*.
5. In the overlay, Home tab, press **Show overlay window** so OBS can see it, and use the *Show ... board (to place it)* buttons to put each board where you want it.

Black or solid background in OBS? Start the program with `--chroma` (right click your shortcut, Properties, add ` --chroma` at the end of *Target*) and add a **Chroma Key** filter in OBS.

## 5. Play

1. Start **Uma Musume**. The overlay waits for it and starts Race Overlay's server by itself. The dot in the Home tab turns **green** when it is ready.
2. Run a race. The tower slides in, then the boards after the race.
3. No Race Overlay? Choose your saved races folder in the **Race data** tab instead.

Use *Windowed* or *Borderless windowed* in the game's graphics settings. A true fullscreen game hides windows that stay on top.

## 6. Pictures of umas and players

The release does not contain pictures (the uma art belongs to Cygames). If someone gave you a **pictures zip**:
People tab, **Players**, **Import pictures zip...**, choose the zip. The program restarts and shows them.
To share your own pictures: **Save my pictures as a zip...** and send the file privately (not on GitHub).

## 7. Change what is shown

Home tab, **Setup**: *Just the tower*, *Tower and results*, *Points for every player*, *Team match (draft)*, *Everything at once*.
The other tabs change looks, timing and the points or team rules.

## 8. Update

Download the new zip and extract it. Your settings and pictures are kept automatically (in `%APPDATA%\\race-overlay-native`).

## Problems?

- Home tab, **Help**: runs checks (game running, Race Overlay found, server answering) and shows the log.
- If the program will not start, open `%APPDATA%\race-overlay-native\crash.log` (paste that into the Windows Explorer address bar) and attach it to an issue.
