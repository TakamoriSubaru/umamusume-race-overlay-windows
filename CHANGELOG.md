# Changelog

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
