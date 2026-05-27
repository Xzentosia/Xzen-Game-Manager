<div align="center">

# Xzen Game Compressor - Higanbana

**A Windows game storage utility for NTFS compression, decompression verification, and FSR package management.**

![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-41CD52?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-In%20Development-B38AFF?style=for-the-badge)
![Codename](https://img.shields.io/badge/Codename-Higanbana-B38AFF?style=for-the-badge)

</div>

---

## About

**Xzen Game Compressor - Higanbana** is a Windows desktop app for reducing game install size using native NTFS compression.

It scans installed games, shows original and compressed sizes, tracks saved space, and can safely decompress games back to normal when needed.

> [!IMPORTANT]
> The compression system uses Windows `compact.exe` with built-in NTFS compression algorithms.

> It does **not** repack, crack, delete, or rewrite game archives. FSR management is separate and only replaces DLL files.

## Stats:
<img width="1920" height="1080" alt="29 98GB (2)" src="https://github.com/user-attachments/assets/c9db3e98-6906-4414-901f-4e7324dc665a" />

## Xzen Compressor vs Competitor - Saved Storage Comparison
Compared to another compressor's public saved-storage claim, Xzen Compressor saved more storage across the currently matched games.

| Game | Other Compressor Saved | Xzen Compressor Saved | Difference |
|---|---:|---:|---:|
| TEKKEN 7 | ~18.10 GB | ~29.98 GB | +65.64% |
| Forza Horizon 5 | ~7.40 GB | ~6.20 GB | -16.22% |
| Dying Light 2 | ~9.90 GB | ~19.33 GB | +95.25% |
| Alan Wake 2 | ~7.20 GB | ~9.64 GB | +33.89% |

### Current Matched Total

- Other compressor saved: **~42.60 GB**
- Xzen Compressor saved: **~65.15 GB**

> These results do not mean Xzen Compressor will always beat every other compressor in every game. Compression depends on the game, file types, permissions, scan depth, already-compressed files, and how the result is measured.
>
> That said, in our current matched-game test set, Xzen Compressor saved **~65.15 GB** compared to the other compressor's **~42.60 GB**, giving Xzen a lead of **~22.55 GB** and about **52.9% more saved storage**.
>
> LoL.
---

## Features

- Compress and decompress game folders with native Windows NTFS compression.
- Scan games from multiple stores and launchers.
- View games in `Grid` or `Rows` layout.
- Fetch posters from Steam and SteamGridDB.
- Track compression progress, elapsed time, and worker (CPU) activity.
- Monitor free drive space during decompression.
- Cleanup half-compressed folders when cancelling.
- Refresh game sizes when launcher metadata is missing or outdated.
- Manage FSR / upscaler replacement files.
- Pause compression while a game is running, then resume when idle.

---

## Store Support

Current scan support includes:

- Steam
- Epic Games
- GOG Galaxy
- Xbox Games
- Microsoft Store / WindowsApps
- itch.io
- EA Games
- Ubisoft
- Battle.net

> [!NOTE]
> Some store scanners are best-effort because every launcher stores game metadata differently. Steam and Epic are usually the most reliable.

---

## How It Works

1. Press `Scan Stores`.
2. The app reads launcher manifests and known install folders.
3. Valid games are saved to `source/settings/user_settings/xzen_games.json`.
4. Posters are fetched and cached locally.
5. Sizes are read from launcher metadata when possible, then folder-scanned when needed.
6. Choose a game and press `Compress`.
7. The app runs Windows `compact.exe` with the selected NTFS algorithm.
8. After the task finishes, compressed size, file count, algorithm, and saved space are recorded.

> [!TIP]
> Use `Refresh Sizes` after installing, moving, or updating games.  
> This helps fix old `0 GB` entries or missing size data.

---

## Game Detection

The app uses different checks depending on the launcher:

- **Steam** games are detected from `appmanifest_*.acf` files. If the Steam manifest is gone, the game is treated as uninstalled even if a leftover folder still exists.
- **Epic Games** are detected from Epic Launcher `.item` manifests. If the Epic manifest disappears, the saved entry is cleaned up.
- **GOG, Xbox, Microsoft Store, itch.io, EA, Ubisoft, and Battle.net** are detected from known install folders, but the folder must contain a probable game `.exe`.
- Obvious non-game executables such as uninstallers, installers, redistributables, crash reporters, helpers, and services are ignored.
- Shared/runtime folders such as Steamworks Common Redistributables and Xbox cache folders are filtered out.

The detected executable path is cached as `exe_path` so future launches do not need to rescan the whole folder just to prove the game still exists.

---

## Compression Algorithms

| Algorithm | Name | Speed | Savings | Best For |
|----------|------|-------|---------|----------|
| XPRESS4K | X4 | Fastest | Lowest | Quick compression |
| XPRESS8K | X8 | Fast | Light | Balanced default |
| XPRESS16K | X16 | Medium | Medium | Better savings |
| LZX | LZX | Slowest | Highest | Maximum compression |

> [!NOTE]
> The selected compression algorithm is saved in app settings.

---

## Compression Safety

Compression is handled through Windows `compact.exe`.  
The app splits files into worker chunks, tracks progress, and updates the overlay while running.

If compression is cancelled, the app starts a cleanup pass to avoid leaving the game half-compressed.

> [!WARNING]
> Cancelling compression may take time because cleanup must safely decompress already-processed files.

---

## Smart Gaming Pause

Compression can pause automatically while you are playing.

The app watches the foreground window and checks whether the active process looks like a game. A process counts as game activity when it is inside a known game folder, inside a Steam `steamapps/common` path, or matches a known game executable name.

When a game is active, running `compact.exe` worker processes are suspended. When the PC has been idle long enough, compression resumes automatically.

This is meant to reduce stutter while gaming without forcing you to cancel the compression task.

---

## Decompression

Decompression uses a forced recursive cleanup command and verifies compressed file attributes afterward.

This helps make sure Windows actually removes compression from existing files instead of only changing folder defaults.

---

## Posters

Poster files are cached locally in:

```
_internal/source/poster_cache/
```

Steam games use Steam app IDs and local Steam data where possible.  
Non-Steam games use SteamGridDB name search fallback.

If posters are missing, use `Refresh Posters`.

---

## FSR Mods

The `FSR Mods` tab scans installed games for AMD FidelityFX / FSR DLL targets and lets you install or restore managed FSR files.

Refresh scans the current game library and dynamically rescans store installs, then searches each game folder for:

```
amd_fidelityfx_upscaler_dx12.dll
amd_fidelityfx_dx12.dll
amd_fidelityfx_framegeneration_dx12.dll
```

The app reads the detected DLL file version when Windows exposes it. FSR 4 installs are considered normally supported when the detected game DLL is `3.1.0.0` or newer.

Games with an older or unknown DLL version are still shown if an FSR target exists. They appear as `Needs FSR 3.1.0.0+` and can be manually enabled with `Mark Supported`.

Manual support is intentionally a user decision. It allows the install button for games the automatic version check would normally block.

During install:

- Originals are backed up under `source/backups/`.
- If a game has both `amd_fidelityfx_upscaler_dx12.dll` and `amd_fidelityfx_dx12.dll`, the app preserves `amd_fidelityfx_dx12.dll` and injects into the upscaler target only.
- If a mod package only provides `amd_fidelityfx_dx12.dll`, it can still be copied into the game's `amd_fidelityfx_upscaler_dx12.dll` target path when that is the correct target.

> [!CAUTION]
> Only use FSR files you trust.  
> The app backs up originals, but replacing DLLs can still cause crashes or broken launches.
> It does not add frame generation to games that do not already support it.
> The FSR Mods system only replaces existing compatible FSR DLL targets that are already present in the game.
> Frame generation DLLs can be replaced only when the game already includes matching frame generation files and the selected mod package provides replacements for them.
> Current packages mainly include FSR INT8 / upscaler DLL replacements, not full frame generation packs.

In short: this tool can swap supported FSR files, including FP8 to INT8 replacements, but it cannot magically add frame generation to unsupported titles or replace the frame generation files. (well it can replace the FG files but yeah uh, I'm confused on how to exactly do that & add support?)

---

## Tested With FSR 4.0

| Game | Status | Note |
|------|--------|------|
| Forza Horizon 6 | Native swap | Works through DLL replacement. |
| Cyberpunk 2077 | Manual support override | Detected through `amd_fidelityfx_dx12.dll`; use `Mark Supported` if the version gate blocks install. |

---

## Data Files

The app stores local state in:

```
source/settings/user_settings/xzen_games.json
source/settings/user_settings/xzen_settings.json
source/settings/user_settings/xzen_fsr_scan_cache.json
```

On clean installs without a local settings folder, `platformdirs` may place this under your per-user app data directory.

These files store:

- game metadata and install paths
- cached executable paths
- poster paths
- compression status and selected algorithms
- app settings such as layout, worker count, terminal visibility, and admin launch preference
- FSR scan results, manual support overrides, detected targets, and backup paths

---

## Administrator Mode

Some folders require elevated access, especially games installed under protected launcher directories.

> [!TIP]
> If games, compression, or FSR files are not detected correctly, run the app as administrator.  
> You can enable the setting that asks for administrator access when the app starts.

---

## Safety Notes

> [!WARNING]
> Do not compress Windows system folders, drive roots, launcher runtime folders, backup folders, or folders that are not actual game installs.

NTFS compression savings vary by game.  
Already-compressed assets, videos, archives, and packed game files may save little or nothing.

FSR replacement is separate from NTFS compression. Compression uses Windows filesystem attributes; FSR management replaces DLL files after creating backups.

---

## Status

**Xzen Game Compressor - Higanbana** is still in development.

Some features may change, and store scanning may improve over time.
FSR Implementation for games are still in early development. ```The FSR Versions are modified FSR INT8 .dll's``` that means it supports older cards like RX6000 Series

Required Notice: Copyright (c) 2026 LXRylex (https://github.com/LXRylex)
