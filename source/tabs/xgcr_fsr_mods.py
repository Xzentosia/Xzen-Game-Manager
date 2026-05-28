import os
import json
import shutil
import subprocess
import time
import hashlib
import re
import ctypes
from ctypes import wintypes
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QDialog,
    QComboBox,
    QListView,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QScrollArea,
    QGridLayout,
    QMenu,
    QWidgetAction,
    QStackedLayout,
)

from source.xzen_engine.constants import (
    DATA_FILE,
    FSR_BACKUP_DIR,
    FSR_MODS_DIR,
    FSR_SCAN_CACHE_FILE,
)
from source.xzen_engine.posters import sanitize_png_file
from source.tabs.game_library import LoadingSpinner, SmoothScrollArea

                                                               
GLOBAL_BACKUP_ROOT = FSR_BACKUP_DIR
LEGACY_BACKUP_ROOT_NAME = "xgcr_fsr_backups"

FSR_UPSCALER_DLL = "amd_fidelityfx_upscaler_dx12.dll"
FSR_LOADER_DLL = "amd_fidelityfx_dx12.dll"
FSR_FRAMEGEN_DLL = "amd_fidelityfx_framegeneration_dx12.dll"

FSR_MANAGED_DLLS = [
    FSR_UPSCALER_DLL,
    FSR_LOADER_DLL,
    FSR_FRAMEGEN_DLL,
]

ANTI_CHEAT_FILE_MARKERS = {
    "easyanticheat_eos.exe": "Easy Anti-Cheat",
    "easyanticheat_setup.exe": "Easy Anti-Cheat",
    "start_protected_game.exe": "Easy Anti-Cheat",
    "beservice.exe": "BattlEye",
    "beservice_x64.exe": "BattlEye",
    "beclient.dll": "BattlEye",
    "beclient_x64.dll": "BattlEye",
    "ace-base.sys": "Anti-Cheat Expert",
    "ace-boost.sys": "Anti-Cheat Expert",
    "ace-game.sys": "Anti-Cheat Expert",
    "x3.xem": "XIGNCODE",
    "xcorona.xem": "XIGNCODE",
    "npggnt.des": "GameGuard",
    "vgk.sys": "Riot Vanguard",
    "vgc.exe": "Riot Vanguard",
}

ANTI_CHEAT_DIR_MARKERS = {
    "easyanticheat": "Easy Anti-Cheat",
    "easyanticheat_eos": "Easy Anti-Cheat",
    "battleye": "BattlEye",
    "binaries\\thirdparty\\easyanticheat": "Easy Anti-Cheat",
    "binaries\\thirdparty\\battleye": "BattlEye",
    "gameguard": "GameGuard",
    "xigncode": "XIGNCODE",
    "ricochet": "Ricochet",
    "equ8": "EQU8",
}

                                                               
FSR_REQUIRED_SUPPORT_DLL = FSR_UPSCALER_DLL
FSR_MIN_GAME_DLL_VERSION = (3, 1, 0, 0)
FSR_MIN_GAME_DLL_VERSION_TEXT = "3.1.0.0"

MIN_CARD_W = 205
MAX_CARD_W = 235
CARD_H_EXTRA = 126
POSTER_W_PADDING = 30
POSTER_ASPECT = 230 / 175
GRID_SPACING = 12

PURPLE_SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        background: #080808;
        width: 11px;
        margin: 0;
        border: none;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical {
        background: #B38AFF;
        min-height: 34px;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical:hover {
        background: #c8aaff;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0;
        background: transparent;
        border: none;
    }

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: transparent;
    }

    QScrollBar:horizontal {
        background: #080808;
        height: 11px;
        margin: 0;
        border: none;
        border-radius: 5px;
    }

    QScrollBar::handle:horizontal {
        background: #B38AFF;
        min-width: 34px;
        border-radius: 5px;
    }

    QScrollBar::handle:horizontal:hover {
        background: #c8aaff;
    }

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {
        width: 0;
        background: transparent;
        border: none;
    }

    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {
        background: transparent;
    }
"""

FSR_PAGE_STYLE = """
    #FsrHeaderPanel {
        background: #0b0b0b;
        border: 1px solid #242424;
        border-radius: 7px;
    }

    #FsrTitle {
        color: #ffffff;
        font-size: 20px;
        font-weight: 900;
        background: transparent;
    }

    #FsrCounter {
        color: #B38AFF;
        font-size: 12px;
        font-weight: 900;
        background: transparent;
    }

    #FsrVersionText {
        color: #FF6B6B;
        font-size: 12px;
        font-weight: 900;
        background: transparent;
    }

    #FsrCacheText {
        color: #888888;
        font-size: 10px;
        font-weight: 800;
        background: transparent;
    }

    #GpuNameText {
        color: #888888;
        font-size: 12px;
        font-weight: 900;
        background: transparent;
    }

    #FsrScanIconButton {
        background: transparent;
        color: #B38AFF;
        border: 1px solid #333333;
        border-radius: 4px;
        min-width: 96px;
        max-width: 120px;
        min-height: 32px;
        max-height: 32px;
        padding: 0 12px;
        font-size: 12px;
        font-weight: 900;
    }

    #FsrScanIconButton:hover {
        background: rgba(179, 138, 255, 0.12);
        border-color: #B38AFF;
        color: #ffffff;
    }

    #FsrManualButton {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #333333;
        border-radius: 4px;
        min-width: 96px;
        max-width: 130px;
        min-height: 32px;
        max-height: 32px;
        padding: 0 12px;
        font-size: 12px;
        font-weight: 900;
    }

    #FsrManualButton:hover {
        background: rgba(179, 138, 255, 0.12);
        border-color: #B38AFF;
        color: #ffffff;
    }

    #FsrManualDialog {
        background: #0B0A10;
        color: #ffffff;
    }

    #FsrManualDialog QLabel {
        background: transparent;
    }

    #FsrManualTitle {
        color: #ffffff;
        font-size: 22px;
        font-weight: 900;
    }

    #FsrManualHint {
        color: #888888;
        font-size: 12px;
        font-weight: 700;
    }

    #FsrManualCombo {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #333333;
        border-radius: 8px;
        padding: 0 12px;
        min-height: 42px;
        font-weight: 900;
    }

    #FsrManualCombo:hover {
        border-color: #B38AFF;
        background: #171421;
    }

    #FsrManualCombo QAbstractItemView {
        background: #0B0A10;
        color: #eeeeee;
        border: 1px solid #2B2640;
        selection-background-color: rgba(179, 138, 255, 0.18);
        selection-color: #ffffff;
        outline: 0;
    }

    #FsrPathInput {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #333333;
        border-radius: 8px;
        padding: 0 12px;
        min-height: 38px;
        font-weight: 800;
    }

    #FsrPathInput:hover,
    #FsrPathInput:focus {
        border-color: #B38AFF;
    }

    #FsrManualFieldLabel {
        color: #ffffff;
        font-size: 12px;
        font-weight: 900;
    }

    #FsrManualPrimary {
        background: #B38AFF;
        color: #08070D;
        border: 1px solid #B38AFF;
        border-radius: 8px;
        padding: 10px 16px;
        font-weight: 900;
    }

    #FsrManualGhost {
        background: #181525;
        color: #ffffff;
        border: 1px solid #2B2640;
        border-radius: 8px;
        padding: 10px 16px;
        font-weight: 900;
    }

    #FsrGameCard {
        background: #0a0a0a;
        border: 1px solid #333333;
        border-radius: 4px;
    }

    #FsrGameCard:hover {
        border: 1px solid #eeeeee;
        background: #111111;
    }

    #FsrPoster {
        background: transparent;
        border-radius: 4px;
    }

    #FsrCardName {
        font-size: 10px;
        font-weight: 800;
        color: #ffffff;
        background: transparent;
    }

    #FsrCardMeta {
        font-size: 9px;
        color: #888888;
        background: transparent;
    }

    #FsrStatusText {
        font-size: 9px;
        color: #B38AFF;
        font-weight: 800;
        background: transparent;
    }

    #FsrAntiCheatPill {
        color: #FFD36B;
        border: 1px solid rgba(255, 211, 107, 0.55);
        border-radius: 4px;
        padding: 2px 7px;
        font-size: 9px;
        font-weight: 900;
        background: rgba(255, 211, 107, 0.08);
    }

    #FsrViewTabs {
        background: transparent;
    }

    #FsrViewTab {
        background: transparent;
        color: #888888;
        border: 1px solid #333333;
        border-radius: 4px;
        padding: 7px 14px;
        font-size: 11px;
        font-weight: 900;
    }

    #FsrViewTab[active="true"] {
        color: #ffffff;
        border-color: #B38AFF;
        background: rgba(179, 138, 255, 0.14);
    }

    #FsrEmptyPanel {
        background: #0a0a0a;
        border: 1px solid #333333;
        border-radius: 7px;
    }

    #FsrEmptyText {
        color: #888888;
        font-size: 13px;
        font-weight: 800;
        background: transparent;
    }

    QMenu {
        background: #0a0a0a;
        color: #eeeeee;
        border: 1px solid #333333;
        padding: 4px;
    }

    QMenu::item {
        padding: 7px 18px;
        background: transparent;
    }

    QMenu::item:selected {
        background: rgba(179, 138, 255, 0.18);
        color: #ffffff;
    }
"""


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def same_file_path(a, b):
    try:
        return os.path.abspath(a).lower() == os.path.abspath(b).lower()
    except Exception:
        return False


def safe_relative(path, root):
    try:
        return os.path.relpath(path, root)
    except Exception:
        return os.path.basename(path)


def short_name(path, root):
    rel = safe_relative(path, root).replace("/", "\\")
    if len(rel) <= 42:
        return rel
    return "..." + rel[-39:]


def file_sha256(path, chunk_size=1024 * 1024):
    try:
        h = hashlib.sha256()

        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)

                if not chunk:
                    break

                h.update(chunk)

        return h.hexdigest()
    except Exception:
        return ""


def files_are_same(path_a, path_b):
    try:
        if not path_a or not path_b:
            return False

        if not os.path.exists(path_a) or not os.path.exists(path_b):
            return False

        if os.path.getsize(path_a) != os.path.getsize(path_b):
            return False

        return file_sha256(path_a) == file_sha256(path_b)
    except Exception:
        return False


def is_target_currently_modded(target, backup):
                                                                           
                                                                        
    if not target or not backup:
        return False

    if not os.path.exists(target) or not os.path.exists(backup):
        return False

    return not files_are_same(target, backup)


def app_file_candidates(filename):
    script_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()
    requested = Path(filename)

    yielded = set()
    paths = [requested] if requested.is_absolute() else [cwd / filename, script_dir / filename]

    for path in paths:
        key = str(path.resolve()).lower()

        if key not in yielded:
            yielded.add(key)
            yield path


def get_writable_app_file(filename):
    for path in app_file_candidates(filename):
        parent = path.parent
        if parent.exists():
            return path

    return Path.cwd() / filename


def backup_root():
    root = Path(GLOBAL_BACKUP_ROOT)
    if not root.is_absolute():
        root = get_writable_app_file(str(root))
    return root


def normalize_backup_file_path(path):
    if not path:
        return path

    try:
        parts = list(Path(path).parts)
        lowered = [part.lower() for part in parts]

        if LEGACY_BACKUP_ROOT_NAME.lower() in lowered:
            index = lowered.index(LEGACY_BACKUP_ROOT_NAME.lower())
            return str(Path(FSR_BACKUP_DIR).joinpath(*parts[index + 1:]))
    except Exception:
        pass

    return path


def normalize_support_info_paths(info):
    if not isinstance(info, dict):
        return info

    info = dict(info)
    info["backup"] = normalize_backup_file_path(info.get("backup", ""))

    backups = info.get("backups", {})
    if isinstance(backups, dict):
        info["backups"] = {
            key: normalize_backup_file_path(value)
            for key, value in backups.items()
        }

    return info


def sanitize_name(text):
    text = str(text or "Unknown").strip()
    text = re.sub(r'[<>:"/\\|?*]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80] or "Unknown"


def game_backup_key(game):
    name = sanitize_name(game.get("name", "Unknown"))
    appid = str(game.get("appid", "") or "").strip()
    path = os.path.abspath(str(game.get("path", "") or ""))
    path_hash = hashlib.sha1(path.lower().encode("utf-8", errors="ignore")).hexdigest()[:8]

    if appid:
        return f"{name}_{appid}_{path_hash}"

    return f"{name}_{path_hash}"


def backup_path_for_target(game, target_path, game_path):
    rel = safe_relative(target_path, game_path)
    return os.path.join(str(backup_root()), game_backup_key(game), rel + ".original")


def local_data_file_candidates():
    for path in app_file_candidates(DATA_FILE):
        if path.exists():
            yield path


def load_games_from_json():
    for path in local_data_file_candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))

            if isinstance(data, list):
                return data

            if isinstance(data, dict):
                for key in ("games", "items", "library"):
                    value = data.get(key)
                    if isinstance(value, list):
                        return value
        except Exception:
            pass

    return []


def existing_dirs(paths):
    clean = []
    seen = set()

    for path in paths:
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


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def extract_vdf_value(text, key):
    pattern = rf'"{re.escape(key)}"\s+"([^"]*)"'
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return match.group(1)

    return ""


def parse_steam_libraries(vdf_text):
    libraries = []

    for match in re.finditer(r'"path"\s+"([^"]+)"', vdf_text, re.IGNORECASE):
        lib_path = match.group(1).replace("\\\\", "\\")
        steamapps = os.path.join(lib_path, "steamapps")

        if os.path.isdir(steamapps):
            libraries.append(steamapps)

    return libraries


def get_steam_path():
    try:
        from source.xzen_engine.steam import get_steam_path as shared_get_steam_path
        return shared_get_steam_path() or ""
    except Exception:
        return ""


def find_steam_libraries():
    libraries = []
    steam_path = get_steam_path()

    if not steam_path:
        return []

    main_steamapps = os.path.join(steam_path, "steamapps")

    if os.path.isdir(main_steamapps):
        libraries.append(main_steamapps)

    library_file = os.path.join(main_steamapps, "libraryfolders.vdf")

    if os.path.exists(library_file):
        libraries.extend(parse_steam_libraries(read_text(library_file)))

    clean = []
    seen = set()

    for lib in libraries:
        normalized = os.path.abspath(lib).lower()

        if normalized not in seen:
            seen.add(normalized)
            clean.append(os.path.abspath(lib))

    return clean


def scan_steam_games_fallback():
    found = []

    for steamapps in find_steam_libraries():
        common = os.path.join(steamapps, "common")

        if not os.path.isdir(common):
            continue

        try:
            files = os.listdir(steamapps)
        except Exception:
            continue

        for file in files:
            if not file.startswith("appmanifest_") or not file.endswith(".acf"):
                continue

            manifest_path = os.path.join(steamapps, file)
            text = read_text(manifest_path)

            appid = extract_vdf_value(text, "appid")
            name = extract_vdf_value(text, "name")
            installdir = extract_vdf_value(text, "installdir")
            size_raw = extract_vdf_value(text, "SizeOnDisk")

            if not name or not installdir:
                continue

            game_path = os.path.join(common, installdir)

            if not os.path.isdir(game_path):
                continue

            try:
                size = int(size_raw or 0)
            except Exception:
                size = 0

            found.append({
                "appid": appid,
                "name": name,
                "path": os.path.abspath(game_path),
                "source": "Steam",
                "poster": "",
                "poster_status": "",
                "size": size,
                "manifest_size": size,
                "compressed_size": 0,
                "compression_algorithm": "",
                "status": "Steam Size" if size else "Unknown",
            })

    return found


def steam_manifest_exists(appid):
    appid = str(appid or "").strip()

    if not appid:
        return False

    manifest_name = f"appmanifest_{appid}.acf"

    for steamapps in find_steam_libraries():
        if os.path.exists(os.path.join(steamapps, manifest_name)):
            return True

    return False


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


def epic_manifest_exists_for_game(game):
    for manifest_dir in epic_manifest_dirs():
        for manifest in Path(manifest_dir).glob("*.item"):
            if epic_manifest_matches_game(read_json(manifest), game):
                return True

    return False


NON_GAME_EXE_NAMES = {
    "explorer.exe",
    "steam.exe",
    "steamwebhelper.exe",
    "discord.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "opera.exe",
    "operagx.exe",
    "spotify.exe",
    "code.exe",
    "pycharm64.exe",
    "devenv.exe",
    "cmd.exe",
    "powershell.exe",
    "windowsterminal.exe",
    "taskmgr.exe",
    "xzen game compressor.exe",
}

KNOWN_GAME_EXE_NAMES = {
    "eldenring.exe",
    "start_protected_game.exe",
    "cs2.exe",
    "csgo.exe",
    "valorant-win64-shipping.exe",
    "valorant.exe",
    "fortniteclient-win64-shipping.exe",
    "gta5.exe",
    "gtaiv.exe",
    "rdr2.exe",
    "witcher3.exe",
    "cyberpunk2077.exe",
    "minecraft.exe",
    "javaw.exe",
    "robloxplayerbeta.exe",
    "league of legends.exe",
    "leagueclient.exe",
    "overwatch.exe",
    "r5apex.exe",
    "destiny2.exe",
    "warframe.x64.exe",
    "dota2.exe",
    "deadbydaylight-win64-shipping.exe",
}

IGNORED_GAME_EXE_KEYWORDS = (
    "unins",
    "uninstall",
    "setup",
    "install",
    "installer",
    "redist",
    "vcredist",
    "directx",
    "dotnet",
    "crash",
    "reporter",
    "bootstrap",
    "helper",
    "service",
    "benchmark",
)


def is_probable_game_exe(path):
    name = os.path.basename(str(path or "")).lower()

    if not name.endswith(".exe") or name in NON_GAME_EXE_NAMES:
        return False

    if name in KNOWN_GAME_EXE_NAMES:
        return True

    stem = os.path.splitext(name)[0]
    if any(keyword in stem for keyword in IGNORED_GAME_EXE_KEYWORDS):
        return False

    return True


def find_game_executable(path, max_depth=5, max_entries=5000):
    if not path or not os.path.isdir(path):
        return ""

    root = os.path.abspath(path)
    candidates = []
    visited_entries = 0

    try:
        for folder, dirs, files in os.walk(root):
            visited_entries += len(dirs) + len(files)
            if visited_entries > max_entries:
                break

            try:
                rel = os.path.relpath(folder, root)
                depth = 0 if rel == "." else len(Path(rel).parts)
            except Exception:
                depth = max_depth + 1

            if depth >= max_depth:
                dirs[:] = []

            dirs[:] = [
                item for item in dirs
                if item.lower() not in {"redist", "_commonredist", "directx", "dotnet", "vcredist"}
            ]

            for file in files:
                if not file.lower().endswith(".exe"):
                    continue

                full_path = os.path.join(folder, file)
                if is_probable_game_exe(full_path):
                    candidates.append(full_path)
    except Exception:
        return ""

    if not candidates:
        return ""

    def score(candidate):
        name = os.path.basename(candidate).lower()
        rel = os.path.relpath(candidate, root).replace("/", "\\").lower()
        value = 0

        if name in KNOWN_GAME_EXE_NAMES:
            value += 100
        if "\\binaries\\win64\\" in f"\\{rel}" or "\\win64\\" in f"\\{rel}" or "\\x64\\" in f"\\{rel}":
            value += 40
        if "\\" not in rel:
            value += 25
        if "launcher" in name:
            value -= 20

        return value

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def game_folder_has_executable(path):
    return bool(find_game_executable(path))


def saved_game_is_installed(game):
    if not isinstance(game, dict):
        return False

    path = str(game.get("path", "") or "")

    if game.get("source") == "Manual FSR":
        return bool(path and os.path.isdir(path))

    if game.get("source") == "Steam":
        appid = str(game.get("appid", "") or "").strip()
        if appid and not steam_manifest_exists(appid):
            return False

    if game.get("source") == "Epic" and not epic_manifest_exists_for_game(game):
        return False

    if game.get("source") not in {"Steam", "Epic"}:
        exe_path = game.get("exe_path", "")
        if exe_path and os.path.isfile(exe_path) and is_probable_game_exe(exe_path):
            return True
        return game_folder_has_executable(path)

    return bool(path and os.path.isdir(path))


def support_info_game_is_installed(info):
    if not isinstance(info, dict):
        return False

    game = info.get("game", {})
    if isinstance(game, dict) and game:
        return saved_game_is_installed(game)

    game_path = str(info.get("game_path", "") or "")
    return game_folder_has_executable(game_path)


def clean_dll_stem(name):
    stem = Path(str(name or "")).stem.lower().strip()
    stem = re.sub(r"\s+", "", stem)
    stem = re.sub(r"\(\d+\)$", "", stem)
    stem = re.sub(r"[-_ ]?copy$", "", stem)
    return stem


def classify_fsr_dll_name(name):
    lower = str(name or "").lower()
    stem = clean_dll_stem(name)

    if not lower.endswith(".dll"):
        return ""

    if "framegeneration" in stem or "frame_generation" in stem or "framegen" in stem:
        return FSR_FRAMEGEN_DLL

    if stem == clean_dll_stem(FSR_LOADER_DLL):
        return FSR_LOADER_DLL

    if "upscaler" in stem and "dx12" in stem:
        return FSR_UPSCALER_DLL

    if stem == clean_dll_stem(FSR_UPSCALER_DLL):
        return FSR_UPSCALER_DLL

    return ""


def file_name_matches(canonical_name, actual_name):
    actual_suffix = Path(str(actual_name or "")).suffix.lower()

    if actual_suffix != ".dll":
        return False

    classified = classify_fsr_dll_name(actual_name)

    if classified:
        return classified == canonical_name

    canonical_stem = clean_dll_stem(canonical_name)
    actual_stem = clean_dll_stem(actual_name)

    if actual_stem == canonical_stem:
        return True

    return actual_stem.startswith(canonical_stem)


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def dll_file_version(path):
    if not path or not os.path.exists(path) or os.name != "nt":
        return None

    try:
        handle = wintypes.DWORD()
        version_api = ctypes.windll.version
        size = version_api.GetFileVersionInfoSizeW(str(path), ctypes.byref(handle))

        if not size:
            return None

        buffer = ctypes.create_string_buffer(size)

        if not version_api.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None

        value = ctypes.c_void_p()
        value_len = wintypes.UINT()

        if not version_api.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(value_len)):
            return None

        fixed_info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents

        if fixed_info.dwSignature != 0xFEEF04BD:
            return None

        return (
            fixed_info.dwFileVersionMS >> 16,
            fixed_info.dwFileVersionMS & 0xFFFF,
            fixed_info.dwFileVersionLS >> 16,
            fixed_info.dwFileVersionLS & 0xFFFF,
        )
    except Exception:
        return None


def normalize_version_tuple(version):
    if not version:
        return ()

    parts = []

    for part in tuple(version)[:4]:
        try:
            parts.append(int(part))
        except Exception:
            parts.append(0)

    while len(parts) < 4:
        parts.append(0)

    return tuple(parts)


def format_version_tuple(version):
    version = normalize_version_tuple(version)

    if not version:
        return "Unknown"

    return ".".join(str(part) for part in version)


def version_at_least(version, minimum):
    version = normalize_version_tuple(version)

    if not version:
        return False

    return version >= normalize_version_tuple(minimum)


def fsr_game_version_info(targets, backups=None, installed=False):
    targets = targets or {}
    backups = backups or {}
    target = (
        targets.get(FSR_UPSCALER_DLL, "")
        or targets.get(FSR_LOADER_DLL, "")
        or targets.get(FSR_FRAMEGEN_DLL, "")
    )
    backup = (
        backups.get(FSR_UPSCALER_DLL, "")
        or backups.get(FSR_LOADER_DLL, "")
        or backups.get(FSR_FRAMEGEN_DLL, "")
    )
    version_path = target
    version_source = "game"

    if installed and backup and os.path.exists(backup):
        version_path = backup
        version_source = "backup"

    version = dll_file_version(version_path)
    supported = version_at_least(version, FSR_MIN_GAME_DLL_VERSION)

    return {
        "fsr_game_dll_version": format_version_tuple(version),
        "fsr_game_dll_version_tuple": list(normalize_version_tuple(version)) if version else [],
        "fsr_game_dll_version_path": version_path,
        "fsr_game_dll_version_source": version_source,
        "fsr_game_dll_version_supported": supported,
        "fsr_min_game_dll_version": FSR_MIN_GAME_DLL_VERSION_TEXT,
    }


def fsr_version_block_message(info, game_name="This game"):
    detected = info.get("fsr_game_dll_version", "Unknown")
    source = info.get("fsr_game_dll_version_source", "game")

    if source == "backup":
        source_text = "original backup"
    else:
        source_text = "game DLL"

    return (
        f"{game_name} cannot use this FSR 4 replacement yet.\n\n"
        f"Minimum required game FSR DLL: {FSR_MIN_GAME_DLL_VERSION_TEXT}\n"
        f"Detected {source_text} version: {detected}\n\n"
        "Update the game to an FSR 3.1+ build first, then scan compatibility again."
    )


def scan_for_managed_dlls(game_path):
    result = {name: [] for name in FSR_MANAGED_DLLS}

    if not game_path or not os.path.isdir(game_path):
        return result

    for folder, _, files in os.walk(game_path):
        norm_folder = folder.replace("/", "\\").lower()

        if "_xgcr_backups" in norm_folder:
            continue

        for file in files:
            for canonical in FSR_MANAGED_DLLS:
                if not file_name_matches(canonical, file):
                    continue

                full = os.path.join(folder, file)
                result[canonical].append(full)

                                                
    for canonical, paths in result.items():
        def score(path):
            rel = safe_relative(path, game_path).replace("/", "\\").lower()
            score_value = 0

            if rel.startswith("bin64\\") or "\\bin64\\" in rel:
                score_value += 100

            if "\\binaries\\" in rel or "\\win64\\" in rel or "\\x64\\" in rel:
                score_value += 40

            if os.path.basename(path).lower() == canonical.lower():
                score_value += 20

            return score_value

        result[canonical] = sorted(paths, key=score, reverse=True)

    return result


def path_inside(parent, child):
    try:
        parent_abs = os.path.abspath(parent)
        child_abs = os.path.abspath(child)
        return os.path.commonpath([parent_abs, child_abs]) == parent_abs
    except Exception:
        return False


def normalized_manual_fsr_targets(game, game_path):
    raw_targets = game.get("fsr_manual_targets", {}) if isinstance(game, dict) else {}
    if not isinstance(raw_targets, dict):
        return {}

    targets = {}
    for canonical in FSR_MANAGED_DLLS:
        path = str(raw_targets.get(canonical, "") or "").strip().strip('"')
        if not path:
            continue
        path = os.path.abspath(path)
        if os.path.isfile(path) and path_inside(game_path, path):
            targets[canonical] = path

    return targets


def detect_anti_cheat(game_path, max_depth=7, max_entries=8000):
    detected = set()

    if not game_path or not os.path.isdir(game_path):
        return []

    root = os.path.abspath(game_path)
    visited_entries = 0

    try:
        for folder, dirs, files in os.walk(root):
            visited_entries += len(dirs) + len(files)
            if visited_entries > max_entries:
                break

            try:
                rel = os.path.relpath(folder, root)
                depth = 0 if rel == "." else len(Path(rel).parts)
            except Exception:
                depth = max_depth + 1

            if depth >= max_depth:
                dirs[:] = []

            rel_key = rel.replace("/", "\\").lower()
            folder_name = os.path.basename(folder).lower()

            for marker, label in ANTI_CHEAT_DIR_MARKERS.items():
                if folder_name == marker or marker in rel_key:
                    detected.add(label)

            for file in files:
                label = ANTI_CHEAT_FILE_MARKERS.get(file.lower())
                if label:
                    detected.add(label)
    except Exception:
        return sorted(detected)

    return sorted(detected)


def analyze_game_support(game):
    game_path = game.get("path", "")
    manual_fsr_added = bool(game.get("fsr_manual_added", False)) or game.get("source") == "Manual FSR"

    result = {
        "game": game,
        "game_path": game_path,
        "target": "",
        "backup": "",
        "targets": {},
        "backups": {},
        "supported": False,
        "framegen_supported": False,
        "installed": False,
        "status": "Unsupported",
        "state": "unsupported",
        "fsr_game_dll_version": "Unknown",
        "fsr_game_dll_version_tuple": [],
        "fsr_game_dll_version_path": "",
        "fsr_game_dll_version_source": "game",
        "fsr_game_dll_version_supported": False,
        "fsr_min_game_dll_version": FSR_MIN_GAME_DLL_VERSION_TEXT,
        "manual_support_override": bool(game.get("fsr_manual_support", False)),
        "hidden": bool(game.get("fsr_hidden", False)),
        "manual_fsr_added": manual_fsr_added,
        "manual_fsr_targets": {},
        "anti_cheat_detected": False,
        "anti_cheat_names": [],
    }

    if not game_path or not os.path.isdir(game_path):
        return result

    anti_cheat_names = detect_anti_cheat(game_path)
    result["anti_cheat_names"] = anti_cheat_names
    result["anti_cheat_detected"] = bool(anti_cheat_names)

    manual_targets = normalized_manual_fsr_targets(game, game_path)
    result["manual_fsr_targets"] = dict(manual_targets)

    found = scan_for_managed_dlls(game_path)
    for canonical, target in manual_targets.items():
        existing = [path for path in found.get(canonical, []) if os.path.abspath(path).lower() != target.lower()]
        found[canonical] = [target] + existing
    primary_targets = found.get(FSR_UPSCALER_DLL, []) or found.get(FSR_LOADER_DLL, [])

    if not primary_targets:
        if manual_fsr_added:
            result["status"] = "No FSR Target"
            result["state"] = "no_target"
        return result

    targets = {}

    for canonical in FSR_MANAGED_DLLS:
        paths = found.get(canonical, [])

        if paths:
            targets[canonical] = os.path.abspath(paths[0])

    backups = {
        canonical: backup_path_for_target(game, target, game_path)
        for canonical, target in targets.items()
    }

    installed = any(
        is_target_currently_modded(target, backups.get(canonical, ""))
        for canonical, target in targets.items()
    )

    version_info = fsr_game_version_info(targets, backups, installed)
    result.update(version_info)

    if not version_info.get("fsr_game_dll_version_supported", False):
        result["target"] = targets.get(FSR_UPSCALER_DLL, "") or targets.get(FSR_LOADER_DLL, "")
        result["backup"] = backups.get(FSR_UPSCALER_DLL, "") or backups.get(FSR_LOADER_DLL, "")
        result["targets"] = targets
        result["backups"] = backups
        result["installed"] = installed
        override = bool(result.get("manual_support_override", False))
        result["supported"] = installed or override
        result["status"] = "Installed" if installed else ("Manual Support" if override else f"Needs FSR {FSR_MIN_GAME_DLL_VERSION_TEXT}+")
        result["state"] = "installed" if installed else ("manual" if override else "unsupported")
        return result

    framegen_supported = bool((targets.get(FSR_UPSCALER_DLL) or targets.get(FSR_LOADER_DLL)) and targets.get(FSR_FRAMEGEN_DLL))

    result["target"] = targets.get(FSR_UPSCALER_DLL, "") or targets.get(FSR_LOADER_DLL, "")
    result["backup"] = backups.get(FSR_UPSCALER_DLL, "") or backups.get(FSR_LOADER_DLL, "")
    result["targets"] = targets
    result["backups"] = backups
    result["supported"] = True
    result["framegen_supported"] = framegen_supported
    result["installed"] = installed
    result["status"] = "Installed" if installed else ("FSR + FG" if framegen_supported else "Supported")
    result["state"] = "installed" if installed else ("framegen" if framegen_supported else "supported")

    return result


def clean_gpu_name(name):
    name = str(name or "").strip()

    for junk in ("(TM)", "(tm)", "(R)", "(r)", "Graphics", "graphics"):
        name = name.replace(junk, "")

    return " ".join(name.split()).strip()


def gpu_vendor_color(name):
    lower = str(name or "").lower()

    if "amd" in lower or "radeon" in lower:
        return "#FF4D4D"

    if "intel" in lower or "arc" in lower or "uhd" in lower or "iris" in lower:
        return "#4DA3FF"

    if "nvidia" in lower or "geforce" in lower or "rtx" in lower or "gtx" in lower:
        return "#6BFF95"

    return "#888888"


def _gpu_names_from_registry():
    if os.name != "nt":
        return []

    names = []
    try:
        import winreg
    except Exception:
        return names

    base_path = r"SYSTEM\CurrentControlSet\Control\Video"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as base_key:
            guid_count = winreg.QueryInfoKey(base_key)[0]
            for guid_index in range(guid_count):
                try:
                    guid_name = winreg.EnumKey(base_key, guid_index)
                except OSError:
                    continue
                for sub_key in ("0000", "0001", "0002"):
                    path = f"{base_path}\\{guid_name}\\{sub_key}"
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as adapter_key:
                            for value_name in ("DriverDesc", "HardwareInformation.AdapterString"):
                                try:
                                    raw_value, _ = winreg.QueryValueEx(adapter_key, value_name)
                                except OSError:
                                    continue

                                value = raw_value
                                if isinstance(value, bytes):
                                    value = value.decode("utf-16-le", errors="ignore").replace("\x00", "")
                                value = str(value or "").strip()
                                if value and value not in names:
                                    names.append(value)
                    except OSError:
                        continue
    except OSError:
        return names

    return names


def _gpu_names_from_display_devices():
    if os.name != "nt":
        return []

    DISPLAY_DEVICE_MIRRORING_DRIVER = 0x00000008
    DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]

    names = []
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_display_devices = user32.EnumDisplayDevicesW
        enum_display_devices.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(DISPLAY_DEVICEW),
            wintypes.DWORD,
        ]
        enum_display_devices.restype = wintypes.BOOL
    except Exception:
        return names

    device_index = 0
    while True:
        device = DISPLAY_DEVICEW()
        device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not enum_display_devices(None, device_index, ctypes.byref(device), 0):
            break

        device_index += 1
        if device.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER:
            continue
        if not (device.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP):
            continue

        name = str(device.DeviceString or "").strip()
        if name and name not in names:
            names.append(name)

    return names


def get_primary_gpu_name():
    names = []

    if os.name == "nt":
        for detected_name in _gpu_names_from_registry():
            if detected_name not in names:
                names.append(detected_name)
        for detected_name in _gpu_names_from_display_devices():
            if detected_name not in names:
                names.append(detected_name)

    if not names:
        return "GPU: Unknown"

    filtered = [
        name for name in names
        if "microsoft basic" not in name.lower()
        and "remote" not in name.lower()
    ]

    if filtered:
        names = filtered

    for vendor in ("amd", "radeon", "nvidia", "geforce", "rtx", "gtx", "intel", "arc"):
        for name in names:
            if vendor in name.lower():
                return clean_gpu_name(name)

    return clean_gpu_name(names[0])


def cache_safe_game(game):
    allowed = (
        "appid",
        "name",
        "path",
        "source",
        "poster",
        "poster_status",
        "size",
        "manifest_size",
        "compressed_size",
        "compression_algorithm",
        "status",
        "exe_path",
        "fsr_manual_support",
        "fsr_hidden",
        "fsr_manual_added",
        "fsr_manual_targets",
    )

    return {key: game.get(key, "") for key in allowed}


def cache_safe_support_info(info):
    game = cache_safe_game(info.get("game", {}))

    return {
        "game": game,
        "game_path": info.get("game_path", ""),
        "target": info.get("target", ""),
        "backup": info.get("backup", ""),
        "targets": info.get("targets", {}),
        "backups": info.get("backups", {}),
        "supported": bool(info.get("supported", False)),
        "framegen_supported": bool(info.get("framegen_supported", False)),
        "installed": bool(info.get("installed", False)),
        "status": info.get("status", "Unsupported"),
        "state": info.get("state", "unsupported"),
        "fsr_game_dll_version": info.get("fsr_game_dll_version", "Unknown"),
        "fsr_game_dll_version_tuple": info.get("fsr_game_dll_version_tuple", []),
        "fsr_game_dll_version_path": info.get("fsr_game_dll_version_path", ""),
        "fsr_game_dll_version_source": info.get("fsr_game_dll_version_source", "game"),
        "fsr_game_dll_version_supported": bool(info.get("fsr_game_dll_version_supported", False)),
        "fsr_min_game_dll_version": info.get("fsr_min_game_dll_version", FSR_MIN_GAME_DLL_VERSION_TEXT),
        "manual_support_override": bool(info.get("manual_support_override", False)),
        "hidden": bool(info.get("hidden", False)),
        "manual_fsr_added": bool(info.get("manual_fsr_added", False)),
        "manual_fsr_targets": info.get("manual_fsr_targets", {}),
        "anti_cheat_detected": bool(info.get("anti_cheat_detected", False)),
        "anti_cheat_names": info.get("anti_cheat_names", []),
    }


def game_override_key(game):
    if not isinstance(game, dict):
        return ""

    appid = str(game.get("appid", "") or "").strip().lower()
    source = str(game.get("source", "") or "").strip().lower()

    if appid:
        return f"{source}:{appid}"

    path = str(game.get("path", "") or "")
    if path:
        return os.path.abspath(path).lower()

    return str(game.get("name", "") or "").strip().lower()


def support_info_override_key(info):
    if not isinstance(info, dict):
        return ""

    game = info.get("game", {})
    key = game_override_key(game)

    if key:
        return key

    game_path = str(info.get("game_path", "") or "")
    if game_path:
        return os.path.abspath(game_path).lower()

    return ""


def apply_manual_support_override(info, enabled):
    if not isinstance(info, dict):
        return info

    info["manual_support_override"] = bool(enabled)
    game = info.get("game", {})

    if isinstance(game, dict):
        game["fsr_manual_support"] = bool(enabled)

    if info.get("target") and not info.get("fsr_game_dll_version_supported", False):
        installed = bool(info.get("installed", False))
        info["supported"] = installed or bool(enabled)
        info["framegen_supported"] = False
        info["state"] = "installed" if installed else ("manual" if enabled else "unsupported")
        info["status"] = "Installed" if installed else ("Manual Support" if enabled else f"Needs FSR {FSR_MIN_GAME_DLL_VERSION_TEXT}+")

    return info


def apply_hidden_state(info, hidden):
    if not isinstance(info, dict):
        return info

    info["hidden"] = bool(hidden)
    game = info.get("game", {})

    if isinstance(game, dict):
        game["fsr_hidden"] = bool(hidden)

    return info


def is_manual_fsr_info(info):
    if not isinstance(info, dict):
        return False
    game = info.get("game", {})
    return bool(info.get("manual_fsr_added", False)) or (
        isinstance(game, dict)
        and bool(game.get("fsr_manual_added", False))
    )


def should_show_fsr_info(info):
    return bool(info.get("supported") or info.get("target") or is_manual_fsr_info(info))


def merge_fsr_games(*game_lists):
    clean = []
    seen = set()

    for games in game_lists:
        for game in games or []:
            if not isinstance(game, dict):
                continue

            path = os.path.abspath(str(game.get("path", ""))) if game.get("path") else ""
            appid = str(game.get("appid", "") or "").strip().lower()
            source = str(game.get("source", "") or "").strip().lower()
            key = f"{source}:{appid}" if appid else path.lower()

            if not path or key in seen or not saved_game_is_installed(game):
                continue

            seen.add(key)
            clean.append(game)

    return clean


def refresh_support_install_states(support_infos):
    visible = [
        info for info in support_infos or []
        if support_info_game_is_installed(info)
    ]

    for info in visible:
        game = info.get("game", {})
        game_path = info.get("game_path", "")
        targets = info.get("targets", {}) or {}
        backups = info.get("backups", {}) or {}
        manual_targets = normalized_manual_fsr_targets(game, game_path)
        if manual_targets:
            info["manual_fsr_targets"] = dict(manual_targets)
            merged_targets = dict(targets)
            merged_targets.update(manual_targets)
            targets = merged_targets
            info["targets"] = targets

        anti_cheat_names = detect_anti_cheat(game_path)
        info["anti_cheat_names"] = anti_cheat_names
        info["anti_cheat_detected"] = bool(anti_cheat_names)

        if not targets and info.get("target"):
            targets = {FSR_UPSCALER_DLL: info.get("target")}
            info["targets"] = targets

        if not targets:
            info["backups"] = backups
            info["supported"] = False
            info["framegen_supported"] = False
            info["installed"] = False
            info["state"] = "no_target" if is_manual_fsr_info(info) else "unsupported"
            info["status"] = "No FSR Target" if is_manual_fsr_info(info) else "Unsupported"
            continue

        for canonical, target in list(targets.items()):
            if canonical not in backups:
                backups[canonical] = backup_path_for_target(game, target, game_path)

        info["backups"] = backups

        installed = any(
            is_target_currently_modded(target, backups.get(canonical, ""))
            for canonical, target in targets.items()
        )

        version_info = fsr_game_version_info(targets, backups, installed)
        info.update(version_info)

        if not version_info.get("fsr_game_dll_version_supported", False):
            override = bool(info.get("manual_support_override", False))
            info["supported"] = installed or override
            info["framegen_supported"] = False
            info["installed"] = installed
            info["state"] = "installed" if installed else ("manual" if override else "unsupported")
            info["status"] = "Installed" if installed else ("Manual Support" if override else f"Needs FSR {FSR_MIN_GAME_DLL_VERSION_TEXT}+")
            continue

        framegen_supported = bool(targets.get(FSR_FRAMEGEN_DLL))

        info["supported"] = True
        info["framegen_supported"] = framegen_supported
        info["installed"] = installed
        info["state"] = "installed" if installed else ("framegen" if framegen_supported else "supported")
        info["status"] = "Installed" if installed else ("FSR + FG" if framegen_supported else "Supported")

    return [
        info for info in visible
        if should_show_fsr_info(info)
    ]


class FsrCompatibilityScanWorker(QThread):
    scan_done = pyqtSignal(object, object, object)
    log = pyqtSignal(str)

    def __init__(self, base_games, loaded_games, manual_games, include_dynamic, overrides, hidden, deleted):
        super().__init__()
        self.base_games = list(base_games or [])
        self.loaded_games = list(loaded_games or [])
        self.manual_games = list(manual_games or [])
        self.include_dynamic = bool(include_dynamic)
        self.overrides = dict(overrides or {})
        self.hidden = dict(hidden or {})
        self.deleted = set(deleted or [])

    def run(self):
        fallback_games = []
        dynamic_games = []

        if not self.base_games and not self.loaded_games:
            fallback_games = scan_steam_games_fallback()

        if self.include_dynamic:
            try:
                from source.xzen_engine.stores import scan_all_store_games
                dynamic_games = scan_all_store_games()
            except Exception as exc:
                self.log.emit(f"Dynamic store scan failed: {exc}")
                dynamic_games = scan_steam_games_fallback()

        games = merge_fsr_games(self.manual_games, self.base_games, self.loaded_games, fallback_games, dynamic_games)
        games = [game for game in games if game_override_key(game) not in self.deleted]
        all_support = [
            info for info in (analyze_game_support(game) for game in games)
            if support_info_override_key(info) not in self.deleted
        ]

        for info in all_support:
            key = support_info_override_key(info)
            if key in self.overrides:
                apply_manual_support_override(info, self.overrides[key])
            if key in self.hidden:
                apply_hidden_state(info, self.hidden[key])

        visible_support = refresh_support_install_states([
            info for info in all_support
            if should_show_fsr_info(info)
        ])

        self.scan_done.emit(games, all_support, visible_support)


class FsrGameCard(QFrame):
    install_version_clicked = pyqtSignal(int, str)
    install_version_mode_clicked = pyqtSignal(int, str, str)
    restore_clicked = pyqtSignal(int)
    launch_clicked = pyqtSignal(int)
    support_override_clicked = pyqtSignal(int)
    hidden_state_clicked = pyqtSignal(int)
    manual_targets_clicked = pyqtSignal(int)
    delete_clicked = pyqtSignal(int)

    def __init__(
        self,
        index,
        support_info,
        versions,
        card_width=MIN_CARD_W,
        poster_width=None,
        poster_height=None,
        parent=None,
    ):
        super().__init__(parent)

        self.index = index
        self.info = support_info
        self.game = support_info.get("game", {})
        self.versions = versions or []
        self.poster_width = int(poster_width or max(1, card_width - POSTER_W_PADDING))
        self.poster_height = int(poster_height or self.poster_width * POSTER_ASPECT)

        self.setFixedSize(int(card_width), int(self.poster_height + CARD_H_EXTRA + 38))
        self.setObjectName("FsrGameCard")
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        self.poster = QLabel(self)
        self.poster.setFixedSize(self.poster_width, self.poster_height)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("FsrPoster")
        self.load_poster()

        self.poster_stack = QWidget(self)
        self.poster_stack.setFixedSize(self.poster_width, self.poster_height)
        self.poster_stack.setContextMenuPolicy(Qt.CustomContextMenu)
        self.poster_stack.customContextMenuRequested.connect(
            lambda pos: self.open_action_menu(self.poster_stack.mapToGlobal(pos))
        )
        self.poster.setContextMenuPolicy(Qt.CustomContextMenu)
        self.poster.customContextMenuRequested.connect(
            lambda pos: self.open_action_menu(self.poster.mapToGlobal(pos))
        )
        poster_stack_layout = QStackedLayout(self.poster_stack)
        poster_stack_layout.setContentsMargins(0, 0, 0, 0)
        poster_stack_layout.setStackingMode(QStackedLayout.StackAll)
        poster_stack_layout.addWidget(self.poster)

        self.name_label = QLabel(self.game.get("name", "Unknown"), self)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("FsrCardName")

        state_row = QHBoxLayout()
        state_row.setSpacing(6)

        self.status_label = QLabel(self.status_text(), self)
        self.status_label.setObjectName("FsrStatusText")

        state_row.addStretch()
        state_row.addWidget(self.status_label)
        state_row.addStretch()

        self.anti_cheat_label = QLabel("Anti-cheat", self.poster_stack)
        self.anti_cheat_label.setObjectName("FsrAntiCheatPill")
        self.anti_cheat_label.setAlignment(Qt.AlignCenter)
        names = support_info.get("anti_cheat_names", []) or []
        if names:
            self.anti_cheat_label.setToolTip(", ".join(names))
        self.anti_cheat_label.setVisible(bool(support_info.get("anti_cheat_detected", False)))

        anti_overlay = QWidget(self.poster_stack)
        anti_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        anti_layout = QVBoxLayout(anti_overlay)
        anti_layout.setContentsMargins(6, 6, 6, 6)
        anti_layout.addWidget(self.anti_cheat_label, alignment=Qt.AlignTop | Qt.AlignRight)
        anti_layout.addStretch()
        poster_stack_layout.addWidget(anti_overlay)

        self.target_label = QLabel("", self)
        self.target_label.hide()

        self.install_btn = QPushButton("Install FSR4", self)
        self.install_btn.setObjectName("CardActionButton")
        self.install_btn.setProperty("state", "enable")
        self.install_btn.clicked.connect(self.open_version_menu)

        self.launch_btn = QPushButton("Launch Game", self)
        self.launch_btn.setObjectName("CardActionButton")
        self.launch_btn.setProperty("state", "enable")
        self.launch_btn.clicked.connect(lambda: self.launch_clicked.emit(self.index))

        self.restore_btn = QPushButton("Restore", self)
        self.restore_btn.setObjectName("CardActionButton")
        self.restore_btn.setProperty("state", "disable")
        self.restore_btn.clicked.connect(lambda: self.restore_clicked.emit(self.index))

        self.override_btn = QPushButton(self.override_text(), self)
        self.override_btn.setObjectName("CardActionButton")
        self.override_btn.setProperty("state", "enable" if not support_info.get("manual_support_override") else "disable")
        self.override_btn.clicked.connect(lambda: self.support_override_clicked.emit(self.index))

        installed = bool(support_info.get("installed", False))
        can_install = bool(support_info.get("supported", False))

        self.install_btn.setVisible(not installed and can_install)
        self.restore_btn.setVisible(installed)
        self.override_btn.setVisible(
            bool(support_info.get("target"))
            and not installed
            and not bool(support_info.get("fsr_game_dll_version_supported", False))
        )

        if not self.versions:
            self.install_btn.setEnabled(False)
            self.install_btn.setText("Missing FSR")

        layout.addWidget(self.poster_stack, alignment=Qt.AlignCenter)
        layout.addWidget(self.name_label)
        layout.addLayout(state_row)
        layout.addStretch()
        layout.addWidget(self.launch_btn)
        layout.addWidget(self.install_btn)
        layout.addWidget(self.restore_btn)
        layout.addWidget(self.override_btn)

    def contextMenuEvent(self, event):
        self.open_action_menu(event.globalPos())
        event.accept()

    def open_action_menu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(FSR_PAGE_STYLE + PURPLE_SCROLLBAR_STYLE)
        path_label = "Edit FSR DLL Paths" if self.info.get("target") or self.info.get("manual_fsr_targets") else "Add FSR DLL Paths"
        manual_action = menu.addAction(path_label)
        hide_action = menu.addAction("Unhide Game" if self.info.get("hidden") else "Hide Game")
        delete_action = menu.addAction("Delete From FSR Tab")
        selected = menu.exec_(global_pos)

        if selected == manual_action:
            self.manual_targets_clicked.emit(self.index)
        elif selected == hide_action:
            self.hidden_state_clicked.emit(self.index)
        elif selected == delete_action:
            self.delete_clicked.emit(self.index)

    def status_text(self):
        if self.info.get("installed"):
            return "Installed"

        if not self.info.get("target"):
            return "No FSR target"

        if self.info.get("manual_support_override"):
            return "Manual"

        if self.info.get("target") and not self.info.get("fsr_game_dll_version_supported", False):
            version = str(self.info.get("fsr_game_dll_version", "Unknown") or "Unknown")
            return f"FSR {version}"

        if self.info.get("framegen_supported"):
            return "FSR + FG"

        return "Supported"

    def override_text(self):
        if self.info.get("manual_support_override"):
            return "Mark Unsupported"

        return "Mark Supported"

    def menu_version_label(self, version):
        version = str(version or "Unknown").strip()

        if version.lower().startswith("fsr "):
            return version

        return f"FSR {version}"

    def open_version_menu(self):
        if not self.versions:
            return

        menu = QMenu(self)
        menu.setStyleSheet(FSR_PAGE_STYLE + PURPLE_SCROLLBAR_STYLE)

        panel = QWidget(menu)
        panel.setObjectName("FsrVersionMenuPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(2)

        game_has_fg = bool(self.info.get("framegen_supported", False))
        added_any = False

        for item in self.versions:
            version = item.get("version", "Unknown")
            files = item.get("files", {}) or {}
            version_valid = bool(item.get("valid", False))
            version_has_fg = bool(item.get("has_fg", False))

            if not version_valid:
                disabled_btn = QPushButton(self.menu_version_label(version), panel)
                disabled_btn.setObjectName("FsrVersionMenuButton")
                disabled_btn.setEnabled(False)
                disabled_btn.setToolTip("This folder has no usable FSR DLL.")
                panel_layout.addWidget(disabled_btn)
                added_any = True
                continue

                                                                              
            fsr_btn = QPushButton(self.menu_version_label(version), panel)
            fsr_btn.setObjectName("FsrVersionMenuButton")
            fsr_btn.setEnabled(True)
            fsr_btn.setToolTip("Install upscaler only.")
            fsr_btn.clicked.connect(
                lambda checked=False, v=version, m=menu: (
                    m.close(),
                    self.install_version_mode_clicked.emit(self.index, v, "fsr")
                )
            )
            panel_layout.addWidget(fsr_btn)
            added_any = True

                                                                                      
                                                                         
            if version_has_fg:
                fg_btn = QPushButton(f"{self.menu_version_label(version)} + Frame Gen", panel)
                fg_btn.setObjectName("FsrVersionMenuButton")
                fg_btn.setEnabled(game_has_fg)

                if game_has_fg:
                    fg_btn.setToolTip("Install upscaler + frame generation files.")
                else:
                    fg_btn.setToolTip("This game has FSR, but no frame generation target DLLs.")

                fg_btn.clicked.connect(
                    lambda checked=False, v=version, m=menu: (
                        m.close(),
                        self.install_version_mode_clicked.emit(self.index, v, "fg")
                    )
                )
                panel_layout.addWidget(fg_btn)
                added_any = True

        if not added_any:
            empty_btn = QPushButton("No FSR versions found", panel)
            empty_btn.setObjectName("FsrVersionMenuButton")
            empty_btn.setEnabled(False)
            panel_layout.addWidget(empty_btn)

        panel_layout.addStretch()

        scroll = QScrollArea(menu)
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setStyleSheet(PURPLE_SCROLLBAR_STYLE)
        scroll.setMinimumWidth(285)
        scroll.setMaximumHeight(260)

        action = QWidgetAction(menu)
        action.setDefaultWidget(scroll)
        menu.addAction(action)

        menu.exec_(self.install_btn.mapToGlobal(self.install_btn.rect().bottomLeft()))

    def load_poster(self):
        poster_path = self.game.get("poster", "")

        if poster_path and os.path.exists(poster_path):
            poster_path = sanitize_png_file(poster_path)
            pixmap = QPixmap(poster_path)

            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.poster_width,
                    self.poster_height,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                self.poster.setPixmap(pixmap)
                return

        if self.info.get("installed"):
            text = "FSR4\nInstalled"
        elif not self.info.get("target"):
            text = "No FSR\nTarget"
        elif self.info.get("framegen_supported"):
            text = "FSR4\nFG Ready"
        else:
            text = "FSR4\nSupported"

        self.poster.setText(text)
        self.poster.setStyleSheet("background: transparent; color:#ffffff; border:none;")


class XGCRFsrModsPage(QWidget):
    def __init__(self, get_games_func=None, get_selected_index_func=None, external_log_func=None):
        super().__init__()

        self.get_games = get_games_func
        self.get_selected_index = get_selected_index_func
        self.external_log = external_log_func

        self.fsr_versions = []
        self.fsr_version = "Missing"
        self.gpu_name = "GPU: Detecting..."

        self.has_scanned = False
        self.cache_loaded = False
        self.cache_path = get_writable_app_file(FSR_SCAN_CACHE_FILE)
        self._deferred_refresh_scheduled = False

        self.all_games_cache = []
        self.all_support_cache = []
        self.visible_support_cache = []
        self.manual_fsr_games = []
        self.deleted_fsr_keys = set()
        self.fsr_view_mode = "visible"
        self.current_columns = 0
        self.current_card_width = 0
        self.reflow_pending = False
        self.scan_worker = None
        self.scan_save_cache = False
        self.busy_overlay = None
        self.busy_spinner = None
        self.busy_label = None
        self.busy_overlay_suppressed = False
        self.pending_render = False
        self.pending_refresh_disk = False

        self.setObjectName("DashboardPage")
        self.setStyleSheet(FSR_PAGE_STYLE)

        self.build_ui()
        self.update_header(0, 0)
        self.show_initial_state()
        QTimer.singleShot(0, self._bootstrap_after_show)

    def _bootstrap_after_show(self):
        self.load_scan_cache_or_initial_state()
        QTimer.singleShot(0, self._refresh_gpu_name)

    def _refresh_gpu_name(self):
        self.gpu_name = get_primary_gpu_name()
        supported_count = len(
            [info for info in self.visible_support_cache if info.get("supported") and not info.get("hidden")]
        )
        unsupported_count = max(0, len(self.all_games_cache) - supported_count)
        self.update_header(supported_count, unsupported_count)

    def schedule_deferred_disk_refresh(self):
        if self._deferred_refresh_scheduled:
            return
        self._deferred_refresh_scheduled = True
        QTimer.singleShot(40, self._run_deferred_disk_refresh)

    def _run_deferred_disk_refresh(self):
        self._deferred_refresh_scheduled = False
        if not self.has_scanned or not self.visible_support_cache:
            return
        self.render_current_results(refresh_disk=True)

    def grid_metrics(self):
        available = self.width()
        if hasattr(self, "scroll"):
            available = max(available, self.scroll.width(), self.scroll.viewport().width())
        available = max(MIN_CARD_W, int(available or MIN_CARD_W))
        columns = max(1, (available + GRID_SPACING) // (MIN_CARD_W + GRID_SPACING))
        card_width = int((available - (GRID_SPACING * (columns - 1))) / columns)
        card_width = max(MIN_CARD_W, min(MAX_CARD_W, card_width))
        poster_width = max(1, card_width - POSTER_W_PADDING)
        poster_height = int(poster_width * POSTER_ASPECT)
        return int(columns), int(card_width), int(poster_width), int(poster_height)

    def schedule_grid_reflow(self):
        if self.reflow_pending:
            return
        self.reflow_pending = True
        QTimer.singleShot(0, self.reflow_current_grid)
        QTimer.singleShot(80, self.reflow_current_grid)

    def reflow_current_grid(self):
        self.reflow_pending = False
        if not self.isVisible() or not self.visible_support_cache:
            return
        columns, card_width, _, _ = self.grid_metrics()
        if columns != self.current_columns or abs(card_width - self.current_card_width) >= 4:
            self.render_current_results(refresh_disk=False)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QFrame(self)
        header.setObjectName("FsrHeaderPanel")

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        self.title_label = QLabel("FSR Mods", header)
        self.title_label.setObjectName("FsrTitle")

        self.counter_label = QLabel("Supported: 0 | Unsupported: 0", header)
        self.counter_label.setObjectName("FsrCounter")

        self.fsr_label = QLabel("FSR: Missing", header)
        self.fsr_label.setObjectName("FsrVersionText")
        self.fsr_label.hide()

        self.cache_label = QLabel("", header)
        self.cache_label.setObjectName("FsrCacheText")
        self.cache_label.hide()

        title_col.addWidget(self.title_label)
        title_col.addWidget(self.counter_label)
        title_col.addWidget(self.cache_label)

        self.scan_btn = QPushButton("Refresh", header)
        self.scan_btn.setObjectName("FsrScanIconButton")
        self.scan_btn.setToolTip("Refresh FSR compatibility")
        self.scan_btn.clicked.connect(self.scan_compatibility)

        self.add_manual_btn = QPushButton("Add Game", header)
        self.add_manual_btn.setObjectName("FsrManualButton")
        self.add_manual_btn.setToolTip("Add a game to the FSR page")
        self.add_manual_btn.clicked.connect(self.open_manual_fsr_add_dialog)

        self.gpu_label = QLabel(self.gpu_name, header)
        self.gpu_label.setObjectName("GpuNameText")
        self.gpu_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        right_col.addWidget(self.gpu_label, alignment=Qt.AlignRight)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        scan_row.addWidget(self.add_manual_btn)
        scan_row.addWidget(self.scan_btn)
        right_col.addLayout(scan_row)

        header_layout.addLayout(title_col)
        header_layout.addStretch()
        header_layout.addLayout(right_col)

        layout.addWidget(header)

        tabs = QHBoxLayout()
        tabs.setObjectName("FsrViewTabs")
        tabs.setSpacing(8)

        self.visible_tab_btn = QPushButton("Games", self)
        self.visible_tab_btn.setObjectName("FsrViewTab")
        self.visible_tab_btn.clicked.connect(lambda: self.set_fsr_view_mode("visible"))

        self.hidden_tab_btn = QPushButton("Hidden", self)
        self.hidden_tab_btn.setObjectName("FsrViewTab")
        self.hidden_tab_btn.clicked.connect(lambda: self.set_fsr_view_mode("hidden"))

        tabs.addWidget(self.visible_tab_btn)
        tabs.addWidget(self.hidden_tab_btn)
        tabs.addStretch()
        layout.addLayout(tabs)
        self.update_fsr_view_tabs()

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(PURPLE_SCROLLBAR_STYLE)

        self.grid_container = QWidget(self.scroll)
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(GRID_SPACING)
        self.grid_layout.setVerticalSpacing(GRID_SPACING)

        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, stretch=1)

        self.empty_panel = QFrame(self)
        self.empty_panel.setObjectName("FsrEmptyPanel")

        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.setContentsMargins(20, 20, 20, 20)

        self.empty_label = QLabel("Press Refresh to scan compatibility.", self.empty_panel)
        self.empty_label.setObjectName("FsrEmptyText")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)

        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addStretch()

        layout.addWidget(self.empty_panel, stretch=1)
        self.empty_panel.hide()

        self.build_busy_overlay()

    def build_busy_overlay(self):
        self.busy_overlay = QFrame(self)
        self.busy_overlay.setWindowFlags(Qt.Widget)
        self.busy_overlay.setObjectName("FsrBusyOverlay")
        self.busy_overlay.setAttribute(Qt.WA_StyledBackground, True)
        self.busy_overlay.setStyleSheet(
            """
            #FsrBusyOverlay {
                background: rgba(8, 7, 14, 174);
                border: 1px solid rgba(179, 138, 255, 0.22);
                border-radius: 10px;
            }
            #FsrBusyText {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
                background: transparent;
            }
            """
        )
        self.busy_overlay.hide()

        overlay_layout = QVBoxLayout(self.busy_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(12)
        overlay_layout.setAlignment(Qt.AlignCenter)

        self.busy_spinner = LoadingSpinner(self.busy_overlay)
        self.busy_label = QLabel("Working...", self.busy_overlay)
        self.busy_label.setObjectName("FsrBusyText")
        self.busy_label.setAlignment(Qt.AlignCenter)

        overlay_layout.addWidget(self.busy_spinner, alignment=Qt.AlignCenter)
        overlay_layout.addWidget(self.busy_label, alignment=Qt.AlignCenter)
        self.position_busy_overlay()

    def position_busy_overlay(self):
        if not self.busy_overlay:
            return
        self.busy_overlay.setGeometry(self.rect())
        self.busy_overlay.raise_()

    def set_busy_overlay(self, visible, text="Working..."):
        if not self.busy_overlay:
            return
        self.busy_label.setText(str(text or "Working..."))
        self.position_busy_overlay()
        if visible and self.isVisible() and not self.busy_overlay_suppressed:
            self.busy_overlay.show()
            self.busy_overlay.raise_()
            self.busy_spinner.start()
        else:
            self.busy_spinner.stop()
            self.busy_overlay.hide()

    def show_initial_state(self):
        self.scroll.hide()
        self.empty_panel.show()
        self.empty_label.setText("Press Refresh to scan compatibility.")

    def update_fsr_view_tabs(self):
        if not hasattr(self, "visible_tab_btn"):
            return

        for mode, button in (("visible", self.visible_tab_btn), ("hidden", self.hidden_tab_btn)):
            button.setProperty("active", "true" if self.fsr_view_mode == mode else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def set_fsr_view_mode(self, mode):
        self.fsr_view_mode = "hidden" if mode == "hidden" else "visible"
        self.update_fsr_view_tabs()
        self.render_current_results(refresh_disk=False)

    def log(self, text):
        if self.external_log:
            try:
                self.external_log(text)
            except Exception:
                pass

    def games_from_callback(self):
        if not self.get_games:
            return []

        try:
            games = self.get_games() or []
            if isinstance(games, list):
                return games
        except Exception:
            pass

        return []

    def merge_games(self, *game_lists):
        return merge_fsr_games(*game_lists)

    def library_games(self):
        return self.merge_games(self.games_from_callback(), load_games_from_json())

    def mark_manual_fsr_games(self):
        for game in self.manual_fsr_games:
            if isinstance(game, dict):
                game["fsr_manual_added"] = True

        manual_keys = {
            game_override_key(game)
            for game in self.manual_fsr_games
            if isinstance(game, dict)
        }

        for info in self.all_support_cache:
            game = info.get("game", {}) if isinstance(info, dict) else {}
            if game_override_key(game) in manual_keys:
                info["manual_fsr_added"] = True
                if isinstance(game, dict):
                    game["fsr_manual_added"] = True

    def is_deleted_fsr_key(self, key):
        return bool(key and key in self.deleted_fsr_keys)

    def filter_deleted_games(self, games):
        return [
            game for game in games or []
            if not self.is_deleted_fsr_key(game_override_key(game))
        ]

    def filter_deleted_support(self, infos):
        return [
            info for info in infos or []
            if not self.is_deleted_fsr_key(support_info_override_key(info))
        ]

    def scan_dynamic_store_games(self):
        try:
            from source.xzen_engine.stores import scan_all_store_games
            return scan_all_store_games()
        except Exception as exc:
            self.log(f"Dynamic store scan failed: {exc}")
            return scan_steam_games_fallback()

    def games(self, include_dynamic=False):
        self.mark_manual_fsr_games()
        games = self.games_from_callback()

        loaded_games = load_games_from_json()
        fallback_games = [] if games or loaded_games else scan_steam_games_fallback()
        dynamic_games = self.scan_dynamic_store_games() if include_dynamic else []
        clean = self.merge_games(self.manual_fsr_games, games, loaded_games, fallback_games, dynamic_games)
        clean = self.filter_deleted_games(clean)

        self.all_games_cache = clean
        return clean

    def manual_fsr_game_from_folder(self, folder):
        if not folder:
            return None

        path = os.path.abspath(str(folder))
        if not os.path.isdir(path):
            return None

        exe_path = find_game_executable(path) or ""
        return {
            "appid": "",
            "name": os.path.basename(path.rstrip("\\/")) or "Manual FSR Game",
            "path": path,
            "source": "Manual FSR",
            "poster": "",
            "poster_status": "Manual",
            "size": 0,
            "manifest_size": 0,
            "compressed_size": 0,
            "compression_algorithm": "",
            "status": "Manual FSR",
            "exe_path": exe_path,
            "fsr_manual_added": True,
        }

    def upsert_manual_fsr_game(self, game):
        if not isinstance(game, dict) or not game.get("path"):
            return None

        manual_game = dict(game)
        manual_game["path"] = os.path.abspath(str(manual_game.get("path", "")))
        manual_game["source"] = manual_game.get("source") or "Manual FSR"
        manual_game["fsr_manual_added"] = True
        key = game_override_key(manual_game)
        updated = False

        for index, existing in enumerate(list(self.manual_fsr_games)):
            if game_override_key(existing) == key:
                self.manual_fsr_games[index] = manual_game
                updated = True
                break

        if not updated:
            self.manual_fsr_games.append(manual_game)

        self.manual_fsr_games = self.merge_games(self.manual_fsr_games)
        self.deleted_fsr_keys.discard(key)
        return manual_game

    def replace_cached_game(self, games, game):
        key = game_override_key(game)
        output = []
        replaced = False

        for existing in games or []:
            if game_override_key(existing) == key:
                if not replaced:
                    output.append(game)
                    replaced = True
                continue
            output.append(existing)

        if not replaced:
            output.append(game)

        return output

    def replace_cached_support(self, infos, info):
        key = support_info_override_key(info)
        output = []
        replaced = False

        for existing in infos or []:
            if support_info_override_key(existing) == key:
                if not replaced:
                    output.append(info)
                    replaced = True
                continue
            output.append(existing)

        if not replaced:
            output.append(info)

        return output

    def add_manual_fsr_game(self, game):
        game = self.upsert_manual_fsr_game(game)
        if not game:
            QMessageBox.warning(self, "FSR Mods", "That game folder could not be added.")
            return

        overrides = self.manual_support_override_map()
        hidden = self.hidden_state_map()
        info = analyze_game_support(game)
        key = support_info_override_key(info)

        if key in overrides:
            apply_manual_support_override(info, overrides[key])
        if key in hidden:
            apply_hidden_state(info, hidden[key])

        self.has_scanned = True
        self.all_games_cache = self.replace_cached_game(self.all_games_cache, game)
        self.all_support_cache = self.replace_cached_support(self.all_support_cache, info)
        visible_candidates = [
            item for item in self.all_support_cache
            if should_show_fsr_info(item)
        ]
        self.visible_support_cache = refresh_support_install_states(visible_candidates)
        self.save_scan_cache()
        self.render_current_results(refresh_disk=False, force=True)

        if info.get("target"):
            self.log(f"Manual FSR game added: {game.get('name', 'Unknown')}")
        else:
            self.log(f"Manual FSR game added, but no FSR target was found: {game.get('name', 'Unknown')}")

    def open_manual_fsr_add_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add FSR Game")
        dialog.setObjectName("FsrManualDialog")
        dialog.setModal(True)
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet(FSR_PAGE_STYLE)

        selected = {"game": None}
        library_games = self.library_games()

        root = QVBoxLayout(dialog)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Add FSR Game", dialog)
        title.setObjectName("FsrManualTitle")

        hint = QLabel("Choose a game already saved in Game Library, or add a folder manually.", dialog)
        hint.setObjectName("FsrManualHint")
        hint.setWordWrap(True)

        combo = QComboBox(dialog)
        combo.setObjectName("FsrManualCombo")
        combo.setView(QListView(combo))
        combo.setMinimumHeight(42)

        for game in library_games:
            name = str(game.get("name", "Unknown"))
            source = str(game.get("source", "Library"))
            path = str(game.get("path", ""))
            combo.addItem(f"{name}  -  {source}", dict(game))
            combo.setItemData(combo.count() - 1, path, Qt.ToolTipRole)

        if not library_games:
            combo.addItem("No saved Game Library entries found", None)
            combo.setEnabled(False)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        cancel_btn = QPushButton("Cancel", dialog)
        cancel_btn.setObjectName("FsrManualGhost")

        folder_btn = QPushButton("Choose Folder", dialog)
        folder_btn.setObjectName("FsrManualGhost")

        add_btn = QPushButton("Add Selected", dialog)
        add_btn.setObjectName("FsrManualPrimary")
        add_btn.setEnabled(bool(library_games))

        def choose_folder():
            picker = QFileDialog(dialog, "Choose FSR Game Folder")
            picker.setFileMode(QFileDialog.Directory)
            picker.setOption(QFileDialog.ShowDirsOnly, True)
            if picker.exec_() != QFileDialog.Accepted:
                return
            folders = picker.selectedFiles()
            if not folders:
                return
            selected["game"] = self.manual_fsr_game_from_folder(folders[0])
            dialog.accept()

        def add_selected():
            game = combo.currentData()
            if isinstance(game, dict):
                selected["game"] = dict(game)
                dialog.accept()

        folder_btn.clicked.connect(choose_folder)
        add_btn.clicked.connect(add_selected)
        cancel_btn.clicked.connect(dialog.reject)

        actions.addWidget(cancel_btn)
        actions.addStretch()
        actions.addWidget(folder_btn)
        actions.addWidget(add_btn)

        root.addWidget(title)
        root.addWidget(hint)
        root.addWidget(combo)
        root.addLayout(actions)

        if dialog.exec_() == QDialog.Accepted and selected.get("game"):
            self.add_manual_fsr_game(selected["game"])

    def find_version_file(self, version_dir, canonical_name):
                                             
                                                     
        exact = version_dir / canonical_name

        if exact.exists() and exact.is_file():
            return str(exact.resolve())

        dlls = []

        try:
            dlls = [file for file in version_dir.rglob("*.dll") if file.is_file()]
        except Exception:
            return ""

        matches = [file for file in dlls if file_name_matches(canonical_name, file.name)]

                   
                                                                                      
                                                                           
        if not matches and canonical_name == FSR_UPSCALER_DLL and len(dlls) == 1:
            one = dlls[0]
            classified = classify_fsr_dll_name(one.name)

            if classified in ("", FSR_UPSCALER_DLL):
                matches.append(one)

        if not matches:
            return ""

        def score(path):
            rel = str(path.relative_to(version_dir)).replace("/", "\\").lower()
            score_value = 0

            if path.name.lower() == canonical_name.lower():
                score_value += 100

            classified = classify_fsr_dll_name(path.name)
            if classified == canonical_name:
                score_value += 80

            if "\\" not in rel:
                score_value += 50

            if "\\bin64\\" in f"\\{rel}" or "\\x64\\" in f"\\{rel}" or "\\win64\\" in f"\\{rel}":
                score_value += 25

            return score_value

        matches.sort(key=score, reverse=True)
        return str(matches[0].resolve())

    def find_fsr_versions(self):
        script_dir = Path(__file__).resolve().parent
        cwd = Path.cwd()

        search_roots = [
            Path(FSR_MODS_DIR),
            cwd / "source" / "fsr_mods",
            script_dir.parent / "fsr_mods",
        ]

        versions = []
        seen_paths = set()

        for root in search_roots:
            if not root.exists() or not root.is_dir():
                continue

            version_dirs = [item for item in root.iterdir() if item.is_dir()]
            version_dirs.sort(key=lambda p: p.name.lower())

            for version_dir in version_dirs:
                folder_key = str(version_dir.resolve()).lower()

                if folder_key in seen_paths:
                    continue

                seen_paths.add(folder_key)

                files = {}

                try:
                    dlls = [file for file in version_dir.rglob("*.dll") if file.is_file()]
                except Exception:
                    dlls = []

                for dll in dlls:
                    classified = classify_fsr_dll_name(dll.name)

                    if classified and classified not in files:
                        files[classified] = str(dll.resolve())

                           
                                                                                          
                                                            
                if FSR_UPSCALER_DLL not in files and len(dlls) == 1:
                    only = dlls[0]
                    classified = classify_fsr_dll_name(only.name)

                    if classified in ("", FSR_UPSCALER_DLL):
                        files[FSR_UPSCALER_DLL] = str(only.resolve())

                loader_as_upscaler = False

                                                                                  
                                                                                                  
                if not files.get(FSR_UPSCALER_DLL) and files.get(FSR_LOADER_DLL):
                    files[FSR_UPSCALER_DLL] = files[FSR_LOADER_DLL]
                    loader_as_upscaler = True

                version_has_upscaler = bool(files.get(FSR_UPSCALER_DLL))
                version_has_framegen = bool(files.get(FSR_FRAMEGEN_DLL))
                version_has_fg_profile = version_has_upscaler and version_has_framegen

                versions.append({
                    "version": version_dir.name,
                    "folder": str(version_dir.resolve()),
                    "files": files,
                    "valid": version_has_upscaler,
                    "has_fg": version_has_fg_profile,
                    "loader_as_upscaler": loader_as_upscaler,
                })

        return versions

    def get_version(self, version):
        for item in self.fsr_versions:
            if item.get("version") == version:
                return item

        return None

    def mod_ready(self):
        return bool(self.fsr_versions)

    def update_fsr_versions(self):
        self.fsr_versions = self.find_fsr_versions()

        if not self.fsr_versions:
            self.fsr_version = "Missing"
        elif len(self.fsr_versions) == 1:
            self.fsr_version = self.fsr_versions[0].get("version", "Unknown")
        else:
            self.fsr_version = f"{len(self.fsr_versions)} versions"

    def update_header(self, supported_count, unsupported_count):
        self.counter_label.setText(f"Supported: {supported_count} | Unsupported: {unsupported_count}")
        self.fsr_label.setText(f"FSR: {self.fsr_version}")

        self.gpu_label.setText(self.gpu_name)
        self.gpu_label.setStyleSheet(
            f"color: {gpu_vendor_color(self.gpu_name)}; font-size: 12px; font-weight: 900; background: transparent;"
        )

    def set_cache_text(self, text):
        if hasattr(self, "cache_label"):
            self.cache_label.setText("")
            self.cache_label.hide()

    def load_scan_cache_or_initial_state(self):
        self.update_fsr_versions()

        if self.load_scan_cache():
            self.cache_loaded = True
            self.render_current_results(refresh_disk=False)
            self.schedule_deferred_disk_refresh()
            return

        self.update_header(0, 0)
        self.set_cache_text("No saved compatibility scan")
        self.show_initial_state()

    def load_scan_cache(self):
        cache_path = self.cache_path

        if not cache_path.exists():
            return False

        try:
            data = json.loads(cache_path.read_text(encoding="utf-8-sig", errors="ignore"))

            if not isinstance(data, dict):
                return False

            all_support = data.get("all_support_cache", [])
            visible_support = data.get("visible_support_cache", [])
            games = data.get("all_games_cache", [])
            manual_games = data.get("manual_fsr_games", [])
            deleted_keys = data.get("deleted_fsr_keys", [])

            if not isinstance(all_support, list) or not isinstance(visible_support, list):
                return False

            cache_root_changed = str(data.get("global_backup_root", "")).lower() != str(backup_root()).lower()
            original_count = (
                len(all_support)
                + len(visible_support)
                + (len(games) if isinstance(games, list) else 0)
                + (len(manual_games) if isinstance(manual_games, list) else 0)
            )
            self.all_games_cache = [
                game for game in (games if isinstance(games, list) else [])
                if saved_game_is_installed(game)
            ]
            self.deleted_fsr_keys = set(str(key) for key in deleted_keys if key)
            self.all_games_cache = self.filter_deleted_games(self.all_games_cache)
            self.manual_fsr_games = self.merge_games(manual_games if isinstance(manual_games, list) else [])
            self.manual_fsr_games = self.filter_deleted_games(self.manual_fsr_games)
            self.mark_manual_fsr_games()
            self.all_support_cache = [
                info for info in (normalize_support_info_paths(item) for item in all_support)
                if support_info_game_is_installed(info)
            ]
            self.all_support_cache = self.filter_deleted_support(self.all_support_cache)
            self.mark_manual_fsr_games()
            self.visible_support_cache = [
                info for info in self.all_support_cache
                if should_show_fsr_info(info)
            ]
            self.has_scanned = True

            new_count = (
                len(self.all_support_cache)
                + len(self.visible_support_cache)
                + len(self.all_games_cache)
                + len(self.manual_fsr_games)
            )
            if new_count != original_count or cache_root_changed:
                self.save_scan_cache()

            return True
        except Exception:
            return False

    def save_scan_cache(self):
        cache_path = self.cache_path

        try:
            payload = {
                "saved_at": now_text(),
                "fsr_version": self.fsr_version,
                "gpu_name": self.gpu_name,
                "scan_source": "Steam libraries + saved game list",
                "global_backup_root": str(backup_root()),
                "deleted_fsr_keys": sorted(self.deleted_fsr_keys),
                "manual_fsr_games": [cache_safe_game(game) for game in self.manual_fsr_games],
                "all_games_cache": [cache_safe_game(game) for game in self.all_games_cache],
                "all_support_cache": [cache_safe_support_info(info) for info in self.all_support_cache],
                "visible_support_cache": [cache_safe_support_info(info) for info in self.visible_support_cache],
            }

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def manual_support_override_map(self):
        overrides = {}

        for info in list(self.all_support_cache) + list(self.visible_support_cache):
            key = support_info_override_key(info)

            if key and info.get("manual_support_override"):
                overrides[key] = True

        return overrides

    def apply_manual_support_overrides(self, overrides):
        for info in self.all_support_cache:
            key = support_info_override_key(info)

            if key in overrides:
                apply_manual_support_override(info, overrides[key])

    def hidden_state_map(self):
        hidden = {}

        for info in list(self.all_support_cache) + list(self.visible_support_cache):
            key = support_info_override_key(info)

            if key and info.get("hidden"):
                hidden[key] = True

        return hidden

    def apply_hidden_states(self, hidden):
        for info in self.all_support_cache:
            key = support_info_override_key(info)

            if key in hidden:
                apply_hidden_state(info, hidden[key])

    def scan_compatibility(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.log("FSR compatibility scan is already running.")
            return

        self.busy_overlay_suppressed = False
        self.scan_btn.setEnabled(False)
        self.add_manual_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.has_scanned = True
        if self.empty_panel.isVisible():
            self.empty_label.setText("Scanning FSR compatibility...")
        self.counter_label.setText("Scanning...")
        self.log("Refreshing FSR compatibility scan...")
        self.set_busy_overlay(True, "Scanning FSR compatibility...")
        self.update_fsr_versions()
        self.mark_manual_fsr_games()

        self.scan_save_cache = True
        self.scan_worker = FsrCompatibilityScanWorker(
            self.games_from_callback(),
            load_games_from_json(),
            self.manual_fsr_games,
            True,
            self.manual_support_override_map(),
            self.hidden_state_map(),
            self.deleted_fsr_keys,
        )
        self.scan_worker.log.connect(self.log)
        self.scan_worker.scan_done.connect(self.on_compatibility_scan_done)
        self.scan_worker.finished.connect(self.on_compatibility_scan_finished)
        self.scan_worker.start()

    def on_compatibility_scan_done(self, games, all_support, visible_support):
        self.all_games_cache = self.filter_deleted_games(list(games or []))
        self.all_support_cache = self.filter_deleted_support(list(all_support or []))
        self.visible_support_cache = self.filter_deleted_support(list(visible_support or []))
        self.has_scanned = True
        self.render_current_results(refresh_disk=False)

        if self.scan_save_cache:
            self.save_scan_cache()

        self.log(
            f"FSR scan complete. Checked {len(self.all_games_cache)} game(s), "
            f"found {len(self.visible_support_cache)} FSR target(s)."
        )

    def on_compatibility_scan_finished(self):
        self.scan_btn.setEnabled(True)
        self.add_manual_btn.setEnabled(True)
        self.scan_btn.setText("Refresh")
        self.set_busy_overlay(False)
        self.busy_overlay_suppressed = False
        self.scan_worker = None

    def refresh_install_states_from_disk(self):
        self.visible_support_cache = refresh_support_install_states(self.visible_support_cache)

    def render_current_results(self, refresh_disk=False, force=False):
        if not force and not self.isVisible():
            self.pending_render = True
            self.pending_refresh_disk = self.pending_refresh_disk or bool(refresh_disk)
            return

        if refresh_disk:
            self.refresh_install_states_from_disk()

        supported_count = len([info for info in self.visible_support_cache if info.get("supported") and not info.get("hidden")])
        unsupported_count = max(0, len(self.all_games_cache) - supported_count)
        hidden_count = len([info for info in self.visible_support_cache if info.get("hidden")])

        self.update_header(supported_count, unsupported_count)
        if hidden_count:
            self.counter_label.setText(f"Supported: {supported_count} | Unsupported: {unsupported_count} | Hidden: {hidden_count}")

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        columns, card_width, poster_width, poster_height = self.grid_metrics()
        self.current_columns = columns
        self.current_card_width = card_width

        current_items = self.current_support_items()

        for display_index, (index, info) in enumerate(current_items):
            row = display_index // columns
            col = display_index % columns

            card = FsrGameCard(
                index,
                info,
                self.fsr_versions,
                card_width=card_width,
                poster_width=poster_width,
                poster_height=poster_height,
                parent=self.grid_container,
            )
            card.install_version_clicked.connect(self.install_for_visible_index)
            card.install_version_mode_clicked.connect(self.install_for_visible_index_mode)
            card.restore_clicked.connect(self.restore_for_visible_index)
            card.launch_clicked.connect(self.launch_for_visible_index)
            card.support_override_clicked.connect(self.toggle_support_override_for_visible_index)
            card.hidden_state_clicked.connect(self.toggle_hidden_state_for_visible_index)
            card.manual_targets_clicked.connect(self.open_manual_targets_for_visible_index)
            card.delete_clicked.connect(self.delete_from_fsr_for_visible_index)
            self.grid_layout.addWidget(card, row, col)

        self.grid_layout.setRowStretch((len(current_items) // columns) + 1, 1)
        self.schedule_grid_reflow()

        has_visible = bool(current_items)
        self.scroll.setVisible(has_visible)
        self.empty_panel.setVisible(not has_visible)

        if not self.has_scanned:
            self.empty_label.setText("Press Refresh to scan compatibility.")
        elif not self.all_games_cache:
            self.empty_label.setText("No games found. Scan Steam in Game Library first.")
        elif not has_visible:
            if self.fsr_view_mode == "hidden":
                self.empty_label.setText("No hidden FSR games.")
            else:
                self.empty_label.setText(
                    f"No FSR DLL targets found. Scanned {len(self.all_games_cache)} game(s)."
                )

    def current_support_items(self):
        hidden = self.fsr_view_mode == "hidden"
        return [
            (index, info)
            for index, info in enumerate(self.visible_support_cache)
            if bool(info.get("hidden", False)) == hidden
        ]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()
        self.reflow_current_grid()

    def showEvent(self, event):
        super().showEvent(event)
        self.busy_overlay_suppressed = False
        self.position_busy_overlay()
        if self.scan_worker and self.scan_worker.isRunning():
            self.set_busy_overlay(True, "Scanning FSR compatibility...")
        if self.pending_render:
            refresh_disk = self.pending_refresh_disk
            self.pending_render = False
            self.pending_refresh_disk = False
            QTimer.singleShot(
                0,
                lambda: self.render_current_results(refresh_disk=refresh_disk, force=True),
            )

    def hideEvent(self, event):
        self.busy_overlay_suppressed = True
        self.set_busy_overlay(False)
        super().hideEvent(event)

    def refresh_games(self, save_cache=False):
        self.has_scanned = True
        self.update_fsr_versions()

        overrides = self.manual_support_override_map()
        hidden = self.hidden_state_map()
        games = self.games(include_dynamic=save_cache)
        self.all_support_cache = [analyze_game_support(game) for game in games]
        self.all_support_cache = self.filter_deleted_support(self.all_support_cache)
        self.apply_manual_support_overrides(overrides)
        self.apply_hidden_states(hidden)
        self.visible_support_cache = [
            info for info in self.all_support_cache
            if should_show_fsr_info(info)
        ]
        self.visible_support_cache = refresh_support_install_states(self.visible_support_cache)

        self.render_current_results(refresh_disk=False)

        if save_cache:
            self.save_scan_cache()

    def selected_index(self):
        if not self.get_selected_index:
            return None

        try:
            return self.get_selected_index()
        except Exception:
            return None

    def install_for_visible_index(self, index, version):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        self.install_info(info, version, mode="auto")

    def install_for_visible_index_mode(self, index, version, mode):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        self.install_info(info, version, mode=mode)

    def restore_for_visible_index(self, index):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        self.restore_info(info)

    def toggle_support_override_for_visible_index(self, index):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        key = support_info_override_key(info)
        enabled = not bool(info.get("manual_support_override", False))

        apply_manual_support_override(info, enabled)

        for cached in self.all_support_cache:
            if support_info_override_key(cached) == key:
                apply_manual_support_override(cached, enabled)

        game_name = info.get("game", {}).get("name", "Unknown")
        self.log(f"{'Marked' if enabled else 'Unmarked'} {game_name} as manually supported.")
        self.render_current_results()
        self.save_scan_cache()

    def toggle_hidden_state_for_visible_index(self, index):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        key = support_info_override_key(info)
        hidden = not bool(info.get("hidden", False))

        apply_hidden_state(info, hidden)

        for cached in self.all_support_cache:
            if support_info_override_key(cached) == key:
                apply_hidden_state(cached, hidden)

        game_name = info.get("game", {}).get("name", "Unknown")
        self.log(f"{'Hidden' if hidden else 'Unhidden'} FSR game: {game_name}.")
        self.render_current_results()
        self.save_scan_cache()

    def delete_from_fsr_for_visible_index(self, index):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        key = support_info_override_key(info)
        game = info.get("game", {})
        game_name = game.get("name", "Unknown") if isinstance(game, dict) else "Unknown"

        if not key:
            return

        self.deleted_fsr_keys.add(key)
        self.visible_support_cache = self.filter_deleted_support(self.visible_support_cache)
        self.all_support_cache = self.filter_deleted_support(self.all_support_cache)
        self.all_games_cache = self.filter_deleted_games(self.all_games_cache)
        self.manual_fsr_games = self.filter_deleted_games(self.manual_fsr_games)
        self.render_current_results(refresh_disk=False, force=True)
        self.save_scan_cache()
        self.log(f"Deleted from FSR tab only: {game_name}.")

    def open_manual_targets_for_visible_index(self, index):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        game = dict(info.get("game", {}) or {})
        game_path = os.path.abspath(str(info.get("game_path", "") or game.get("path", "") or ""))
        game_name = game.get("name", "Unknown")

        if not game_path or not os.path.isdir(game_path):
            QMessageBox.warning(self, "FSR Mods", f"Game path not found: {game_path}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Manual FSR DLL Paths")
        dialog.setObjectName("FsrManualDialog")
        dialog.setModal(True)
        dialog.setMinimumWidth(720)
        dialog.setStyleSheet(FSR_PAGE_STYLE)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Manual FSR DLL Paths", dialog)
        title.setObjectName("FsrManualTitle")

        hint = QLabel(f"{game_name}\nPick the target DLL files inside the game folder. Empty rows will use auto-detection.", dialog)
        hint.setObjectName("FsrManualHint")
        hint.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(hint)

        existing_targets = {}
        for source in (game.get("fsr_manual_targets", {}), info.get("manual_fsr_targets", {}), info.get("targets", {})):
            if isinstance(source, dict):
                existing_targets.update({key: value for key, value in source.items() if value})

        inputs = {}
        labels = {
            FSR_UPSCALER_DLL: "Upscaler target",
            FSR_LOADER_DLL: "Loader target",
            FSR_FRAMEGEN_DLL: "Frame generation target",
        }

        def browse_for(canonical):
            current = inputs[canonical].text().strip()
            start_dir = os.path.dirname(current) if current else game_path
            path, _ = QFileDialog.getOpenFileName(
                dialog,
                f"Choose {labels[canonical]}",
                start_dir,
                "DLL files (*.dll)",
            )
            if not path:
                return
            if not path_inside(game_path, path):
                QMessageBox.warning(dialog, "FSR Mods", "Choose a DLL inside this game's folder.")
                return
            inputs[canonical].setText(os.path.abspath(path))

        for canonical in FSR_MANAGED_DLLS:
            label = QLabel(labels[canonical], dialog)
            label.setObjectName("FsrManualFieldLabel")

            row = QHBoxLayout()
            row.setSpacing(8)

            field = QLineEdit(dialog)
            field.setObjectName("FsrPathInput")
            field.setText(str(existing_targets.get(canonical, "") or ""))
            field.setPlaceholderText(canonical)
            inputs[canonical] = field

            browse_btn = QPushButton("Browse", dialog)
            browse_btn.setObjectName("FsrManualGhost")
            browse_btn.clicked.connect(lambda checked=False, key=canonical: browse_for(key))

            clear_btn = QPushButton("Clear", dialog)
            clear_btn.setObjectName("FsrManualGhost")
            clear_btn.clicked.connect(lambda checked=False, key=canonical: inputs[key].clear())

            row.addWidget(field, stretch=1)
            row.addWidget(browse_btn)
            row.addWidget(clear_btn)
            root.addWidget(label)
            root.addLayout(row)

        actions = QHBoxLayout()
        cancel_btn = QPushButton("Cancel", dialog)
        cancel_btn.setObjectName("FsrManualGhost")
        save_btn = QPushButton("Save Paths", dialog)
        save_btn.setObjectName("FsrManualPrimary")
        cancel_btn.clicked.connect(dialog.reject)
        save_btn.clicked.connect(dialog.accept)
        actions.addWidget(cancel_btn)
        actions.addStretch()
        actions.addWidget(save_btn)

        root.addLayout(actions)

        if dialog.exec_() != QDialog.Accepted:
            return

        manual_targets = {}
        for canonical, field in inputs.items():
            path = field.text().strip().strip('"')
            if not path:
                continue
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                QMessageBox.warning(self, "FSR Mods", f"Target file not found:\n{path}")
                return
            if not path_inside(game_path, path):
                QMessageBox.warning(self, "FSR Mods", f"Target must be inside the game folder:\n{path}")
                return
            manual_targets[canonical] = path

        game["path"] = game_path
        game["fsr_manual_added"] = True
        game["fsr_manual_targets"] = manual_targets
        self.upsert_manual_fsr_game(game)

        refreshed = analyze_game_support(game)
        if info.get("manual_support_override"):
            apply_manual_support_override(refreshed, True)
        if info.get("hidden"):
            apply_hidden_state(refreshed, True)

        self.visible_support_cache[index] = refreshed
        self.all_support_cache = self.replace_cached_support(self.all_support_cache, refreshed)
        self.all_games_cache = self.replace_cached_game(self.all_games_cache, game)
        self.save_scan_cache()
        self.render_current_results(refresh_disk=False, force=True)
        self.log(f"Manual FSR target paths saved: {game_name}")

    def launch_for_visible_index(self, index):
        if index < 0 or index >= len(self.visible_support_cache):
            return

        info = self.visible_support_cache[index]
        game = info.get("game", {})
        game_path = info.get("game_path", "")
        game_name = game.get("name", "Unknown")

        if not game_path or not os.path.exists(game_path):
            QMessageBox.warning(self, "FSR Mods", f"Game path not found: {game_path}")
            return

                                                                    
        launch_btn = None
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item:
                widget = item.widget()
                if isinstance(widget, FsrGameCard) and widget.index == index:
                    launch_btn = widget.launch_btn
                    break

        if launch_btn:
            launch_btn.setEnabled(False)
            launch_btn.setText("Launching...")

                                                  
        exe_files = []
        try:
            for item in os.listdir(game_path):
                item_path = os.path.join(game_path, item)
                if os.path.isfile(item_path) and item.lower().endswith(".exe"):
                    exe_files.append(item)
        except Exception as e:
            QMessageBox.warning(self, "FSR Mods", f"Could not read game directory: {e}")
            if launch_btn:
                launch_btn.setEnabled(True)
                launch_btn.setText("Launch Game")
            return

        if not exe_files:
            QMessageBox.warning(self, "FSR Mods", f"No executable found in {game_name}")
            if launch_btn:
                launch_btn.setEnabled(True)
                launch_btn.setText("Launch Game")
            return

        exe_to_launch = None

                                                     
                                       
        priority_patterns = [
            game_name.replace(" ", "").lower(),
            "game.exe",
            exe_files[0]                         
        ]

        exe_lower = [exe.lower() for exe in exe_files]

        for pattern in priority_patterns:
            for i, exe_lower_name in enumerate(exe_lower):
                if pattern in exe_lower_name or exe_lower_name in pattern:
                    exe_to_launch = exe_files[i]
                    break
            if exe_to_launch:
                break

        if not exe_to_launch:
            exe_to_launch = exe_files[0]

        exe_path = os.path.join(game_path, exe_to_launch)

        try:
            launch_flags = 0
            startup_info = None
            if os.name == "nt":
                launch_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if hasattr(subprocess, "STARTUPINFO"):
                    startup_info = subprocess.STARTUPINFO()
                    startup_info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
                    startup_info.wShowWindow = 0

            subprocess.Popen(
                exe_path,
                cwd=game_path,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=launch_flags,
                startupinfo=startup_info,
            )
            self.log(f"Launched {game_name}: {exe_to_launch}")
            
                                                                               
            if launch_btn:
                QTimer.singleShot(2000, lambda: self._reset_launch_button(launch_btn))
        except Exception as e:
            QMessageBox.critical(self, "FSR Mods", f"Failed to launch {game_name}:\n\n{e}")
            if launch_btn:
                launch_btn.setEnabled(True)
                launch_btn.setText("Launch Game")

    def _reset_launch_button(self, launch_btn):
        """Re-enable launch button after game startup"""
        if launch_btn:
            launch_btn.setEnabled(True)
            launch_btn.setText("Launch Game")

    def install_info(self, info, version=None, mode="auto"):
        game = info.get("game", {})
        game_name = game.get("name", "Unknown")
        game_path = info.get("game_path", "")
        targets = info.get("targets", {}) or {}

        self.update_fsr_versions()

        if not self.fsr_versions:
            fsr_example_root = Path(FSR_MODS_DIR) / "4.0.3c"
            QMessageBox.warning(
                self,
                "FSR Mods",
                (
                    "Missing FSR files.\n\n"
                    "Use this structure:\n\n"
                    f"{fsr_example_root}\\{FSR_UPSCALER_DLL}\n"
                    f"{fsr_example_root}\\{FSR_LOADER_DLL}\n"
                    f"{fsr_example_root}\\{FSR_FRAMEGEN_DLL}"
                ),
            )
            return

        if not version:
            version = self.fsr_versions[0].get("version", "Unknown")

        version_info = self.get_version(version)

        if not version_info:
            QMessageBox.warning(self, "FSR Mods", f"FSR {version} files are missing.")
            return

        if not version_info.get("valid", False):
            QMessageBox.warning(
                self,
                "FSR Mods",
                f"FSR {version} folder has no usable FSR DLL."
            )
            return

        if mode == "fg" and not version_info.get("has_fg", False):
            QMessageBox.warning(
                self,
                "FSR Mods",
                "This FSR version folder does not contain both the upscaler and frame generation DLL."
            )
            return

        mod_files = version_info.get("files", {}) or {}

        if not targets:
            target = info.get("target", "")
            if target:
                targets = {FSR_UPSCALER_DLL: target}
                info["targets"] = targets

        if not (targets.get(FSR_UPSCALER_DLL) or targets.get(FSR_LOADER_DLL)):
            QMessageBox.warning(self, "FSR Mods", f"{game_name} FSR DLL is missing. Run Refresh again.")
            return

        backups = info.get("backups", {}) or {}
        installed = any(
            is_target_currently_modded(target, backups.get(canonical, ""))
            for canonical, target in targets.items()
        )
        version_info = fsr_game_version_info(targets, backups, installed)
        info.update(version_info)

        if not version_info.get("fsr_game_dll_version_supported", False) and not info.get("manual_support_override", False):
            QMessageBox.warning(self, "FSR Mods", fsr_version_block_message(info, game_name))
            return

        replaced = []
        skipped = []
        game_has_upscaler_target = bool(targets.get(FSR_UPSCALER_DLL))

        try:
            if mode == "fg" and not info.get("framegen_supported", False):
                QMessageBox.warning(
                    self,
                    "FSR Mods",
                    "This game does not support frame generation replacement.\n\nOnly the normal FSR option is available."
                )
                return

            for canonical in FSR_MANAGED_DLLS:
                target = targets.get(canonical)
                mod_file = mod_files.get(canonical)

                if canonical == FSR_LOADER_DLL and game_has_upscaler_target:
                    skipped.append(canonical)
                    continue

                if canonical == FSR_LOADER_DLL and not mod_file:
                    mod_file = mod_files.get(FSR_UPSCALER_DLL)

                if canonical == FSR_UPSCALER_DLL and not mod_file:
                    mod_file = mod_files.get(FSR_LOADER_DLL)

                if mode == "fsr" and canonical not in (FSR_UPSCALER_DLL, FSR_LOADER_DLL):
                    continue

                if mode == "fg" and canonical == FSR_FRAMEGEN_DLL and not info.get("framegen_supported", False):
                    continue

                                                          
                if not target:
                    continue

                                                                       
                if not mod_file or not os.path.exists(mod_file):
                    skipped.append(canonical)
                    continue

                if not os.path.exists(target):
                    skipped.append(canonical)
                    continue

                if same_file_path(mod_file, target):
                    skipped.append(canonical)
                    continue

                backup = backups.get(canonical) or backup_path_for_target(game, target, game_path)
                os.makedirs(os.path.dirname(backup), exist_ok=True)

                                                                         
                if not os.path.exists(backup):
                    shutil.copy2(target, backup)

                shutil.copy2(mod_file, target)
                backups[canonical] = backup
                replaced.append(canonical)

            if not replaced:
                QMessageBox.warning(self, "FSR Mods", "Nothing was installed. No matching files were available.")
                return

            info["backups"] = backups
            self.log(f"Installed FSR {version} into {game_name}: {', '.join(replaced)}")

            self.render_current_results()
            self.save_scan_cache()

            skipped_framegen = FSR_FRAMEGEN_DLL in skipped and FSR_FRAMEGEN_DLL in targets
            if skipped_framegen:
                QMessageBox.information(
                    self,
                    "FSR Mods",
                    "Upscaler installed, but frame generation file was skipped because this FSR version folder does not include it.",
                )

        except Exception as e:
            QMessageBox.critical(self, "FSR Mods", f"Install failed:\n\n{e}")

    def restore_info(self, info):
        game = info.get("game", {})
        game_name = game.get("name", "Unknown")
        targets = info.get("targets", {}) or {}
        backups = info.get("backups", {}) or {}

        if not targets:
            target = info.get("target", "")
            backup = info.get("backup", "")
            if target:
                targets = {FSR_UPSCALER_DLL: target}
            if backup:
                backups = {FSR_UPSCALER_DLL: backup}

        restored = []

        try:
            for canonical, target in targets.items():
                backup = backups.get(canonical)

                if not target or not backup:
                    continue

                if not os.path.exists(target) or not os.path.exists(backup):
                    continue

                shutil.copy2(backup, target)
                restored.append(canonical)

            if not restored:
                QMessageBox.warning(self, "FSR Mods", "No backup found. Cannot safely restore.")
                return

            self.log(f"Restored original FSR files for {game_name}: {', '.join(restored)}")

            self.render_current_results()
            self.save_scan_cache()

        except Exception as e:
            QMessageBox.critical(self, "FSR Mods", f"Restore failed:\n\n{e}")

                                                           
    def scan_selected_game(self):
        self.scan_compatibility()

    def install_mod(self):
        index = self.selected_index()

        if index is None:
            QMessageBox.warning(self, "FSR Mods", "Select a game in Game Library first.")
            return

        games = self.games()

        if index < 0 or index >= len(games):
            QMessageBox.warning(self, "FSR Mods", "Invalid selected game.")
            return

        info = analyze_game_support(games[index])
        key = support_info_override_key(info)
        overrides = self.manual_support_override_map()

        if key in overrides:
            apply_manual_support_override(info, overrides[key])

        if not info.get("supported"):
            if info.get("target"):
                QMessageBox.warning(
                    self,
                    "FSR Mods",
                    fsr_version_block_message(info, info.get("game", {}).get("name", "Selected game")),
                )
            else:
                QMessageBox.warning(self, "FSR Mods", "Selected game is not supported.")
            return

        version = self.fsr_versions[0].get("version", "Unknown") if self.fsr_versions else None
        self.install_info(info, version, mode="auto")

    def restore_original(self):
        index = self.selected_index()

        if index is None:
            QMessageBox.warning(self, "FSR Mods", "Select a game in Game Library first.")
            return

        games = self.games()

        if index < 0 or index >= len(games):
            QMessageBox.warning(self, "FSR Mods", "Invalid selected game.")
            return

        info = analyze_game_support(games[index])
        key = support_info_override_key(info)
        overrides = self.manual_support_override_map()

        if key in overrides:
            apply_manual_support_override(info, overrides[key])

        if not info.get("supported"):
            QMessageBox.warning(self, "FSR Mods", "Selected game is not supported.")
            return

        self.restore_info(info)
