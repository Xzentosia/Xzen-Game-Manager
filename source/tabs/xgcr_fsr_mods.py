import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from source.xzen_engine.constants import FSR_BACKUP_DIR, FSR_MODS_DIR, FSR_SCAN_CACHE_FILE
from source.xzen_engine.posters import sanitize_png_file
from source.xzen_engine.system import find_game_executable
from source.xzen_engine.theme import themed_qss
from source.logs import log_debug, log_error, log_exception, log_success, log_warning
from source.tabs.game_library import SmoothScrollArea


GLOBAL_BACKUP_ROOT = Path(FSR_BACKUP_DIR)

OPTISCALER_DLL = "OptiScaler.dll"
OPTISCALER_INI = "OptiScaler.ini"
OPTISCALER_SOURCE_FOLDER = "optiscaler"
OPTISCALER_SOURCE_METADATA = "xzen_optiscaler_source.json"
OPTISCALER_CACHE_VERSION = 3
UPSCALER_SCAN_SIGNATURE_VERSION = 2
OPTISCALER_RELEASE_API = "https://api.github.com/repos/optiscaler/OptiScaler/releases/latest"
OPTIPATCHER_RELEASE_API = "https://api.github.com/repos/optiscaler/OptiPatcher/releases/latest"
_OPTISCALER_DLL_HASH_CACHE = {"path": "", "mtime": 0.0, "hash": ""}

OPTISCALER_WRAPPERS = [
    "dxgi.dll",
    "winmm.dll",
    "d3d12.dll",
    "dbghelp.dll",
    "version.dll",
    "wininet.dll",
    "winhttp.dll",
    "OptiScaler.asi",
]

UPSCALER_TARGETS = {
    "nvngx_dlss.dll": ("NVIDIA DLSS", "DLSS SR"),
    "nvngx_dlssg.dll": ("NVIDIA DLSS", "DLSS FG"),
    "nvngx_dlssd.dll": ("NVIDIA DLSS", "DLSS RR"),
    "sl.dlss.dll": ("NVIDIA DLSS", "Streamline DLSS"),
    "sl.dlss_g.dll": ("NVIDIA DLSS", "Streamline FG"),
    "amd_fidelityfx_dx12.dll": ("AMD FSR", "FSR Loader"),
    "amd_fidelityfx_upscaler_dx12.dll": ("AMD FSR", "FSR SR"),
    "amd_fidelityfx_framegeneration_dx12.dll": ("AMD FSR", "FSR FG"),
    "amd_fidelityfx_vk.dll": ("AMD FSR", "FSR Vulkan"),
    "libxess.dll": ("Intel XeSS", "XeSS DX12"),
    "libxess_dx11.dll": ("Intel XeSS", "XeSS DX11"),
    "libxess_fg.dll": ("Intel XeSS", "XeFG"),
    "libxell.dll": ("Intel XeSS", "XeLL"),
}

COMMON_GAME_BIN_DIRS = (
    ("Binaries", "Win64"),
    ("Binaries", "WinGDK"),
    ("bin", "x64"),
    ("bin", "x64_dx12"),
    ("Retail",),
    ("binaries",),
)

SKIPPED_SCAN_DIRS = {
    "__pycache__",
    ".git",
    "content",
    "paks",
    "movies",
    "screenshots",
    "saved",
    "shadercache",
    "webcache",
}

ANTI_CHEAT_MARKERS = {
    "easyanticheat_eos.exe": "Easy Anti-Cheat",
    "easyanticheat_setup.exe": "Easy Anti-Cheat",
    "start_protected_game.exe": "Easy Anti-Cheat",
    "beservice.exe": "BattlEye",
    "beservice_x64.exe": "BattlEye",
    "beclient.dll": "BattlEye",
    "beclient_x64.dll": "BattlEye",
    "vgk.sys": "Riot Vanguard",
    "vgc.exe": "Riot Vanguard",
    "gameguard": "GameGuard",
}

FSR_PAGE_STYLE = themed_qss("""
QWidget {
    background: #0B0A10;
    color: #f5f2ff;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}
QLabel {
    background: transparent;
    border: none;
}
QScrollArea, QScrollArea QWidget, QAbstractScrollArea {
    background: transparent;
}
QLabel#PageTitle {
    color: #ffffff;
    font-size: 24px;
    font-weight: 800;
}
QLabel#Muted, QLabel#PathLabel, QLabel#HintLabel {
    color: #9b96b9;
}
QLabel#SectionTitle {
    color: #cbc2ff;
    font-size: 13px;
    font-weight: 800;
}
QFrame#Panel, QFrame#GameCard, QFrame#StatusPanel {
    background: #141426;
    border: 1px solid #2a2940;
    border-radius: 8px;
}
QFrame#InfoPanel {
    background: #181a30;
    border: 1px solid #4778c7;
    border-radius: 7px;
}
QFrame#PosterFrame {
    background: #10101d;
    border: 1px solid #292840;
    border-radius: 8px;
}
QLabel#PosterLabel {
    background: transparent;
    color: #716d8b;
    border: none;
    border-radius: 8px;
    padding: 0;
}
QLabel#Pill {
    color: #dcd6ff;
    background: transparent;
    border: none;
    padding: 2px 8px 2px 0;
    font-weight: 700;
}
QLabel#StatusGood {
    color: #80d44f;
    font-weight: 900;
}
QLabel#StatusBad {
    color: #ff7777;
    font-weight: 900;
}
QPushButton {
    background: #24213b;
    color: #f6f2ff;
    border: 1px solid #3d3862;
    border-radius: 7px;
    padding: 8px 12px;
    font-weight: 800;
}
QPushButton:hover {
    background: #332c55;
    border-color: #7d61ff;
}
QPushButton:pressed {
    background: #5c45b8;
}
QPushButton#PrimaryButton {
    background: #7e61ff;
    border-color: #9c86ff;
}
QPushButton#PrimaryButton:hover {
    background: #9278ff;
}
QPushButton#DangerButton {
    color: #ffb7b7;
    background: #2a181d;
    border-color: #8e3f46;
}
QPushButton#GreenButton {
    color: #a6f7c1;
    background: #13281f;
    border-color: #278756;
}
QPushButton#TinyButton {
    padding: 5px 8px;
    min-width: 0;
}
QComboBox, QLineEdit {
    background: #17172a;
    color: #ffffff;
    border: 1px solid #302e4b;
    border-radius: 7px;
    padding: 7px 10px;
}
QComboBox:hover, QLineEdit:hover {
    border-color: #6c5bd1;
}
QComboBox::drop-down {
    width: 26px;
    border: none;
}
QListView#ComboDropdown {
    background: #17172a;
    color: #f6f2ff;
    border: 1px solid #7e61ff;
    border-radius: 7px;
    padding: 3px;
    outline: none;
}
QListView#ComboDropdown::item {
    min-height: 24px;
    padding: 4px 8px;
    margin: 1px 0;
    color: #f6f2ff;
    background: transparent;
    border: none;
    border-radius: 5px;
}
QListView#ComboDropdown::item:hover,
QListView#ComboDropdown::item:selected {
    background: #2b2448;
    color: #ffffff;
}
QListView#ComboDropdown QScrollBar:vertical {
    background: #0a0a14;
    width: 9px;
    margin: 3px 0 3px 0;
    border: none;
    border-radius: 4px;
}
QListView#ComboDropdown QScrollBar::handle:vertical {
    background: #7e61ff;
    min-height: 24px;
    border-radius: 4px;
}
QListView#ComboDropdown QScrollBar::add-line:vertical,
QListView#ComboDropdown QScrollBar::sub-line:vertical,
QListView#ComboDropdown QScrollBar::add-page:vertical,
QListView#ComboDropdown QScrollBar::sub-page:vertical {
    height: 0;
    background: transparent;
    border: none;
}
QCheckBox {
    spacing: 8px;
    color: #dcd7f5;
    background: transparent;
    border: none;
}
QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid #4a456d;
    background: #121220;
}
QCheckBox::indicator:checked {
    background: #7e61ff;
    border-color: #a28fff;
}
QCheckBox:hover {
    background: transparent;
}
""")

PURPLE_SCROLLBAR_STYLE = themed_qss("""
QScrollBar:vertical {
    background: #0a0a14;
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
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    height: 0;
    background: transparent;
    border: none;
}
""")


def safe_text(value):
    return str(value or "").strip()


def cache_key_for_game(game):
    path = os.path.abspath(safe_text(game.get("path") or game.get("install_dir") or ""))
    exe = os.path.abspath(safe_text(game.get("exe_path") or ""))
    appid = safe_text(game.get("appid"))
    name = safe_text(game.get("name"))
    raw = "|".join([appid, name.lower(), path.lower(), exe.lower()])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def game_scan_signature(game):
    root = game_root(game)
    exe = safe_text(game.get("exe_path"))
    root_text = str(root or "")
    return {
        "version": UPSCALER_SCAN_SIGNATURE_VERSION,
        "root": root_text,
        "exe": os.path.abspath(exe) if exe else "",
        "root_mtime": safe_mtime(root_text) if root_text else 0.0,
        "exe_mtime": safe_mtime(exe) if exe else 0.0,
        "manual": bool(game.get("upscaler_manual")),
    }


def load_cache():
    try:
        with open(FSR_SCAN_CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("version", OPTISCALER_CACHE_VERSION)
            data.setdefault("manual_entries", [])
            data.setdefault("install_records", {})
            return data
    except Exception as exc:
        log_warning("upscaler", "load_cache", "Could not read FSR/upscaler scan cache.", path=FSR_SCAN_CACHE_FILE, error=str(exc))
    return {
        "version": OPTISCALER_CACHE_VERSION,
        "manual_entries": [],
        "install_records": {},
    }


def load_optiscaler_source_metadata(source_dir=None):
    source_dir = Path(source_dir or find_optiscaler_source())
    meta_path = source_dir / OPTISCALER_SOURCE_METADATA
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log_warning("upscaler", "load_optiscaler_source_metadata", "Could not read OptiScaler source metadata.", path=meta_path, error=str(exc))
        return {}


def save_cache(data):
    try:
        Path(FSR_SCAN_CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(FSR_SCAN_CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except Exception as exc:
        log_exception("upscaler", "save_cache", exc, "Could not save FSR/upscaler scan cache.", path=FSR_SCAN_CACHE_FILE)


def find_optiscaler_source():
    here = Path(__file__).resolve()
    return here.parents[1] / OPTISCALER_SOURCE_FOLDER


def find_fsr_mods_source():
    candidates = [
        Path(FSR_MODS_DIR),
        Path(__file__).resolve().parents[3] / "source" / "fsr_mods",
        Path.cwd() / "source" / "fsr_mods",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def available_fsr4_int8_versions():
    root = find_fsr_mods_source()
    versions = []
    try:
        for folder in root.iterdir():
            dll = fsr4_int8_source_file(folder.name)
            if folder.is_dir() and dll.exists():
                versions.append(folder.name)
    except Exception as exc:
        log_warning("upscaler", "available_fsr4_int8_versions", "Could not scan FSR4 INT8 versions.", root=root, error=str(exc))
    return sorted(versions, key=lambda value: [int(part) if part.isdigit() else part for part in value.replace("-", ".").split(".")])


def fsr4_option_label(version):
    version = safe_text(version)
    if version == "4.0.2c":
        return f"{version}   LATEST"
    return version


def fsr4_option_value(label):
    return safe_text(label).replace("LATEST", "").strip()


def fsr4_int8_source_file(version):
    folder = find_fsr_mods_source() / safe_text(version)
    preferred = folder / "amd_fidelityfx_upscaler_dx12.dll"
    if preferred.exists():
        return preferred
    return folder / "amd_fidelityfx_dx12.dll"


def file_sha256(path):
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return ""


def optiscaler_dll_hash():
    path = find_optiscaler_source() / OPTISCALER_DLL
    path_text = str(path)
    mtime = safe_mtime(path)
    if (
        _OPTISCALER_DLL_HASH_CACHE.get("path") == path_text
        and _OPTISCALER_DLL_HASH_CACHE.get("mtime") == mtime
    ):
        return _OPTISCALER_DLL_HASH_CACHE.get("hash", "")
    digest = file_sha256(path)
    _OPTISCALER_DLL_HASH_CACHE.update({"path": path_text, "mtime": mtime, "hash": digest})
    return digest


def file_version(path):
    if os.name != "nt" or not os.path.exists(path):
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer)
        value = ctypes.c_void_p()
        length = wintypes.UINT()
        ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(length))
        fixed = ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32))
        ms = fixed[2]
        ls = fixed[3]
        return f"{ms >> 16}.{ms & 0xffff}.{ls >> 16}.{ls & 0xffff}"
    except Exception:
        return ""


def version_original_filename(path):
    if os.name != "nt" or not os.path.exists(path):
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer)

        trans = ctypes.c_void_p()
        trans_len = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buffer, "\\VarFileInfo\\Translation", ctypes.byref(trans), ctypes.byref(trans_len)
        ):
            return ""
        if trans_len.value < 4:
            return ""
        pair = ctypes.cast(trans, ctypes.POINTER(ctypes.c_ushort * 2)).contents
        lang, codepage = pair[0], pair[1]
        query = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\OriginalFilename"
        value = ctypes.c_wchar_p()
        value_len = wintypes.UINT()
        if ctypes.windll.version.VerQueryValueW(
            buffer, query, ctypes.byref(value), ctypes.byref(value_len)
        ):
            return value.value or ""
    except Exception:
        return ""
    return ""


def set_ini_value(text, key, value):
    lines = text.splitlines()
    prefix = f"{key}="
    replaced = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith(prefix.lower()):
            lines[idx] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def apply_ini_settings(ini_path, settings):
    try:
        text = Path(ini_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    for key, value in settings.items():
        text = set_ini_value(text, key, value)
    Path(ini_path).write_text(text, encoding="utf-8")


def latest_optipatcher_release_asset():
    data = fetch_github_release(OPTIPATCHER_RELEASE_API)
    tag = safe_text(data.get("tag_name") or data.get("name") or "latest")
    for asset in data.get("assets", []):
        name = safe_text(asset.get("name"))
        url = safe_text(asset.get("browser_download_url"))
        if name.lower().endswith(".asi") and "optipatcher" in name.lower() and url:
            return tag, name, url
    raise RuntimeError("Latest OptiPatcher release does not include an OptiPatcher .asi asset.")


def fetch_github_release(api_url):
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "XzenGameManager",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def latest_optiscaler_release_asset():
    data = fetch_github_release(OPTISCALER_RELEASE_API)
    tag = safe_text(data.get("tag_name") or data.get("name") or "latest")
    assets = []
    for asset in data.get("assets", []):
        name = safe_text(asset.get("name"))
        url = safe_text(asset.get("browser_download_url"))
        low = name.lower()
        if not url:
            continue
        if not (low.endswith(".zip") or low.endswith(".7z")):
            continue
        if any(token in low for token in ("source", "pdb", "symbols", "linux")):
            continue
        assets.append((name, url))
    if not assets:
        raise RuntimeError("Latest OptiScaler release does not include a Windows archive asset.")
    assets.sort(key=lambda item: (0 if item[0].lower().endswith(".zip") else 1, len(item[0])))
    name, url = assets[0]
    return tag, name, url


def download_file(url, dest):
    log_debug("upscaler", "download_start", "Downloading file.", url=url, dest=dest)
    request = urllib.request.Request(url, headers={"User-Agent": "XzenGameManager"})
    with urllib.request.urlopen(request, timeout=90) as response, open(dest, "wb") as handle:
        shutil.copyfileobj(response, handle)
    log_success("upscaler", "download_complete", "Downloaded file.", url=url, dest=dest, bytes=Path(dest).stat().st_size if Path(dest).exists() else 0)


def safe_extract_zip(zip_path, dest_dir):
    dest_dir = Path(dest_dir).resolve()
    log_debug("upscaler", "extract_zip_start", "Extracting ZIP archive.", archive=zip_path, dest=dest_dir)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (dest_dir / member.filename).resolve()
            if not str(target).lower().startswith(str(dest_dir).lower()):
                log_error("upscaler", "extract_zip_unsafe_path", "Unsafe ZIP member path blocked.", archive=zip_path, member=member.filename, dest=dest_dir)
                raise RuntimeError(f"Unsafe archive path skipped: {member.filename}")
        archive.extractall(dest_dir)
    log_success("upscaler", "extract_zip_complete", "ZIP archive extracted.", archive=zip_path, dest=dest_dir)


def safe_extract_7z(archive_path, dest_dir):
    seven_zip = find_7zip_executable()
    log_debug("upscaler", "extract_7z_start", "Extracting 7z archive.", archive=archive_path, dest=dest_dir, extractor=seven_zip or "py7zr")
    if seven_zip:
        validate_7z_paths(archive_path, dest_dir)
        result = subprocess.run(
            [seven_zip, "x", "-y", f"-o{Path(dest_dir)}", str(archive_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            log_error("upscaler", "extract_7z_failed", "7-Zip extraction failed.", archive=archive_path, dest=dest_dir, returncode=result.returncode, output=result.stdout[-1200:])
            raise RuntimeError(f"7-Zip extraction failed:\n{result.stdout[-1200:]}")
        log_success("upscaler", "extract_7z_complete", "7z archive extracted with 7-Zip.", archive=archive_path, dest=dest_dir, extractor=seven_zip)
        return
    try:
        import py7zr
    except Exception as exc:
        log_exception("upscaler", "extract_7z_missing_extractor", exc, "No 7z extractor available.", archive=archive_path)
        raise RuntimeError("7-Zip or py7zr is required to extract official OptiScaler .7z releases.") from exc
    dest_dir = Path(dest_dir).resolve()
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        for member in archive.getnames():
            target = (dest_dir / member).resolve()
            if not str(target).lower().startswith(str(dest_dir).lower()):
                log_error("upscaler", "extract_7z_unsafe_path", "Unsafe 7z member path blocked.", archive=archive_path, member=member, dest=dest_dir)
                raise RuntimeError(f"Unsafe archive path skipped: {member}")
        archive.extractall(dest_dir)
    log_success("upscaler", "extract_7z_complete", "7z archive extracted with py7zr.", archive=archive_path, dest=dest_dir)


def find_7zip_executable():
    bundled = bundled_7zip_executable()
    if bundled:
        return bundled
    names = ("7z.exe", "7z", "7zr.exe", "7zr")
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    likely = [
        ("7-Zip", "7z.exe"),
        ("AMD", "AMDInstallManager", "7z.exe"),
        ("AMD", "CIM", "Bin64", "7z.exe"),
        ("AMD", "CNext", "CNext", "7z.exe"),
        ("NanaZip", "NanaZipC.exe"),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root)
        for parts in likely:
            candidate = base.joinpath(*parts)
            if candidate.exists():
                return str(candidate)
    return ""


def bundled_7zip_executable():
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "tools" / "7zip" / "7z.exe",
        Path.cwd() / "source" / "tools" / "7zip" / "7z.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def validate_7z_paths(archive_path, dest_dir):
    try:
        import py7zr
    except Exception:
        return
    dest_dir = Path(dest_dir).resolve()
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        for member in archive.getnames():
            target = (dest_dir / member).resolve()
            if not str(target).lower().startswith(str(dest_dir).lower()):
                raise RuntimeError(f"Unsafe archive path skipped: {member}")


def safe_extract_archive(archive_path, dest_dir):
    low = str(archive_path).lower()
    if low.endswith(".zip"):
        safe_extract_zip(archive_path, dest_dir)
        return
    if low.endswith(".7z"):
        safe_extract_7z(archive_path, dest_dir)
        return
    log_error("upscaler", "extract_unsupported_archive", "Unsupported OptiScaler archive type.", archive=archive_path)
    raise RuntimeError(f"Unsupported OptiScaler archive type: {Path(archive_path).name}")


def find_extracted_optiscaler_payload(root):
    root = Path(root)
    direct = root / OPTISCALER_DLL
    if direct.exists():
        return root
    matches = [path.parent for path in root.rglob(OPTISCALER_DLL)]
    for parent in matches:
        if (parent / OPTISCALER_INI).exists():
            return parent
    if matches:
        return matches[0]
    raise RuntimeError("Downloaded archive did not contain OptiScaler.dll.")


def replace_directory_contents(source_dir, target_dir):
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)
    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    backup_dir = parent / f".{target_dir.name}_previous"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if target_dir.exists():
        log_debug("upscaler", "replace_directory_backup", "Backing up existing source directory.", source=source_dir, target=target_dir, backup=backup_dir)
        target_dir.rename(backup_dir)
    try:
        log_debug("upscaler", "replace_directory_copy", "Copying replacement directory.", source=source_dir, target=target_dir)
        shutil.copytree(source_dir, target_dir)
    except Exception:
        log_error("upscaler", "replace_directory_failed", "Directory replacement failed, restoring previous directory.", source=source_dir, target=target_dir, backup=backup_dir)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        if backup_dir.exists():
            backup_dir.rename(target_dir)
        raise
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    log_success("upscaler", "replace_directory_complete", "Directory replacement completed.", source=source_dir, target=target_dir)


def update_optiscaler_source_from_github(target_dir):
    log_debug("upscaler", "optiscaler_update_start", "Updating OptiScaler source from GitHub.", target=target_dir)
    tag, asset_name, asset_url = latest_optiscaler_release_asset()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        archive_path = temp_dir / asset_name
        extract_dir = temp_dir / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        download_file(asset_url, archive_path)
        safe_extract_archive(archive_path, extract_dir)
        payload_dir = find_extracted_optiscaler_payload(extract_dir)
        replace_directory_contents(payload_dir, target_dir)
    metadata = {
        "tag": tag,
        "asset": asset_name,
        "updated_at": int(time.time()),
        "source": "https://github.com/optiscaler/OptiScaler/releases/latest",
    }
    Path(target_dir, OPTISCALER_SOURCE_METADATA).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    log_success("upscaler", "optiscaler_update_complete", "OptiScaler source updated.", target=target_dir, tag=tag, asset=asset_name)
    return metadata


def game_root(game):
    path = safe_text(game.get("path") or game.get("install_dir"))
    if path and os.path.isdir(path):
        return Path(path).resolve()
    exe = safe_text(game.get("exe_path"))
    if exe and os.path.isfile(exe):
        return Path(exe).resolve().parent
    return None


def candidate_install_dirs(game):
    root = game_root(game)
    dirs = []
    if root:
        dirs.extend(unreal_shipping_dirs(root))
    exe = safe_text(game.get("exe_path"))
    if exe and os.path.isfile(exe):
        exe_path = Path(exe).resolve()
        if is_unreal_shipping_exe(exe_path):
            dirs.insert(0, exe_path.parent)
        else:
            dirs.append(exe_path.parent)
    if root:
        for parts in COMMON_GAME_BIN_DIRS:
            candidate = root.joinpath(*parts)
            if candidate.is_dir():
                dirs.append(candidate)
        dirs.append(root)

    unique = []
    seen = set()
    for directory in dirs:
        key = str(directory).lower()
        if key not in seen:
            unique.append(directory)
            seen.add(key)
    return unique


def is_unreal_shipping_exe(path):
    name = Path(path).name.lower()
    return name.endswith("-win64-shipping.exe") or name.endswith("-wingdk-shipping.exe")


def unreal_shipping_dirs(root):
    root = Path(root)
    dirs = []
    patterns = (
        "*-Win64-Shipping.exe",
        "*-WinGDK-Shipping.exe",
        "*-win64-shipping.exe",
        "*-wingdk-shipping.exe",
    )
    for pattern in patterns:
        try:
            for exe in root.rglob(pattern):
                parent = exe.parent
                parts = {part.lower() for part in parent.parts}
                if "binaries" in parts and ("win64" in parts or "wingdk" in parts):
                    if "engine" in parts:
                        dirs.append(parent)
                    else:
                        dirs.insert(0, parent)
        except Exception:
            pass
    return dirs


def iter_game_files(root, max_files=50000):
    if not root or not root.exists():
        return
    count = 0
    try:
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SKIPPED_SCAN_DIRS]
            for filename in files:
                count += 1
                if count > max_files:
                    return
                yield Path(current) / filename
    except Exception:
        return


def detect_anti_cheat(root):
    found = set()
    if not root:
        return []
    for file_path in iter_game_files(root, max_files=12000):
        name = file_path.name.lower()
        if name in ANTI_CHEAT_MARKERS:
            found.add(ANTI_CHEAT_MARKERS[name])
    return sorted(found)


def detect_game_upscalers(game):
    root = game_root(game)
    targets = []
    wrappers = []
    components = set()

    source_hash = optiscaler_dll_hash()

    search_roots = candidate_install_dirs(game)
    if root and root not in search_roots:
        search_roots.append(root)
    preferred_install_dir = search_roots[0] if search_roots else root
    install_dir = preferred_install_dir

    seen_paths = set()
    for directory in search_roots:
        if not directory or not directory.exists():
            continue
        for wrapper in OPTISCALER_WRAPPERS:
            candidate = directory / wrapper
            if candidate.exists():
                original_name = version_original_filename(candidate)
                if original_name.lower() == OPTISCALER_DLL.lower() or (
                    source_hash and file_sha256(candidate) == source_hash
                ):
                    wrappers.append(str(candidate))
                    if directory == preferred_install_dir or not install_dir:
                        install_dir = directory
        for file_path in iter_game_files(directory, max_files=26000):
            low = file_path.name.lower()
            if str(file_path).lower() in seen_paths:
                continue
            seen_paths.add(str(file_path).lower())
            if low in UPSCALER_TARGETS:
                family, label = UPSCALER_TARGETS[low]
                components.add(family)
                targets.append(
                    {
                        "path": str(file_path),
                        "file": file_path.name,
                        "family": family,
                        "label": label,
                    }
                )
                if (
                    not install_dir
                    and file_path.parent.name.lower() not in {"plugins", "sl.interposer"}
                    and "plugins" not in {part.lower() for part in file_path.parent.parts}
                ):
                    install_dir = file_path.parent

    if not install_dir:
        dirs = candidate_install_dirs(game)
        install_dir = dirs[0] if dirs else root

    if any((find_optiscaler_source() / name).exists() for name in ("fakenvapi.dll", "fakenvapi.ini")):
        components.add("Fakenvapi ready")
    if (find_optiscaler_source() / "dlssg_to_fsr3_amd_is_better.dll").exists():
        components.add("NukemFG ready")

    installed = bool(wrappers or (install_dir and (install_dir / OPTISCALER_INI).exists()))
    return {
        "supported": bool(targets or wrappers),
        "manual": bool(game.get("upscaler_manual")),
        "targets": targets,
        "components": sorted(components),
        "wrappers": wrappers,
        "installed": installed,
        "install_dir": str(install_dir) if install_dir else "",
        "anti_cheat": detect_anti_cheat(root),
        "version": file_version(wrappers[0]) if wrappers else file_version(find_optiscaler_source() / OPTISCALER_DLL),
    }


def should_show_upscaler_info(info):
    if not isinstance(info, dict):
        return False
    return bool(info.get("supported") or info.get("manual") or info.get("installed"))


def lightweight_upscaler_info(game):
    exe = safe_text(game.get("exe_path"))
    if exe and os.path.isfile(exe):
        install_dir = str(Path(exe).resolve().parent)
    else:
        root = game_root(game)
        install_dir = str(root) if root else safe_text(game.get("path"))
    return {
        "supported": False,
        "manual": bool(game.get("upscaler_manual")),
        "targets": [],
        "components": [],
        "wrappers": [],
        "installed": False,
        "install_dir": install_dir,
        "anti_cheat": [],
        "version": file_version(find_optiscaler_source() / OPTISCALER_DLL),
        "scanning": True,
    }


class UpscalerScanWorker(QThread):
    result_ready = pyqtSignal(str, dict, dict)
    finished_all = pyqtSignal(int)

    def __init__(self, games, parent=None):
        super().__init__(parent)
        self.games = [dict(game) for game in games if isinstance(game, dict)]

    def run(self):
        count = 0
        for game in self.games:
            if self.isInterruptionRequested():
                break
            key = cache_key_for_game(game)
            info = detect_game_upscalers(game)
            self.result_ready.emit(key, game, info)
            count += 1
        self.finished_all.emit(count)


class LoadingSpinner(QWidget):
    def __init__(self, parent=None, size=26):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def start(self):
        self.show()
        if not self.timer.isActive():
            self.timer.start(32)

    def stop(self):
        self.timer.stop()
        self.hide()

    def tick(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = max(5, min(self.width(), self.height()) // 2 - 4)
        for step in range(12):
            alpha = int(45 + (step + 1) * 17)
            color = QColor(179, 138, 255, min(255, alpha))
            painter.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap))
            painter.save()
            painter.translate(center)
            painter.rotate(self.angle + step * 30)
            painter.drawLine(0, -radius, 0, -max(2, radius - 5))
            painter.restore()


class DialogOperationWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            ok, message = self.callback()
        except Exception as exc:
            ok, message = False, str(exc)
        self.finished.emit(bool(ok), str(message or ""))


class SmoothComboListView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoScroll(False)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        bar = self.verticalScrollBar()
        previous_value = bar.value()
        super().mouseMoveEvent(event)
        if not event.buttons() and bar.value() != previous_value:
            bar.setValue(previous_value)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        step = max(18, bar.singleStep() * 3)
        delta = event.angleDelta().y()
        if delta:
            bar.setValue(bar.value() - int(delta / 120) * step)
            event.accept()
            return
        super().wheelEvent(event)


def card_poster(poster_path, width, height):
    label = QLabel("No Poster")
    label.setObjectName("PosterLabel")
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(width, height)
    if poster_path and os.path.exists(poster_path):
        clean = sanitize_png_file(poster_path)
        pixmap = QPixmap(clean)
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            return label
    return label


class OptiScalerGameCard(QFrame):
    def __init__(self, index, game, info, manage_callback, launch_callback, parent=None):
        super().__init__(parent)
        self.index = index
        self.game = game
        self.info = info
        self.manage_callback = manage_callback
        self.launch_callback = launch_callback
        self.setObjectName("GameCard")
        self.setFixedWidth(230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(9)

        layout.addWidget(card_poster(game.get("poster", ""), 214, 292), alignment=Qt.AlignCenter)

        title = QLabel(game.get("name", "Unknown Game"))
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 14px; font-weight: 900; color: #ffffff;")
        title.setMinimumHeight(36)
        layout.addWidget(title)

        status = QLabel("Installed" if info.get("installed") else "Ready")
        if info.get("scanning"):
            status.setText("Scanning...")
        status.setObjectName("StatusGood" if info.get("installed") else "Muted")
        layout.addWidget(status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        manage = QPushButton("Manage")
        manage.setObjectName("PrimaryButton")
        manage.clicked.connect(lambda: self.manage_callback(self.index))
        launch = QPushButton("Launch")
        launch.clicked.connect(lambda: self.launch_callback(self.index))
        buttons.addWidget(manage)
        buttons.addWidget(launch)
        layout.addLayout(buttons)


class OptiScalerManageDialog(QDialog):
    def __init__(self, game, info, parent_page):
        super().__init__(parent_page)
        self.game = game
        self.info = info
        self.parent_page = parent_page
        self.operation_worker = None
        self.busy_widgets = []
        self.setWindowTitle(f"Manage OptiScaler - {game.get('name', 'Game')}")
        self.setMinimumSize(900, 560)
        self.setStyleSheet(FSR_PAGE_STYLE + PURPLE_SCROLLBAR_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(16)

        left = QFrame()
        left.setObjectName("Panel")
        left.setFixedWidth(255)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10)
        left_layout.addWidget(card_poster(game.get("poster", ""), 239, 326), alignment=Qt.AlignCenter)

        title = QLabel(game.get("name", "Unknown Game"))
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 17px; font-weight: 900; color: #ffffff;")
        left_layout.addWidget(title)

        self.browse_btn = QPushButton("Choose Install Folder")
        self.browse_btn.clicked.connect(self.choose_install_folder)
        left_layout.addWidget(self.browse_btn)
        left_layout.addStretch(1)

        layout.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(10)
        layout.addLayout(right, stretch=1)

        status_panel = QFrame()
        status_panel.setObjectName("StatusPanel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(5)

        status_title = QLabel("OptiScaler Status")
        status_title.setObjectName("SectionTitle")
        status_layout.addWidget(status_title)
        status = QLabel(self.status_text())
        status.setObjectName("StatusGood" if info.get("installed") else "StatusBad")
        status_layout.addWidget(status)
        if info.get("wrappers"):
            wrapper_label = QLabel(os.path.basename(info.get("wrappers", [""])[0]))
            wrapper_label.setObjectName("Muted")
            status_layout.addWidget(wrapper_label)
        right.addWidget(status_panel)

        note = QFrame()
        note.setObjectName("InfoPanel")
        note_layout = QHBoxLayout(note)
        note_layout.setContentsMargins(12, 9, 12, 9)
        note_text = QLabel("This local OptiScaler package includes Fakenvapi and NukemFG when present in the official folder.")
        note_text.setObjectName("HintLabel")
        note_text.setWordWrap(True)
        note_layout.addWidget(note_text)
        right.addWidget(note)

        form = QFrame()
        form.setObjectName("Panel")
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(9)
        right.addWidget(form)

        metadata = load_optiscaler_source_metadata(self.parent_page.source_dir())
        release_tag = metadata.get("tag") or "Latest"
        asset_name = metadata.get("asset") or "Official release asset"
        self.channel = self.combo([str(release_tag)])
        self.channel.setCurrentIndex(0)
        self.version = QLineEdit("Stable")
        self.version.setReadOnly(True)
        self.asset = QLineEdit(str(asset_name))
        self.asset.setReadOnly(True)
        self.wrapper = self.combo(OPTISCALER_WRAPPERS)
        self.wrapper.setCurrentText(self.detect_default_wrapper())
        self.gpu = self.combo(["Auto / ask nothing", "AMD or Intel", "NVIDIA"])
        self.spoofing = QCheckBox("Enable NVIDIA spoofing for DLSS inputs")
        self.spoofing.setChecked(True)
        self.nvidia_identity = QCheckBox("Spoof GPU identity as NVIDIA RTX 4090")
        self.nvidia_identity.setChecked(True)
        self.fsr4_int8 = self.combo(self.fsr4_options())
        latest_label = fsr4_option_label("4.0.2c")
        if self.fsr4_int8.findText(latest_label) >= 0:
            self.fsr4_int8.setCurrentText(latest_label)
        self.optipatcher = self.combo(["Latest from GitHub Releases", "None"])
        self.fakenvapi = self.combo(self.component_options("fakenvapi.dll", "Bundled"))
        self.nukemfg = self.combo(self.component_options("dlssg_to_fsr3_amd_is_better.dll", "Bundled"))
        self.fakenvapi.setEnabled(False)
        self.nukemfg.setEnabled(False)
        self.agility = QCheckBox("FSR Agility SDK upgrade")
        self.agility.setChecked(False)

        self.add_field(form_layout, 0, 0, "OptiScaler", self.version)
        self.add_field(form_layout, 0, 1, "Release", self.channel)
        self.add_field(form_layout, 1, 0, "Release asset", self.asset)
        self.add_field(form_layout, 1, 1, "FSR4 INT8", self.fsr4_int8)
        self.add_field(form_layout, 2, 0, "Fakenvapi", self.fakenvapi)
        self.add_field(form_layout, 2, 1, "Injection", self.wrapper)
        self.add_field(form_layout, 3, 0, "OptiPatcher", self.optipatcher)
        self.add_field(form_layout, 3, 1, "GPU profile", self.gpu)
        self.add_field(form_layout, 4, 0, "NukemFG", self.nukemfg)
        form_layout.addWidget(self.spoofing, 5, 0, 1, 2)
        form_layout.addWidget(self.nvidia_identity, 6, 0, 1, 2)
        form_layout.addWidget(self.agility, 7, 0, 1, 2)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.busy_spinner = LoadingSpinner(size=26)
        self.busy_spinner.hide()
        self.busy_label = QLabel("")
        self.busy_label.setObjectName("Muted")
        self.busy_label.hide()
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.setObjectName("DangerButton")
        self.uninstall_btn.clicked.connect(self.uninstall)
        self.install_btn = QPushButton("Install / Reinstall")
        self.install_btn.setObjectName("GreenButton")
        self.install_btn.clicked.connect(self.install)
        self.launch_btn = QPushButton("Launch")
        self.launch_btn.clicked.connect(lambda: self.parent_page.launch_game(self.game))
        actions.addWidget(self.busy_spinner)
        actions.addWidget(self.busy_label)
        actions.addWidget(self.uninstall_btn)
        actions.addWidget(self.install_btn)
        actions.addWidget(self.launch_btn)
        right.addLayout(actions)
        right.addStretch(1)
        self.busy_widgets = [
            self.browse_btn,
            self.channel,
            self.version,
            self.asset,
            self.wrapper,
            self.gpu,
            self.spoofing,
            self.nvidia_identity,
            self.fsr4_int8,
            self.optipatcher,
            self.fakenvapi,
            self.nukemfg,
            self.agility,
            self.uninstall_btn,
            self.install_btn,
            self.launch_btn,
        ]

    def combo(self, items):
        box = QComboBox()
        view = SmoothComboListView()
        view.setObjectName("ComboDropdown")
        view.setSpacing(4)
        view.setUniformItemSizes(False)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setMaximumHeight(154)
        box.setView(view)
        box.setMaxVisibleItems(5)
        box.addItems(items)
        for index in range(box.count()):
            box.setItemData(index, QSize(0, 30), Qt.SizeHintRole)
        return box

    def value_combo(self, items):
        box = QComboBox()
        view = SmoothComboListView()
        view.setObjectName("ComboDropdown")
        view.setSpacing(4)
        view.setUniformItemSizes(False)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setMaximumHeight(154)
        box.setView(view)
        box.setMaxVisibleItems(5)
        for value, label in items:
            box.addItem(label, value)
        for index in range(box.count()):
            box.setItemData(index, QSize(0, 30), Qt.SizeHintRole)
        return box

    def component_options(self, filename, bundled_label):
        source = self.parent_page.source_dir()
        if (source / filename).exists():
            return [bundled_label]
        return ["None"]

    def fsr4_options(self):
        return ["None"] + [fsr4_option_label(version) for version in available_fsr4_int8_versions()]

    def add_field(self, layout, row, column, label, widget):
        wrap = QVBoxLayout()
        title = QLabel(label)
        title.setObjectName("Muted")
        wrap.addWidget(title)
        wrap.addWidget(widget)
        layout.addLayout(wrap, row, column)

    def status_text(self):
        if self.info.get("installed"):
            version = self.info.get("version") or "unknown version"
            return f"● OptiScaler Installed  {version}"
        return "● OptiScaler Not Installed"

    def component_pills(self):
        components = list(self.info.get("components") or [])
        if not components:
            components = ["No DLSS/FSR/XeSS DLLs detected"]
        return components[:6]

    def detect_default_wrapper(self):
        wrappers = self.info.get("wrappers") or []
        if wrappers:
            return os.path.basename(wrappers[0])
        return "dxgi.dll"

    def choose_install_folder(self):
        current = self.info.get("install_dir") or self.game.get("path") or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose OptiScaler install folder", current)
        if folder:
            self.info["install_dir"] = folder

    def selected_settings(self):
        gpu = self.gpu.currentText()
        spoof = self.spoofing.isChecked()
        spoof_identity = spoof and self.nvidia_identity.isChecked()
        if gpu == "NVIDIA":
            spoof_value = "false" if not spoof else "auto"
        else:
            spoof_value = "true" if spoof else "false"
        settings = {
            "__fsr4_int8": fsr4_option_value(self.fsr4_int8.currentText()),
            "__optipatcher": self.optipatcher.currentText(),
            "Dxgi": spoof_value,
            "StreamlineSpoofing": spoof_value,
            "Vulkan": spoof_value,
            "VulkanExtensionSpoofing": spoof_value,
            "SpoofHAGS": spoof_value,
            "Registry": spoof_value,
            "OverrideNvapiDll": spoof_value,
            "DisableFlipMetering": spoof_value,
            "LoadAsiPlugins": "true" if self.optipatcher.currentText() != "None" else "auto",
            "FsrAgilitySDKUpgrade": "true" if self.agility.isChecked() else "auto",
        }
        if spoof_identity:
            settings.update(
                {
                    "SpoofedVendorId": "0x10de",
                    "SpoofedDeviceId": "0x2684",
                    "SpoofedGPUName": "NVIDIA GeForce RTX 4090",
                    "TargetVendorId": "auto",
                    "TargetDeviceId": "auto",
                }
            )
        else:
            settings.update(
                {
                    "SpoofedVendorId": "auto",
                    "SpoofedDeviceId": "auto",
                    "SpoofedGPUName": "auto",
                    "TargetVendorId": "auto",
                    "TargetDeviceId": "auto",
                }
            )
        return settings

    def set_busy(self, busy, text=""):
        for widget in self.busy_widgets:
            widget.setEnabled(not busy)
        self.busy_label.setText(text)
        self.busy_label.setVisible(bool(busy))
        if busy:
            self.busy_spinner.start()
        else:
            self.busy_spinner.stop()

    def run_operation(self, label, callback):
        if self.operation_worker and self.operation_worker.isRunning():
            log_warning("upscaler", "dialog_operation_busy", "Operation ignored because another operation is already running.", game=self.game.get("name", ""), label=label)
            return
        log_debug("upscaler", "dialog_operation_start", "Starting OptiScaler dialog operation.", game=self.game.get("name", ""), label=label)
        self.set_busy(True, label)
        self.operation_worker = DialogOperationWorker(callback, self)
        self.operation_worker.finished.connect(self.on_operation_finished)
        self.operation_worker.start()

    def on_operation_finished(self, ok, message):
        self.set_busy(False)
        if ok:
            log_success("upscaler", "dialog_operation_success", message, game=self.game.get("name", ""))
            QMessageBox.information(self, "OptiScaler", message)
            self.info = detect_game_upscalers(self.game)
            self.parent_page.refresh_grid()
        else:
            log_error("upscaler", "dialog_operation_failed", message, game=self.game.get("name", ""))
            QMessageBox.warning(self, "OptiScaler", message)

    def install(self):
        wrapper = self.wrapper.currentText()
        settings = self.selected_settings()
        log_debug("upscaler", "install_clicked", "Install/reinstall clicked.", game=self.game.get("name", ""), wrapper=wrapper, settings=settings)
        self.run_operation(
            "Installing...",
            lambda: self.parent_page.install_optiscaler(self.game, self.info, wrapper, settings),
        )

    def uninstall(self):
        answer = QMessageBox.question(
            self,
            "Uninstall OptiScaler",
            "Remove OptiScaler files from this game and restore backed-up files?",
        )
        if answer != QMessageBox.Yes:
            log_warning("upscaler", "uninstall_cancelled", "User cancelled OptiScaler uninstall.", game=self.game.get("name", ""))
            return
        log_debug("upscaler", "uninstall_clicked", "Uninstall clicked.", game=self.game.get("name", ""))
        self.run_operation(
            "Removing...",
            lambda: self.parent_page.uninstall_optiscaler(self.game, self.info),
        )

    def closeEvent(self, event):
        if self.operation_worker and self.operation_worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)


class XGCRFsrModsPage(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self, get_games_func=None, get_selected_index_func=None, external_log_func=None, parent=None):
        super().__init__(parent)
        self.get_games_func = get_games_func or (lambda: [])
        self.get_selected_index_func = get_selected_index_func or (lambda: -1)
        self.external_log_func = external_log_func
        self.log_signal.connect(self.emit_external_log)
        self.cache = load_cache()
        self.cache.setdefault("scan_results", {})
        self.visible_entries = []
        self._grid_columns = 0
        self.scan_worker = None
        self._render_pending = False
        self.setStyleSheet(FSR_PAGE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_wrap = QVBoxLayout()
        title = QLabel("Upscaler Mods")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)
        header.addLayout(title_wrap, stretch=1)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(lambda: self.refresh_grid(force_scan=True))
        update_source = QPushButton("Update OptiScaler")
        update_source.clicked.connect(self.update_optiscaler_source)
        manual = QPushButton("Manual Add")
        manual.setObjectName("PrimaryButton")
        manual.clicked.connect(self.manual_add_game)
        header.addWidget(refresh)
        header.addWidget(update_source)
        header.addWidget(manual)
        layout.addLayout(header)

        self.notice = QLabel("")
        self.notice.setObjectName("StatusBad")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(PURPLE_SCROLLBAR_STYLE)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, stretch=1)

        self.empty = QLabel("No compatible upscaler games detected yet. Use Manual Add if you want to manage one anyway.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Muted")
        self.grid.addWidget(self.empty, 0, 0)

        QTimer.singleShot(0, self.refresh_grid)

    def log(self, message):
        self.log_signal.emit(str(message))

    def emit_external_log(self, message):
        if self.external_log_func:
            self.external_log_func(message)

    def source_dir(self):
        return find_optiscaler_source()

    def update_optiscaler_source(self):
        target = self.source_dir()
        try:
            self.log("Updating OptiScaler source from GitHub releases...")
            log_debug("upscaler", "update_source_clicked", "Updating OptiScaler source from GitHub releases.", target=target)
            metadata = update_optiscaler_source_from_github(target)
            self.cache.setdefault("scan_results", {}).clear()
            save_cache(self.cache)
            QMessageBox.information(
                self,
                "OptiScaler Updated",
                f"Updated OptiScaler source to {metadata.get('tag', 'latest')}.\n{target}",
            )
            self.log(f"OptiScaler source updated: {metadata.get('tag', 'latest')}")
            log_success("upscaler", "update_source_success", "OptiScaler source update completed.", target=target, metadata=metadata)
        except Exception as exc:
            QMessageBox.warning(self, "OptiScaler Update", f"Could not update OptiScaler:\n{exc}")
            self.log(f"OptiScaler update failed: {exc}")
            log_exception("upscaler", "update_source_failed", exc, "Could not update OptiScaler source.", target=target)
        self.refresh_grid(force_scan=True)

    def games_from_callback(self):
        try:
            games = self.get_games_func() or []
        except Exception:
            games = []
        return [dict(game) for game in games if isinstance(game, dict)]

    def manual_entries(self):
        entries = self.cache.get("manual_entries", [])
        if isinstance(entries, list):
            return [dict(item, upscaler_manual=True) for item in entries if isinstance(item, dict)]
        return []

    def all_games(self):
        games = self.games_from_callback()
        seen = {cache_key_for_game(game) for game in games}
        for manual in self.manual_entries():
            key = cache_key_for_game(manual)
            if key not in seen:
                games.append(manual)
                seen.add(key)
        return games

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def cached_info_for_game(self, game):
        key = cache_key_for_game(game)
        record = self.cache.get("scan_results", {}).get(key)
        if not isinstance(record, dict):
            return None
        if record.get("signature") != game_scan_signature(game):
            return None
        info = record.get("info")
        return info if isinstance(info, dict) else None

    def cache_scan_result(self, key, game, info):
        self.cache.setdefault("scan_results", {})[key] = {
            "signature": game_scan_signature(game),
            "info": info,
            "scanned_at": int(time.time()),
        }

    def refresh_grid(self, force_scan=False):
        source = self.source_dir()
        source_ok = (source / OPTISCALER_DLL).exists()
        if not source_ok:
            self.notice.setText(f"Missing {OPTISCALER_DLL} in {source}")
        else:
            self.notice.setText(
                "Online games can trigger anti-cheat issues."
            )

        entries = []
        pending_scan = []
        for game in self.all_games():
            info = None if force_scan else self.cached_info_for_game(game)
            if info is None:
                pending_scan.append(game)
                info = lightweight_upscaler_info(game)
            if should_show_upscaler_info(info):
                entries.append((game, info))
        self.visible_entries = entries
        self.render_visible_entries()
        if pending_scan:
            self.start_scan_worker(pending_scan)

    def render_visible_entries(self):
        self.clear_grid()

        if not self.visible_entries:
            self.empty = QLabel("No compatible upscaler games detected. Manual Add keeps a game visible here.")
            self.empty.setAlignment(Qt.AlignCenter)
            self.empty.setObjectName("Muted")
            self.grid.addWidget(self.empty, 0, 0)
            return

        columns = self.grid_columns()
        self._grid_columns = columns
        for index, (game, info) in enumerate(self.visible_entries):
            row = index // columns
            column = index % columns
            card = OptiScalerGameCard(index, game, info, self.open_manage_dialog, self.launch_for_visible_index)
            self.grid.addWidget(card, row, column)
        self.grid.setRowStretch((len(self.visible_entries) // columns) + 1, 1)
        self.grid.setColumnStretch(columns, 1)

    def start_scan_worker(self, games):
        if self.scan_worker and self.scan_worker.isRunning():
            return
        self.notice.setText("Scanning upscaler support in the background...")
        self.scan_worker = UpscalerScanWorker(games, self)
        self.scan_worker.result_ready.connect(self.on_scan_result)
        self.scan_worker.finished_all.connect(self.on_scan_finished)
        self.scan_worker.start()

    def on_scan_result(self, key, game, info):
        self.cache_scan_result(key, game, info)
        if should_show_upscaler_info(info):
            replaced = False
            for idx, (entry_game, _) in enumerate(self.visible_entries):
                if cache_key_for_game(entry_game) == key:
                    self.visible_entries[idx] = (game, info)
                    replaced = True
                    break
            if not replaced:
                self.visible_entries.append((game, info))
        else:
            self.visible_entries = [
                (entry_game, entry_info)
                for entry_game, entry_info in self.visible_entries
                if cache_key_for_game(entry_game) != key
            ]
        self.schedule_render()

    def schedule_render(self):
        if self._render_pending:
            return
        self._render_pending = True
        QTimer.singleShot(80, self.flush_render)

    def flush_render(self):
        self._render_pending = False
        self.render_visible_entries()

    def on_scan_finished(self, count):
        save_cache(self.cache)
        if count:
            self.notice.setText(f"Upscaler scan complete. Checked {count} game(s).")
        else:
            self.notice.setText("Upscaler scan complete.")
        self.render_visible_entries()

    def grid_columns(self):
        return max(1, self.scroll.viewport().width() // 250 if hasattr(self, "scroll") else self.width() // 250)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.grid_columns() != self._grid_columns:
            QTimer.singleShot(0, self.render_visible_entries)

    def closeEvent(self, event):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.requestInterruption()
        super().closeEvent(event)

    def manual_add_game(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose game folder")
        if not folder:
            log_warning("upscaler", "manual_add_cancelled_folder", "Manual upscaler add cancelled before folder selection.")
            return
        exe = QFileDialog.getOpenFileName(self, "Choose game executable", folder, "Executables (*.exe)")[0]
        name = Path(exe).stem if exe else Path(folder).name
        entry = {
            "name": name,
            "path": folder,
            "exe_path": exe,
            "poster": "",
            "poster_status": "Manual",
            "source": "Manual Upscaler",
            "upscaler_manual": True,
        }
        entries = self.cache.setdefault("manual_entries", [])
        key = cache_key_for_game(entry)
        entries[:] = [item for item in entries if cache_key_for_game(item) != key]
        entries.append(entry)
        save_cache(self.cache)
        self.log(f"Manual upscaler entry added: {name}")
        log_success("upscaler", "manual_add_success", "Manual upscaler entry added.", name=name, folder=folder, exe=exe)
        self.refresh_grid()

    def open_manage_dialog(self, visible_index):
        if visible_index < 0 or visible_index >= len(self.visible_entries):
            return
        game, info = self.visible_entries[visible_index]
        dialog = OptiScalerManageDialog(game, info, self)
        dialog.exec_()
        self.cache = load_cache()
        self.refresh_grid()

    def launch_for_visible_index(self, visible_index):
        if visible_index < 0 or visible_index >= len(self.visible_entries):
            return
        game, _ = self.visible_entries[visible_index]
        self.launch_game(game)

    def launch_game(self, game):
        exe = safe_text(game.get("exe_path"))
        if not exe or not os.path.isfile(exe):
            root = safe_text(game.get("path"))
            exe = find_game_executable(root) if root else ""
        if not exe or not os.path.isfile(exe):
            QMessageBox.warning(self, "Launch Game", "No executable was found for this game.")
            log_warning("upscaler", "launch_missing_exe", "No executable was found for this game.", game=game.get("name", ""), exe=exe)
            return
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe) or None)
            self.log(f"Launched: {game.get('name', os.path.basename(exe))}")
            log_success("upscaler", "launch_success", "Game launched from Upscaler tab.", game=game.get("name", ""), exe=exe)
        except Exception as exc:
            QMessageBox.warning(self, "Launch Game", f"Could not launch game:\n{exc}")
            log_exception("upscaler", "launch_failed", exc, "Could not launch game.", game=game.get("name", ""), exe=exe)

    def install_record_key(self, install_dir):
        return hashlib.sha1(str(install_dir).lower().encode("utf-8", errors="ignore")).hexdigest()

    def backup_root(self, game, install_dir):
        key = cache_key_for_game(game)[:12]
        return GLOBAL_BACKUP_ROOT / "optiscaler" / key / hashlib.sha1(
            str(install_dir).lower().encode("utf-8", errors="ignore")
        ).hexdigest()[:12]

    def backup_dest_file(self, src, backup_root, relative):
        backup_file = backup_root / "files" / relative
        if src.exists() and not backup_file.exists():
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, backup_file)
            log_debug("upscaler", "backup_file", "Backed up existing game file.", source=src, backup=backup_file, relative=relative)
        return str(backup_file) if backup_file.exists() else ""

    def copy_payload_file(self, src, dest, record, backup_root, relative=None):
        relative = relative or dest.name
        backup = self.backup_dest_file(dest, backup_root, relative)
        if backup:
            record["backups"][relative] = backup
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        log_debug("upscaler", "copy_payload_file", "Copied OptiScaler payload file.", source=src, dest=dest, relative=relative, backup=backup)
        if relative not in record["files"]:
            record["files"].append(relative)

    def install_optiscaler(self, game, info, wrapper, settings):
        source = self.source_dir()
        if not (source / OPTISCALER_DLL).exists():
            log_error("upscaler", "install_missing_source", "OptiScaler source DLL missing.", game=game.get("name", ""), source=source, dll=OPTISCALER_DLL)
            return False, f"Official OptiScaler source is missing {OPTISCALER_DLL}."

        install_dir = Path(info.get("install_dir") or "")
        if not install_dir.exists():
            dirs = candidate_install_dirs(game)
            install_dir = dirs[0] if dirs else Path(safe_text(game.get("path") or ""))
        if not install_dir or not install_dir.exists():
            log_error("upscaler", "install_invalid_folder", "Could not resolve valid OptiScaler install folder.", game=game.get("name", ""), install_dir=install_dir)
            return False, "Could not resolve a valid install folder."
        log_debug(
            "upscaler",
            "install_start",
            "Starting OptiScaler install.",
            game=game.get("name", ""),
            install_dir=install_dir,
            wrapper=wrapper,
            fsr4_int8=safe_text(settings.get("__fsr4_int8")),
            optipatcher=safe_text(settings.get("__optipatcher")),
        )

        backup_root = self.backup_root(game, install_dir)
        backup_root.mkdir(parents=True, exist_ok=True)
        record = {
            "game": game.get("name", ""),
            "install_dir": str(install_dir),
            "wrapper": wrapper,
            "files": [],
            "backups": {},
            "created_at": int(time.time()),
            "source": str(source),
        }

        skipped = {"setup_windows.bat", "setup_linux.sh"}
        for src in source.iterdir():
            if src.name in skipped or src.name.startswith("!! README"):
                continue
            if src.name == OPTISCALER_DLL:
                continue
            if src.is_file():
                self.copy_payload_file(src, install_dir / src.name, record, backup_root)
            elif src.is_dir():
                for child in src.rglob("*"):
                    if child.is_file():
                        rel = str(child.relative_to(source))
                        self.copy_payload_file(child, install_dir / rel, record, backup_root, rel)

        wrapper_dest = install_dir / wrapper
        self.copy_payload_file(source / OPTISCALER_DLL, wrapper_dest, record, backup_root, wrapper)
        log_success("upscaler", "install_wrapper", "Installed OptiScaler wrapper DLL.", game=game.get("name", ""), wrapper=wrapper, dest=wrapper_dest)

        fsr4_version = safe_text(settings.get("__fsr4_int8"))
        if fsr4_version and fsr4_version != "None":
            fsr4_dll = fsr4_int8_source_file(fsr4_version)
            if fsr4_dll.exists():
                self.copy_payload_file(
                    fsr4_dll,
                    install_dir / "amd_fidelityfx_upscaler_dx12.dll",
                    record,
                    backup_root,
                    "amd_fidelityfx_upscaler_dx12.dll",
                )
                record["fsr4_int8_version"] = fsr4_version
                record["fsr4_int8_source_name"] = fsr4_dll.name
                log_success(
                    "upscaler",
                    "fsr4_int8_replace",
                    "Replaced OptiScaler FSR upscaler DLL with bundled FSR4 INT8 DLL.",
                    game=game.get("name", ""),
                    version=fsr4_version,
                    source=fsr4_dll,
                    dest=install_dir / "amd_fidelityfx_upscaler_dx12.dll",
                )
            else:
                log_error("upscaler", "fsr4_int8_missing", "Selected FSR4 INT8 DLL was missing.", game=game.get("name", ""), version=fsr4_version, expected=fsr4_dll)
                return False, f"FSR4 INT8 version '{fsr4_version}' is missing an upscaler DLL."

        optipatcher_choice = safe_text(settings.get("__optipatcher"))
        if optipatcher_choice and optipatcher_choice != "None":
            try:
                tag, asset_name, asset_url = latest_optipatcher_release_asset()
                plugins_dir = install_dir / "plugins"
                plugins_dir.mkdir(parents=True, exist_ok=True)
                plugin_dest = plugins_dir / "OptiPatcher.asi"
                backup = self.backup_dest_file(plugin_dest, backup_root, "plugins/OptiPatcher.asi")
                if backup:
                    record["backups"]["plugins/OptiPatcher.asi"] = backup
                download_file(asset_url, plugin_dest)
                if "plugins/OptiPatcher.asi" not in record["files"]:
                    record["files"].append("plugins/OptiPatcher.asi")
                record["optipatcher_version"] = tag
                record["optipatcher_asset"] = asset_name
                settings["LoadAsiPlugins"] = "true"
                self.log(f"Downloaded OptiPatcher {tag}: {asset_name}")
                log_success("upscaler", "optipatcher_install", "Installed OptiPatcher plugin.", game=game.get("name", ""), tag=tag, asset=asset_name, dest=plugin_dest)
            except Exception as exc:
                log_exception("upscaler", "optipatcher_install_failed", exc, "OptiPatcher latest release download failed.", game=game.get("name", ""))
                return False, f"OptiPatcher latest release download failed:\n{exc}"

        ini_path = install_dir / OPTISCALER_INI
        if ini_path.exists():
            ini_settings = {key: value for key, value in settings.items() if not key.startswith("__")}
            apply_ini_settings(ini_path, ini_settings)
            log_success("upscaler", "optiscaler_ini_patch", "Applied OptiScaler INI settings.", game=game.get("name", ""), ini=ini_path, settings=ini_settings)
        else:
            log_warning("upscaler", "optiscaler_ini_missing", "OptiScaler INI was not found after install.", game=game.get("name", ""), ini=ini_path)

        self.write_remove_bat(install_dir, wrapper, record)
        record_path = backup_root / "optiscaler_record.json"
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

        records = self.cache.setdefault("install_records", {})
        records[self.install_record_key(install_dir)] = str(record_path)
        save_cache(self.cache)
        self.log(f"OptiScaler installed for {game.get('name', 'game')} as {wrapper}")
        log_success("upscaler", "install_complete", "OptiScaler install completed.", game=game.get("name", ""), install_dir=install_dir, wrapper=wrapper, record=record_path, file_count=len(record.get("files", [])), backup_count=len(record.get("backups", {})))
        return True, f"OptiScaler installed as {wrapper} beside the game executable."

    def write_remove_bat(self, install_dir, wrapper, record):
        remove_path = install_dir / "Remove OptiScaler.bat"
        files = [wrapper, "OptiScaler.log", "fakenvapi.log", "dlssg_to_fsr3.log"]
        files.extend([name for name in record["files"] if "\\" not in name and "/" not in name])
        unique = []
        for item in files:
            if item not in unique:
                unique.append(item)
        lines = ["@echo off", "echo Removing OptiScaler files..."]
        for item in unique:
            lines.append(f'del "{item}" 2>nul')
        lines.append("echo Done.")
        remove_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        log_debug("upscaler", "write_remove_bat", "Wrote Remove OptiScaler helper BAT.", path=remove_path, wrapper=wrapper)

    def find_record(self, install_dir, game=None):
        records = self.cache.get("install_records", {})
        key = self.install_record_key(install_dir)
        record_path = records.get(key)
        if record_path and os.path.exists(record_path):
            try:
                return Path(record_path), json.loads(Path(record_path).read_text(encoding="utf-8"))
            except Exception:
                return None, None
        if game:
            game_name = safe_text(game.get("name")).lower()
            root = game_root(game)
            root_text = str(root).lower() if root else ""
            for candidate in records.values():
                if not candidate or not os.path.exists(candidate):
                    continue
                try:
                    data = json.loads(Path(candidate).read_text(encoding="utf-8"))
                except Exception:
                    continue
                record_game = safe_text(data.get("game")).lower()
                record_dir = safe_text(data.get("install_dir")).lower()
                if (game_name and record_game == game_name) or (root_text and record_dir.startswith(root_text)):
                    return Path(candidate), data
        return None, None

    def uninstall_optiscaler(self, game, info):
        install_dir = Path(info.get("install_dir") or "")
        if not install_dir.exists():
            log_error("upscaler", "uninstall_invalid_folder", "Could not resolve OptiScaler install folder.", game=game.get("name", ""), install_dir=install_dir)
            return False, "Could not resolve this game's OptiScaler install folder."
        log_debug("upscaler", "uninstall_start", "Starting OptiScaler uninstall.", game=game.get("name", ""), install_dir=install_dir)

        record_path, record = self.find_record(install_dir, game)
        if not record:
            wrappers = info.get("wrappers") or ["dxgi.dll"]
            record = {
                "wrapper": os.path.basename(wrappers[0]),
                "files": [
                    OPTISCALER_INI,
                    "fakenvapi.ini",
                    "fakenvapi.dll",
                    "amd_fidelityfx_dx12.dll",
                    "amd_fidelityfx_framegeneration_dx12.dll",
                    "amd_fidelityfx_upscaler_dx12.dll",
                    "amd_fidelityfx_vk.dll",
                    "dlssg_to_fsr3_amd_is_better.dll",
                    "libxell.dll",
                    "libxess_dx11.dll",
                    "libxess_fg.dll",
                    "libxess.dll",
                    "D3D12_Optiscaler/D3D12Core.dll",
                    "Licenses/XeSS_LICENSE.txt",
                    "Licenses/FidelityFX_v2_LICENSE.md",
                    "Licenses/FidelityFX_v1_LICENSE.md",
                    "Licenses/DirectX_LICENSE.txt",
                ],
                "backups": {},
            }
            if record["wrapper"] not in record["files"]:
                record["files"].append(record["wrapper"])
            log_warning("upscaler", "uninstall_no_record", "No install record found; using fallback uninstall file list.", game=game.get("name", ""), install_dir=install_dir)
        if record.get("install_dir"):
            install_dir = Path(record.get("install_dir"))

        restored = 0
        removed = 0
        for relative in record.get("files", []):
            dest = install_dir / relative
            backup = record.get("backups", {}).get(relative)
            try:
                if backup and os.path.exists(backup):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, dest)
                    restored += 1
                    log_debug("upscaler", "restore_backup_file", "Restored backed-up file.", game=game.get("name", ""), dest=dest, backup=backup)
                elif dest.exists():
                    dest.unlink()
                    removed += 1
                    log_debug("upscaler", "remove_installed_file", "Removed installed OptiScaler file.", game=game.get("name", ""), path=dest)
            except Exception as exc:
                log_exception("upscaler", "uninstall_file_failed", exc, "Failed to remove or restore OptiScaler file.", game=game.get("name", ""), path=dest, backup=backup)

        for extra in ("OptiScaler.log", "fakenvapi.log", "dlssg_to_fsr3.log", "Remove OptiScaler.bat"):
            try:
                path = install_dir / extra
                if path.exists():
                    path.unlink()
                    removed += 1
                    log_debug("upscaler", "remove_extra_file", "Removed extra OptiScaler file.", game=game.get("name", ""), path=path)
            except Exception as exc:
                log_warning("upscaler", "remove_extra_file_failed", "Failed to remove extra OptiScaler file.", game=game.get("name", ""), path=install_dir / extra, error=str(exc))

        for directory in ("D3D12_Optiscaler", "Licenses"):
            try:
                path = install_dir / directory
                if path.exists():
                    for child in sorted(path.rglob("*"), reverse=True):
                        if child.is_dir():
                            child.rmdir()
                    path.rmdir()
            except Exception as exc:
                log_warning("upscaler", "remove_directory_failed", "Failed to remove OptiScaler support directory.", game=game.get("name", ""), path=install_dir / directory, error=str(exc))

        if record_path:
            try:
                record_path.unlink()
            except Exception as exc:
                log_warning("upscaler", "remove_record_failed", "Failed to remove OptiScaler install record.", game=game.get("name", ""), record=record_path, error=str(exc))
        records = self.cache.setdefault("install_records", {})
        records.pop(self.install_record_key(install_dir), None)
        if record_path:
            stale_keys = [key for key, value in records.items() if value == str(record_path)]
            for key in stale_keys:
                records.pop(key, None)
        save_cache(self.cache)
        self.log(f"OptiScaler uninstalled for {game.get('name', 'game')}")
        log_success("upscaler", "uninstall_complete", "OptiScaler uninstall completed.", game=game.get("name", ""), install_dir=install_dir, restored=restored, removed=removed)
        return True, f"OptiScaler removed. Restored {restored} backup(s), removed {removed} file(s)."

    def scan_selected_game(self):
        games = self.games_from_callback()
        index = self.get_selected_index_func()
        if index is None or index < 0 or index >= len(games):
            QMessageBox.information(self, "Upscaler Mods", "Select a game first.")
            return
        info = detect_game_upscalers(games[index])
        QMessageBox.information(
            self,
            "Upscaler Mods",
            "Compatible upscaler components detected." if should_show_upscaler_info(info) else "No DLSS/FSR/XeSS targets detected.",
        )
        self.refresh_grid()

    def install_mod(self):
        games = self.games_from_callback()
        index = self.get_selected_index_func()
        if index is None or index < 0 or index >= len(games):
            QMessageBox.information(self, "Upscaler Mods", "Select a game first.")
            return
        info = detect_game_upscalers(games[index])
        dialog = OptiScalerManageDialog(games[index], info, self)
        dialog.exec_()
        self.refresh_grid()

    def restore_original(self):
        games = self.games_from_callback()
        index = self.get_selected_index_func()
        if index is None or index < 0 or index >= len(games):
            QMessageBox.information(self, "Upscaler Mods", "Select a game first.")
            return
        info = detect_game_upscalers(games[index])
        ok, message = self.uninstall_optiscaler(games[index], info)
        if ok:
            QMessageBox.information(self, "Upscaler Mods", message)
        else:
            QMessageBox.warning(self, "Upscaler Mods", message)
        self.refresh_grid()
