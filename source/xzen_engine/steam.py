import os
import re

from .constants import EXCLUDED_STEAM_APPIDS, EXCLUDED_STEAM_NAMES
from .system import is_excluded_steam_game, safe_path
def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def extract_vdf_value(text, key):
    pattern = rf'"{re.escape(key)}"\s+"([^"]*)"'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def get_steam_path():
    possible_paths = []

    def add_candidate(path):
        if not path:
            return
        try:
            expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path))))
        except Exception:
            return
        if expanded.lower() not in [item.lower() for item in possible_paths]:
            possible_paths.append(expanded)

    if os.name == "nt":
        try:
            import winreg
            registry_keys = (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
            )
            for hive, key_path in registry_keys:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        for value_name in ("SteamPath", "InstallPath"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                                add_candidate(value)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    add_candidate(os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam"))
    add_candidate(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Steam"))

    for path in possible_paths:
        if os.path.isdir(path):
            return path
    return None


def parse_steam_libraries(vdf_path):
    libraries = []
    text = read_text(vdf_path)

    for match in re.finditer(r'"path"\s+"([^"]+)"', text, re.IGNORECASE):
        lib_path = match.group(1).replace("\\\\", "\\")
        steamapps = os.path.join(lib_path, "steamapps")
        if os.path.exists(steamapps):
            libraries.append(steamapps)

    return libraries


def find_steam_libraries():
    libraries = []
    steam_path = get_steam_path()

    if not steam_path:
        return [], None

    main_steamapps = os.path.join(steam_path, "steamapps")
    if os.path.exists(main_steamapps):
        libraries.append(main_steamapps)

    library_file = os.path.join(main_steamapps, "libraryfolders.vdf")
    if os.path.exists(library_file):
        libraries.extend(parse_steam_libraries(library_file))

    clean = []
    for lib in libraries:
        lib = os.path.abspath(lib)
        if lib not in clean:
            clean.append(lib)

    return clean, steam_path


def scan_steam_games():
    found = []
    libraries, steam_path = find_steam_libraries()

    for steamapps in libraries:
        common = os.path.join(steamapps, "common")
        if not os.path.exists(common):
            continue

        for file in os.listdir(steamapps):
            if not file.startswith("appmanifest_") or not file.endswith(".acf"):
                continue

            manifest_path = os.path.join(steamapps, file)
            text = read_text(manifest_path)

            appid = extract_vdf_value(text, "appid")
            name = extract_vdf_value(text, "name")
            installdir = extract_vdf_value(text, "installdir")
            size_on_disk_raw = extract_vdf_value(text, "SizeOnDisk")

            if is_excluded_steam_game(appid, name):
                continue

            try:
                manifest_size = int(size_on_disk_raw)
            except Exception:
                manifest_size = 0

            if not name or not installdir:
                continue

            game_path = os.path.join(common, installdir)
            if not os.path.isdir(game_path):
                continue

            ok, _ = safe_path(game_path)
            if not ok:
                continue

            found.append({
                "appid": appid,
                "name": name,
                "path": os.path.abspath(game_path),
                "source": "Steam",
                "poster": "",
                "poster_status": "Queued",
                "size": manifest_size,
                "manifest_size": manifest_size,
                "compressed_size": 0,
                "compressed_file_count": 0,
                "compression_algorithm": "",
                "file_count": 0,
                "scan_progress": 100 if manifest_size else 0,
                "status": "Steam Size" if manifest_size else "Unknown",
                "size_source": "Steam manifest" if manifest_size else "Unknown",
            })

    return found


def steam_manifest_exists(appid):
    appid = str(appid or "").strip()
    if not appid:
        return False

    manifest_name = f"appmanifest_{appid}.acf"
    libraries, _ = find_steam_libraries()

    for steamapps in libraries:
        if os.path.exists(os.path.join(steamapps, manifest_name)):
            return True

    return False


def is_steam_game_installed(game):
    if not isinstance(game, dict):
        return False

    appid = str(game.get("appid", "") or "").strip()
    path = game.get("path", "")

    if is_excluded_steam_game(appid, game.get("name")):
        return False

    if appid and not steam_manifest_exists(appid):
        return False

    return bool(path and os.path.isdir(path))


def get_steam_manifest_size(appid):
    appid = str(appid or "").strip()
    if not appid:
        return 0

    libraries, _ = find_steam_libraries()
    manifest_name = f"appmanifest_{appid}.acf"

    for steamapps in libraries:
        manifest_path = os.path.join(steamapps, manifest_name)
        if not os.path.exists(manifest_path):
            continue

        text = read_text(manifest_path)
        size_on_disk_raw = extract_vdf_value(text, "SizeOnDisk")
        try:
            return max(0, int(size_on_disk_raw))
        except Exception:
            return 0

    return 0

