import os
import sys
import json
import ctypes
import ctypes.wintypes
import subprocess
from pathlib import Path

from .constants import (
    SETTINGS_FILE,
    DEFAULT_LAUNCH_AS_ADMIN,
    BLOCKED_PATHS,
    FULLSCREEN_COVERAGE_RATIO,
    EXCLUDED_STEAM_APPIDS,
    EXCLUDED_STEAM_NAMES,
    NON_GAME_EXE_NAMES,
    KNOWN_GAME_EXE_NAMES,
    IDLE_RESUME_SECONDS,
)
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_INFORMATION = 0x0200
IDLE_PRIORITY_CLASS = 0x00000040
NORMAL_PRIORITY_CLASS = 0x00000020
PROCESS_MODE_BACKGROUND_BEGIN = 0x00100000
PROCESS_MODE_BACKGROUND_END = 0x00200000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.wintypes.DWORD),
        ("cntUsage", ctypes.wintypes.DWORD),
        ("th32ThreadID", ctypes.wintypes.DWORD),
        ("th32OwnerProcessID", ctypes.wintypes.DWORD),
        ("tpBasePri", ctypes.wintypes.LONG),
        ("tpDeltaPri", ctypes.wintypes.LONG),
        ("dwFlags", ctypes.wintypes.DWORD),
    ]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.wintypes.DWORD),
        ("cntUsage", ctypes.wintypes.DWORD),
        ("th32ProcessID", ctypes.wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", ctypes.wintypes.DWORD),
        ("cntThreads", ctypes.wintypes.DWORD),
        ("th32ParentProcessID", ctypes.wintypes.DWORD),
        ("pcPriClassBase", ctypes.wintypes.LONG),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szExeFile", ctypes.wintypes.WCHAR * 260),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.wintypes.LONG),
        ("top", ctypes.wintypes.LONG),
        ("right", ctypes.wintypes.LONG),
        ("bottom", ctypes.wintypes.LONG),
    ]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_as_admin():
    if os.name != "nt" or is_admin():
        return False

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        executable = sys.executable
        if executable.lower().endswith("python.exe"):
            pythonw_candidate = os.path.join(os.path.dirname(executable), "pythonw.exe")
            if os.path.exists(pythonw_candidate):
                executable = pythonw_candidate
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + sys.argv[1:])

    try:
                                                                                        
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, os.getcwd(), 1)
        return result > 32
    except Exception:
        return False


def should_launch_as_admin():
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_LAUNCH_AS_ADMIN

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        if isinstance(settings, dict):
            return bool(settings.get("launch_as_admin", DEFAULT_LAUNCH_AS_ADMIN))
    except Exception:
        pass

    return DEFAULT_LAUNCH_AS_ADMIN


def is_excluded_steam_game(appid, name):
    return (
        str(appid or "").strip() in EXCLUDED_STEAM_APPIDS
        or str(name or "").strip().lower() in EXCLUDED_STEAM_NAMES
    )


def safe_path(path):
    path = os.path.abspath(path)

    if not os.path.exists(path):
        return False, "Path does not exist."

    if not os.path.isdir(path):
        return False, "Path is not a folder."

    for blocked in BLOCKED_PATHS:
        if blocked and os.path.abspath(path).lower() == os.path.abspath(blocked).lower():
            return False, "Blocked dangerous system folder."

    if len(Path(path).parts) <= 2:
        return False, "Refusing to compress drive root."

    return True, "OK"


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
            try:
                rel = os.path.relpath(folder, root)
                depth = 0 if rel == "." else len(Path(rel).parts)
            except Exception:
                depth = max_depth + 1

            if depth >= max_depth:
                dirs[:] = []

            dirs[:] = [
                item for item in dirs
                if item.lower() not in {
                    "redist", "_commonredist", "directx", "dotnet", "vcredist",
                    "content", "movies", "soundtrack", "screenshots", "saved",
                }
            ]
            priority_dirs = {
                "binaries": 0,
                "win64": 1,
                "x64": 1,
                "game": 2,
                "bin": 3,
                "engine": 4,
            }
            dirs.sort(key=lambda item: (priority_dirs.get(item.lower(), 20), item.lower()))

            visited_entries += len(dirs) + len(files)
            if visited_entries > max_entries and not candidates:
                break

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


def normalize_windows_path(path):
    try:
        return os.path.abspath(str(path)).replace("/", "\\").lower()
    except Exception:
        return ""


def is_path_inside(child, parent):
    child = normalize_windows_path(child)
    parent = normalize_windows_path(parent)

    if not child or not parent:
        return False

    try:
        return os.path.commonpath([child, parent]).lower() == parent.lower()
    except Exception:
        return child.startswith(parent.rstrip("\\") + "\\")


def get_idle_seconds():
    if os.name != "nt":
        return 0

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)

        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0

        tick = kernel32.GetTickCount()
        elapsed_ms = int(tick - info.dwTime) & 0xFFFFFFFF
        return max(0, elapsed_ms / 1000.0)
    except Exception:
        return 0


def get_process_image_path(pid):
    if os.name != "nt" or not pid:
        return ""

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    OpenProcess.restype = ctypes.wintypes.HANDLE

    QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
    QueryFullProcessImageNameW.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.LPWSTR,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    CloseHandle.restype = ctypes.wintypes.BOOL

    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.wintypes.DWORD(len(buffer))
        if QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
    except Exception:
        pass
    finally:
        CloseHandle(handle)

    return ""


def get_window_title(hwnd):
    if os.name != "nt" or not hwnd:
        return ""

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value
    except Exception:
        return ""


def is_foreground_window_fullscreen(hwnd):
    if os.name != "nt" or not hwnd:
        return False

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False

        window_w = max(0, rect.right - rect.left)
        window_h = max(0, rect.bottom - rect.top)
        if window_w <= 0 or window_h <= 0:
            return False

        monitor = user32.MonitorFromWindow(hwnd, 2)

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.wintypes.DWORD),
            ]

        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)

        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
        else:
            screen_w = max(1, info.rcMonitor.right - info.rcMonitor.left)
            screen_h = max(1, info.rcMonitor.bottom - info.rcMonitor.top)

        return (window_w * window_h) >= int((screen_w * screen_h) * FULLSCREEN_COVERAGE_RATIO)
    except Exception:
        return False


def get_foreground_process_info():
    if os.name != "nt":
        return {"pid": 0, "path": "", "exe": "", "title": "", "fullscreen": False}

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        GetForegroundWindow = user32.GetForegroundWindow
        GetForegroundWindow.restype = ctypes.wintypes.HWND

        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
        GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD

        hwnd = GetForegroundWindow()
        if not hwnd:
            return {"pid": 0, "path": "", "exe": "", "title": "", "fullscreen": False}

        pid = ctypes.wintypes.DWORD(0)
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return {"pid": 0, "path": "", "exe": "", "title": "", "fullscreen": False}

        path = get_process_image_path(pid.value)
        return {
            "pid": int(pid.value),
            "path": path,
            "exe": os.path.basename(path).lower(),
            "title": get_window_title(hwnd),
            "fullscreen": is_foreground_window_fullscreen(hwnd),
        }
    except Exception:
        return {"pid": 0, "path": "", "exe": "", "title": "", "fullscreen": False}


def build_game_detection_roots(game_paths):
    roots = []

    for path in game_paths or []:
        if path and os.path.isdir(path):
            roots.append(os.path.abspath(path))

    try:
        from .steam import find_steam_libraries
        libraries, _ = find_steam_libraries()
        for steamapps in libraries:
            common = os.path.join(steamapps, "common")
            if os.path.isdir(common):
                roots.append(common)
    except Exception:
        pass

    clean = []
    seen = set()
    for root in roots:
        normalized = normalize_windows_path(root)
        if normalized and normalized not in seen:
            seen.add(normalized)
            clean.append(root)

    return clean


def detect_game_activity(game_roots):
    info = get_foreground_process_info()
    idle_seconds = get_idle_seconds()
    path = info.get("path", "")
    exe = info.get("exe", "")
    title = info.get("title", "")
    fullscreen = bool(info.get("fullscreen", False))

    if not path or not exe:
        return False, "", idle_seconds, "No foreground executable"

    if info.get("pid") == os.getpid():
        return False, "", idle_seconds, "Compressor is foreground"

    if exe in NON_GAME_EXE_NAMES:
        return False, "", idle_seconds, "Foreground app is not a game"

    path_norm = normalize_windows_path(path)
    inside_game_root = any(is_path_inside(path, root) for root in game_roots)
    inside_steam_common = "\\steamapps\\common\\" in path_norm
    known_game_exe = exe in KNOWN_GAME_EXE_NAMES
    is_game_like = inside_game_root or inside_steam_common or known_game_exe

    if not is_game_like:
        return False, "", idle_seconds, "Foreground app is not recognized as a game"

    display_name = title.strip() or os.path.basename(path)

    if idle_seconds >= IDLE_RESUME_SECONDS:
        return False, display_name, idle_seconds, "PC idle, compression allowed"

    if fullscreen or inside_game_root or inside_steam_common or known_game_exe:
        return True, display_name, idle_seconds, "Game is active"

    return False, display_name, idle_seconds, "Game not active enough to pause"


def get_process_tree_pids(root_pid):
    if os.name != "nt" or not root_pid:
        return [int(root_pid)] if root_pid else []

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
    CreateToolhelp32Snapshot.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
    CreateToolhelp32Snapshot.restype = ctypes.wintypes.HANDLE

    Process32First = kernel32.Process32FirstW
    Process32First.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    Process32First.restype = ctypes.wintypes.BOOL

    Process32Next = kernel32.Process32NextW
    Process32Next.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    Process32Next.restype = ctypes.wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    CloseHandle.restype = ctypes.wintypes.BOOL

    root_pid = int(root_pid)
    children_by_parent = {}
    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return [root_pid]

    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        has_process = Process32First(snapshot, ctypes.byref(entry))

        while has_process:
            pid = int(entry.th32ProcessID)
            parent = int(entry.th32ParentProcessID)
            children_by_parent.setdefault(parent, []).append(pid)
            has_process = Process32Next(snapshot, ctypes.byref(entry))
    finally:
        CloseHandle(snapshot)

    tree = []
    pending = [root_pid]
    seen = set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        tree.append(pid)
        pending.extend(children_by_parent.get(pid, []))

    return tree


def _open_process_for_control(pid):
    if os.name != "nt" or not pid:
        return None, None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    OpenProcess.restype = ctypes.wintypes.HANDLE

    access = PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION
    handle = OpenProcess(access, False, int(pid))
    return kernel32, handle


def throttle_process_for_pause(pid):
    kernel32, handle = _open_process_for_control(pid)
    if not kernel32 or not handle:
        return None

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    CloseHandle.restype = ctypes.wintypes.BOOL

    GetPriorityClass = kernel32.GetPriorityClass
    GetPriorityClass.argtypes = [ctypes.wintypes.HANDLE]
    GetPriorityClass.restype = ctypes.wintypes.DWORD

    SetPriorityClass = kernel32.SetPriorityClass
    SetPriorityClass.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
    SetPriorityClass.restype = ctypes.wintypes.BOOL

    GetProcessAffinityMask = kernel32.GetProcessAffinityMask
    GetProcessAffinityMask.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    GetProcessAffinityMask.restype = ctypes.wintypes.BOOL

    SetProcessAffinityMask = kernel32.SetProcessAffinityMask
    SetProcessAffinityMask.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_size_t]
    SetProcessAffinityMask.restype = ctypes.wintypes.BOOL

    state = {"pid": int(pid), "priority": 0, "affinity": 0}
    try:
        state["priority"] = int(GetPriorityClass(handle) or 0)

        process_mask = ctypes.c_size_t(0)
        system_mask = ctypes.c_size_t(0)
        if GetProcessAffinityMask(handle, ctypes.byref(process_mask), ctypes.byref(system_mask)):
            state["affinity"] = int(process_mask.value or 0)
            allowed = int(process_mask.value or system_mask.value or 0)
            if allowed:
                lowest_cpu = allowed & -allowed
                SetProcessAffinityMask(handle, ctypes.c_size_t(lowest_cpu))

        if not SetPriorityClass(handle, PROCESS_MODE_BACKGROUND_BEGIN):
            SetPriorityClass(handle, IDLE_PRIORITY_CLASS)
        return state
    except Exception:
        return state
    finally:
        CloseHandle(handle)


def restore_process_after_pause(pid, state=None):
    kernel32, handle = _open_process_for_control(pid)
    if not kernel32 or not handle:
        return False

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    CloseHandle.restype = ctypes.wintypes.BOOL

    SetPriorityClass = kernel32.SetPriorityClass
    SetPriorityClass.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
    SetPriorityClass.restype = ctypes.wintypes.BOOL

    SetProcessAffinityMask = kernel32.SetProcessAffinityMask
    SetProcessAffinityMask.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_size_t]
    SetProcessAffinityMask.restype = ctypes.wintypes.BOOL

    restored = False
    try:
        state = state or {}
        affinity = int(state.get("affinity", 0) or 0)
        if affinity:
            restored = bool(SetProcessAffinityMask(handle, ctypes.c_size_t(affinity))) or restored

        SetPriorityClass(handle, PROCESS_MODE_BACKGROUND_END)
        priority = int(state.get("priority", 0) or 0) or NORMAL_PRIORITY_CLASS
        restored = bool(SetPriorityClass(handle, priority)) or restored
    except Exception:
        pass
    finally:
        CloseHandle(handle)

    return restored


def suspend_process_threads(pid):
    if os.name != "nt" or not pid:
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
    CreateToolhelp32Snapshot.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
    CreateToolhelp32Snapshot.restype = ctypes.wintypes.HANDLE

    Thread32First = kernel32.Thread32First
    Thread32First.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    Thread32First.restype = ctypes.wintypes.BOOL

    Thread32Next = kernel32.Thread32Next
    Thread32Next.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    Thread32Next.restype = ctypes.wintypes.BOOL

    OpenThread = kernel32.OpenThread
    OpenThread.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    OpenThread.restype = ctypes.wintypes.HANDLE

    SuspendThread = kernel32.SuspendThread
    SuspendThread.argtypes = [ctypes.wintypes.HANDLE]
    SuspendThread.restype = ctypes.wintypes.DWORD

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    CloseHandle.restype = ctypes.wintypes.BOOL

    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return False

    suspended_any = False
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(THREADENTRY32)
        has_thread = Thread32First(snapshot, ctypes.byref(entry))

        while has_thread:
            if int(entry.th32OwnerProcessID) == int(pid):
                thread_handle = OpenThread(THREAD_SUSPEND_RESUME, False, int(entry.th32ThreadID))
                if thread_handle:
                    try:
                        result = SuspendThread(thread_handle)
                        if result != 0xFFFFFFFF:
                            suspended_any = True
                    finally:
                        CloseHandle(thread_handle)
            has_thread = Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        CloseHandle(snapshot)

    return suspended_any


def suspend_process_tree(pid):
    suspended = set()
    for tree_pid in get_process_tree_pids(pid):
        if suspend_process_threads(tree_pid):
            suspended.add(int(tree_pid))
    return suspended


def resume_process_threads(pid):
    if os.name != "nt" or not pid:
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
    CreateToolhelp32Snapshot.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
    CreateToolhelp32Snapshot.restype = ctypes.wintypes.HANDLE

    Thread32First = kernel32.Thread32First
    Thread32First.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    Thread32First.restype = ctypes.wintypes.BOOL

    Thread32Next = kernel32.Thread32Next
    Thread32Next.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    Thread32Next.restype = ctypes.wintypes.BOOL

    OpenThread = kernel32.OpenThread
    OpenThread.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    OpenThread.restype = ctypes.wintypes.HANDLE

    ResumeThread = kernel32.ResumeThread
    ResumeThread.argtypes = [ctypes.wintypes.HANDLE]
    ResumeThread.restype = ctypes.wintypes.DWORD

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    CloseHandle.restype = ctypes.wintypes.BOOL

    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return False

    resumed_any = False
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(THREADENTRY32)
        has_thread = Thread32First(snapshot, ctypes.byref(entry))

        while has_thread:
            if int(entry.th32OwnerProcessID) == int(pid):
                thread_handle = OpenThread(THREAD_SUSPEND_RESUME, False, int(entry.th32ThreadID))
                if thread_handle:
                    try:
                        for _ in range(32):
                            result = ResumeThread(thread_handle)
                            if result == 0xFFFFFFFF:
                                break
                            resumed_any = True
                            if result <= 1:
                                break
                    finally:
                        CloseHandle(thread_handle)
            has_thread = Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        CloseHandle(snapshot)

    return resumed_any


def resume_process_tree(pid):
    resumed = set()
    for tree_pid in reversed(get_process_tree_pids(pid)):
        if resume_process_threads(tree_pid):
            resumed.add(int(tree_pid))
    return resumed

