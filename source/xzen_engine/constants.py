import os
import sys
from pathlib import Path

from .deps import user_data_path

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parents[2]

SOURCE_DIR = APP_ROOT / "source"
if not SOURCE_DIR.exists() and getattr(sys, "frozen", False):
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        fallback_source = Path(meipass) / "source"
        if fallback_source.exists():
            SOURCE_DIR = fallback_source

if os.name == "nt":
    fallback_settings_root = Path(
        os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    ) / "Xzen" / "XzenGameCompressor"
else:
    fallback_settings_root = Path(
        os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    ) / "XzenGameCompressor"

PLATFORM_USER_SETTINGS_DIR = user_data_path(
    app_name="XzenGameCompressor",
    app_author="Xzen",
    fallback_path=fallback_settings_root,
) / "user_settings"

                                                                              
                                                      
USER_SETTINGS_DIR = PLATFORM_USER_SETTINGS_DIR
FSR_MODS_DIR = SOURCE_DIR / "fsr_mods"
FSR_BACKUP_DIR = USER_SETTINGS_DIR / "fsr_backups"
ASSETS_DIR = SOURCE_DIR / "assets"
APP_ICON_FILE = ASSETS_DIR / "xzen.ico"

APP_NAME = "Xzen Game Compressor - HIGANBANA"
DATA_FILE = str(USER_SETTINGS_DIR / "xzen_games.json")
SETTINGS_FILE = str(USER_SETTINGS_DIR / "xzen_settings.json")
FSR_SCAN_CACHE_FILE = str(USER_SETTINGS_DIR / "xzen_fsr_scan_cache.json")
POSTER_CACHE_DIR = str(USER_SETTINGS_DIR / "poster_cache")

STEAMGRIDDB_API_KEY = "2ea17ac465e731acac19e07c01687f98"
DASHBOARD_ACCENT = "#B38AFF"

POSTER_DOWNLOAD_WORKERS = 3

MAX_SPEED_CHUNK_SIZE = 24
MAX_SPEED_CHUNK_BYTES = 512 * 1024 * 1024

HUGE_FILE_SINGLE_CHUNK_BYTES = 1024 * 1024 * 1024
HUGE_FILE_SEQUENTIAL_BYTES = 4 * 1024 * 1024 * 1024
HUGE_FILE_WARNING_BYTES = 10 * 1024 * 1024 * 1024

DEFAULT_COMPRESSION_ALGORITHM = "XPRESS8K"
DEFAULT_LAUNCH_AS_ADMIN = False
DEFAULT_WORKER_MODE = "auto"
DEFAULT_WORKER_COUNT = 4

AUTO_PAUSE_WHEN_GAME_RUNNING = True
GAME_DETECT_CHECK_SECONDS = 2.0
IDLE_RESUME_SECONDS = 45
FULLSCREEN_COVERAGE_RATIO = 0.88

COMPRESSION_ALGORITHMS = [
    ("XPRESS4K", "X4 - fastest, lowest savings", "xpress4k"),
    ("XPRESS8K", "X8 - fast, light savings", "xpress8k"),
    ("XPRESS16K", "X16 - balanced", "xpress16k"),
    ("LZX", "LZX - strongest, slowest", "lzx"),
]

VALID_WORKER_MODES = {"auto", "1", "2", "4", "custom"}
BACKGROUND_SELECTION_MODES = {"all", "custom"}

BLOCKED_PATHS = [
    os.environ.get("WINDIR", r"C:\Windows"),
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

EXCLUDED_STEAM_APPIDS = {"228980"}
EXCLUDED_STEAM_NAMES = {"steamworks common redistributables"}

NON_GAME_EXE_NAMES = {
    "explorer.exe", "steam.exe", "steamwebhelper.exe", "discord.exe",
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "operagx.exe",
    "spotify.exe", "code.exe", "pycharm64.exe", "devenv.exe", "cmd.exe",
    "powershell.exe", "windowsterminal.exe", "taskmgr.exe", "xzen game compressor.exe",
}

KNOWN_GAME_EXE_NAMES = {
    "eldenring.exe", "start_protected_game.exe", "cs2.exe", "csgo.exe",
    "valorant-win64-shipping.exe", "valorant.exe", "fortniteclient-win64-shipping.exe",
    "gta5.exe", "gtaiv.exe", "rdr2.exe", "witcher3.exe", "cyberpunk2077.exe",
    "minecraft.exe", "javaw.exe", "robloxplayerbeta.exe", "league of legends.exe",
    "leagueclient.exe", "overwatch.exe", "r5apex.exe", "destiny2.exe",
    "warframe.x64.exe", "dota2.exe", "deadbydaylight-win64-shipping.exe",
}

MANUAL_LIBRARY_FOLDER_NAMES = {
    "battle.net",
    "common",
    "ea games",
    "epic games",
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
    "steamapps",
    "ubisoft game launcher",
    "xboxgames",
}

MANUAL_LIBRARY_SCAN_SUBDIRS = (
    "steamapps\\common",
    "common",
    "games",
    "Games",
)

MANUAL_CONTENT_FOLDER_NAME = "Content"

def compression_algorithm_keys():
    return [key for key, _, _ in COMPRESSION_ALGORITHMS]


def compression_algorithm_label(key):
    for option_key, label, _ in COMPRESSION_ALGORITHMS:
        if option_key == key:
            return label
    return compression_algorithm_label(DEFAULT_COMPRESSION_ALGORITHM)


def compression_algorithm_compact_value(key):
    for option_key, _, compact_value in COMPRESSION_ALGORITHMS:
        if option_key == key:
            return compact_value
    return compression_algorithm_compact_value(DEFAULT_COMPRESSION_ALGORITHM)


def normalized_worker_mode(value):
    value = str(value or DEFAULT_WORKER_MODE)
    if value in VALID_WORKER_MODES:
        return value
    return DEFAULT_WORKER_MODE


def normalized_worker_count(value):
    cpu_threads = max(1, os.cpu_count() or 1)
    try:
        value = int(value or DEFAULT_WORKER_COUNT)
    except Exception:
        value = DEFAULT_WORKER_COUNT
    return max(1, min(value, cpu_threads))


def estimated_cpu_core_count(cpu_threads=None):
    cpu_threads = max(1, int(cpu_threads or os.cpu_count() or 1))
    if cpu_threads >= 4:
        return max(1, cpu_threads // 2)
    return cpu_threads


def automatic_worker_count(cpu_threads=None):
    cpu_cores = estimated_cpu_core_count(cpu_threads)
    return max(1, min(12, cpu_cores // 2))


def resolve_worker_count(worker_mode, worker_count):
    cpu_threads = max(1, os.cpu_count() or 1)
    worker_mode = normalized_worker_mode(worker_mode)
    worker_count = normalized_worker_count(worker_count)

    if worker_mode == "auto":
        return automatic_worker_count(cpu_threads)
    if worker_mode == "custom":
        return max(1, min(cpu_threads, worker_count))
    if worker_mode in {"1", "2", "4"}:
        return max(1, min(cpu_threads, int(worker_mode)))
    return automatic_worker_count(cpu_threads)

