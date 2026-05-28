import json
import os
import string
from pathlib import Path

from .steam import is_steam_game_installed, scan_steam_games
from .system import find_game_executable, is_probable_game_exe, game_folder_has_executable, safe_path


IGNORED_STORE_FOLDER_NAMES = {
    "gamesave",
    "game saves",
    "saved games",
    "common",
    "wgs",
    "mutablebackup",
    "msixvc",
    "deliveryoptimization",
    "epic online services",
    "launcher",
    "launchers",
    "online services",
    "riot client",
    "steamapps",
    "steamworks shared",
    "support",
}

IGNORED_SCAN_FOLDER_NAMES = {
    "$recycle.bin",
    "$windows.~bt",
    "$windows.~ws",
    "android",
    "appdata",
    "boot",
    "documents and settings",
    "drivers",
    "intel",
    "msocache",
    "onedrivetemp",
    "pagefile.sys",
    "perflogs",
    "program files",
    "program files (x86)",
    "programdata",
    "recovery",
    "system volume information",
    "users",
    "windows",
}

COMMON_GAME_LIBRARY_NAMES = {
    "battle.net",
    "epic games",
    "epicgames",
    "ea games",
    "game",
    "game library",
    "gamelibrary",
    "games",
    "games library",
    "gog games",
    "installed games",
    "pc games",
    "steam",
    "steam library",
    "steamlibrary",
    "ubisoft game launcher",
    "xboxgames",
}

COMMON_GAME_LIBRARY_TOKENS = (
    "battle",
    "epic",
    "game",
    "gog",
    "library",
    "steam",
    "ubisoft",
    "xbox",
)

IGNORED_MICROSOFT_STORE_PACKAGE_TOKENS = (
    "microsoft.edge.gameassist",
    "microsoft.gamingapp",
    "microsoft.gamingservices",
    "microsoft.xbox",
    "microsoft.gameinput",
    "microsoft.windowsstore",
    "microsoft.storepurchaseapp",
    "microsoft.vclibs",
    "microsoft.ui.",
)

GAME_INSTALL_MARKER_NAMES = {
    ".egstore",
    "_commonredist",
    "binaries",
    "content",
    "engine",
    "game",
    "redist",
    "steam_appid.txt",
}


def is_ignored_store_folder(name):
    return str(name or "").strip().lower() in IGNORED_STORE_FOLDER_NAMES


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def epic_manifest_dirs():
    return existing_dirs([
        r"%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests",
    ])


def epic_manifest_matches_game(data, game):
    if not isinstance(data, dict) or not isinstance(game, dict):
        return False

    game_path = os.path.abspath(str(game.get("path", "") or "")).lower()
    install_path = data.get("InstallLocation") or data.get("InstallLocationString") or ""
    if game_path and install_path and os.path.abspath(install_path).lower() == game_path:
        return True

    appid = str(game.get("appid", "") or "").strip().lower()
    manifest_ids = [
        data.get("CatalogItemId"),
        data.get("AppName"),
        data.get("MainGameAppName"),
    ]
    if appid and any(str(value or "").strip().lower() == appid for value in manifest_ids):
        return True

    name = str(game.get("name", "") or "").strip().lower()
    manifest_names = [
        data.get("DisplayName"),
        data.get("AppName"),
        data.get("MainGameAppName"),
    ]
    return bool(name and any(str(value or "").strip().lower() == name for value in manifest_names))


def is_epic_game_installed(game):
    for manifest_dir in epic_manifest_dirs():
        for manifest in Path(manifest_dir).glob("*.item"):
            if epic_manifest_matches_game(read_json(manifest), game):
                return bool(game.get("path") and os.path.isdir(game.get("path")))

    return False


def is_store_game_installed(game):
    if not isinstance(game, dict):
        return False

    source = game.get("source", "")

    if source == "Steam":
        return is_steam_game_installed(game)

    if source == "Epic":
        return is_epic_game_installed(game)

    if source in {"Xbox", "Microsoft Store"} and is_ignored_store_folder(game.get("name")):
        return False

    path = game.get("path", "")
    exe_path = game.get("exe_path", "")
    if exe_path and os.path.isfile(exe_path) and is_probable_game_exe(exe_path):
        return True

    return game_folder_has_executable(path)


def existing_dirs(paths):
    clean = []
    seen = set()

    for path in paths:
        if not path:
            continue
        try:
            resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path))))
        except Exception:
            continue
        key = resolved.lower()
        if key in seen or not os.path.isdir(resolved):
            continue
        seen.add(key)
        clean.append(resolved)

    return clean


def drive_roots():
    roots = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.isdir(root):
            roots.append(root)
    return roots


def should_scan_folder_name(name):
    lower = str(name or "").strip().lower()
    if not lower or lower in IGNORED_STORE_FOLDER_NAMES or lower in IGNORED_SCAN_FOLDER_NAMES:
        return False
    if lower.startswith("."):
        return False
    return True


def game_entry(name, path, source, appid="", manifest_size=0, poster_status="Queued"):
    if not name or not path:
        return None
    if is_ignored_store_folder(name):
        return None

    path = os.path.abspath(path)
    ok, _ = safe_path(path)
    if not ok:
        return None

    exe_path = ""
    if source not in {"Steam", "Epic"}:
        exe_path = find_game_executable(path)
        if not exe_path:
            return None

    manifest_size = int(manifest_size or 0)
    return {
        "appid": str(appid or ""),
        "name": str(name).strip(),
        "path": path,
        "source": source,
        "poster": "",
        "poster_status": poster_status,
        "size": manifest_size,
        "manifest_size": manifest_size,
        "compressed_size": 0,
        "compressed_file_count": 0,
        "compression_algorithm": "",
        "file_count": 0,
        "exe_path": exe_path,
        "scan_progress": 100 if manifest_size else 0,
        "status": f"{source} Size" if manifest_size else "Unknown",
        "size_source": f"{source} manifest" if manifest_size else "Unknown",
    }


def unique_games(games):
    clean = []
    seen = set()

    for game in games:
        if not game:
            continue
        path = os.path.abspath(game.get("path", ""))
        key = path.lower()
        if not path or key in seen:
            continue
        seen.add(key)
        clean.append(game)

    return clean


def scan_epic_games():
    found = []

    for manifest_dir in epic_manifest_dirs():
        for manifest in Path(manifest_dir).glob("*.item"):
            data = read_json(manifest)
            if not isinstance(data, dict):
                continue

            path = data.get("InstallLocation") or data.get("InstallLocationString")
            name = data.get("DisplayName") or data.get("AppName") or data.get("MainGameAppName")
            appid = data.get("CatalogItemId") or data.get("AppName") or manifest.stem
            size = data.get("InstallSize") or data.get("MainGameInstallSize") or 0
            found.append(game_entry(name, path, "Epic", appid, size))

    return unique_games(found)


def scan_itch_games():
    found = []
    roots = existing_dirs([
        r"%APPDATA%\itch\apps",
        r"%LOCALAPPDATA%\itch\apps",
    ])

    for root in roots:
        try:
            children = [item for item in Path(root).iterdir() if item.is_dir()]
        except Exception:
            children = []

        for child in children:
            found.append(game_entry(child.name, str(child), "itch.io", child.name, 0, "Manual Folder"))

    return unique_games(found)


def scan_known_store_roots():
    found = []
    root_patterns = []

    for drive in drive_roots():
        root_patterns.extend([
            (os.path.join(drive, "GOG Games"), "GOG Galaxy"),
            (os.path.join(drive, "XboxGames"), "Xbox"),
            (os.path.join(drive, "EA Games"), "EA"),
            (os.path.join(drive, "Program Files", "EA Games"), "EA"),
            (os.path.join(drive, "Program Files (x86)", "Ubisoft", "Ubisoft Game Launcher", "games"), "Ubisoft"),
            (os.path.join(drive, "Ubisoft Game Launcher", "games"), "Ubisoft"),
            (os.path.join(drive, "Program Files (x86)", "Battle.net", "Games"), "Battle.net"),
            (os.path.join(drive, "Battle.net", "Games"), "Battle.net"),
        ])

    for root, source in root_patterns:
        if not os.path.isdir(root):
            continue
        try:
            children = [item for item in Path(root).iterdir() if item.is_dir()]
        except Exception:
            children = []

        for child in children:
            if is_ignored_store_folder(child.name):
                continue
            game_path = child
            content_path = child / "Content"
            if source == "Xbox":
                if not content_path.is_dir():
                    continue
                game_path = content_path
            found.append(game_entry(child.name, str(game_path), source, child.name, 0, "Manual Folder"))

    return unique_games(found)


def common_library_roots_for_drive(drive):
    roots = []

    static_paths = [
        "Battle.net\\Games",
        "EA Games",
        "Epic Games",
        "GOG Games",
        "Games",
        "Game Library",
        "Games Library",
        "GameLibrary",
        "Installed Games",
        "PC Games",
        "SteamLibrary\\steamapps\\common",
        "Ubisoft Game Launcher\\games",
        "XboxGames",
        "Program Files\\Epic Games",
        "Program Files\\EA Games",
        "Program Files\\GOG Galaxy\\Games",
        "Program Files\\Steam\\steamapps\\common",
        "Program Files\\Ubisoft\\Ubisoft Game Launcher\\games",
        "Program Files (x86)\\Epic Games",
        "Program Files (x86)\\EA Games",
        "Program Files (x86)\\GOG Galaxy\\Games",
        "Program Files (x86)\\Steam\\steamapps\\common",
        "Program Files (x86)\\Ubisoft\\Ubisoft Game Launcher\\games",
    ]

    for rel_path in static_paths:
        roots.append(Path(drive) / rel_path)

    try:
        top_level = [item for item in Path(drive).iterdir() if item.is_dir()]
    except Exception:
        top_level = []

    for item in top_level[:200]:
        lower = item.name.lower()
        if not should_scan_folder_name(lower):
            continue

        if lower in COMMON_GAME_LIBRARY_NAMES or any(token in lower for token in COMMON_GAME_LIBRARY_TOKENS):
            roots.append(item)
            roots.extend([
                item / "games",
                item / "Games",
                item / "steamapps" / "common",
                item / "common",
            ])

    return existing_dirs(roots)


def folder_entry_from_detected_path(path, source="Detected Folder"):
    if not path or not os.path.isdir(path):
        return None

    folder = Path(path)
    if not should_scan_folder_name(folder.name):
        return None

    exe_path = find_game_executable(str(folder), max_depth=5, max_entries=6500)
    if not exe_path:
        return None

    entry = game_entry(folder.name, str(folder), source, folder.name, 0, "Manual Folder")
    if entry:
        entry["exe_path"] = exe_path
    return entry


def has_game_install_markers(path):
    try:
        children = [item.name.lower() for item in Path(path).iterdir()]
    except Exception:
        return False
    if any(name in GAME_INSTALL_MARKER_NAMES for name in children):
        return True
    return any(name.endswith(".exe") for name in children)


def scan_detected_game_folders():
    found = []
    seen_roots = set()

    for drive in drive_roots():
        for root in common_library_roots_for_drive(drive):
            root_key = os.path.abspath(root).lower()
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)

            try:
                children = [item for item in Path(root).iterdir() if item.is_dir()]
            except Exception:
                children = []

            for child in children[:350]:
                if not should_scan_folder_name(child.name):
                    continue

                if child.name.lower() == "content":
                    continue

                content_path = child / "Content"
                if content_path.is_dir():
                    content_entry = folder_entry_from_detected_path(str(content_path), "Detected Folder")
                    if content_entry:
                        content_entry["name"] = child.name
                        found.append(content_entry)
                        continue

                found.append(folder_entry_from_detected_path(str(child), "Detected Folder"))

        try:
            top_level = [item for item in Path(drive).iterdir() if item.is_dir()]
        except Exception:
            top_level = []

        for child in top_level[:200]:
            if not should_scan_folder_name(child.name):
                continue

            lower = child.name.lower()
            if lower in COMMON_GAME_LIBRARY_NAMES or any(token in lower for token in COMMON_GAME_LIBRARY_TOKENS):
                continue

            if not has_game_install_markers(child):
                continue

            found.append(folder_entry_from_detected_path(str(child), "Detected Folder"))

    return unique_games(found)


def scan_microsoft_store_games():
    found = []

    for drive in drive_roots():
        windows_apps = Path(drive) / "Program Files" / "WindowsApps"
        if not windows_apps.is_dir():
            continue
        try:
            candidates = [item for item in windows_apps.iterdir() if item.is_dir()]
        except Exception:
            continue

        for item in candidates:
            name = item.name
            lower = name.lower()
            if any(token in lower for token in IGNORED_MICROSOFT_STORE_PACKAGE_TOKENS):
                continue
            if (
                "microsoft.gaming" in lower
                or "gamingservices" in lower
                or lower.startswith("microsoft.vclibs")
                or lower.startswith("microsoft.ui.")
            ):
                continue
            if any(token in lower for token in ("studio", "game", "forza", "minecraft", "halo")):
                found.append(game_entry(name.split("_")[0], str(item), "Microsoft Store", name, 0, "Manual Folder"))

    return unique_games(found)


def scan_all_store_games():
    games = []
    games.extend(scan_steam_games())
    games.extend(scan_epic_games())
    games.extend(scan_itch_games())
    games.extend(scan_known_store_roots())
    games.extend(scan_microsoft_store_games())
    games.extend(scan_detected_game_folders())
    return unique_games(games)
