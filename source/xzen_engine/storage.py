import os
import time
import ctypes
import ctypes.wintypes
import subprocess
def scan_manual_folder_size(path, progress_callback=None, max_seconds=300):
    total = 0
    file_count = 0
    start = time.time()
    last_emit = time.time()
    visited = set()
    stack = [path]

    while stack:
        if time.time() - start > max_seconds:
            break

        folder = stack.pop()
        try:
            real = os.path.realpath(folder).lower()
            if real in visited:
                continue
            visited.add(real)

            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            file_count += 1
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except Exception:
                        pass

                    now = time.time()
                    if progress_callback and now - last_emit >= 0.2:
                        progress_callback(total, file_count)
                        last_emit = now
        except Exception:
            pass

    if progress_callback:
        progress_callback(total, file_count)

    return total, file_count


def get_file_size_on_disk(path):
    try:
        logical_size = os.path.getsize(path)
    except Exception:
        logical_size = 0

    if os.name != "nt":
        return logical_size

    try:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith("\\\\?\\"):
            if abs_path.startswith("\\\\"):
                win_path = "\\\\?\\UNC\\" + abs_path[2:]
            else:
                win_path = "\\\\?\\" + abs_path
        else:
            win_path = abs_path

        high = ctypes.wintypes.DWORD(0)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCompressedFileSizeW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.POINTER(ctypes.wintypes.DWORD)]
        kernel32.GetCompressedFileSizeW.restype = ctypes.wintypes.DWORD
        ctypes.set_last_error(0)
        low = kernel32.GetCompressedFileSizeW(win_path, ctypes.byref(high))
        last_error = ctypes.get_last_error()

        if low == 0xFFFFFFFF and last_error != 0:
            return logical_size

        disk_size = (high.value << 32) + low
        if disk_size <= 0 and logical_size > 0:
            return logical_size
        return disk_size
    except Exception:
        return logical_size


def get_drive_cluster_size(path):
    if os.name != "nt":
        return 4096

    try:
        abs_path = os.path.abspath(path)
        drive = os.path.splitdrive(abs_path)[0] + "\\"
        sectors_per_cluster = ctypes.wintypes.DWORD(0)
        bytes_per_sector = ctypes.wintypes.DWORD(0)
        free_clusters = ctypes.wintypes.DWORD(0)
        total_clusters = ctypes.wintypes.DWORD(0)

        ok = ctypes.windll.kernel32.GetDiskFreeSpaceW(
            drive,
            ctypes.byref(sectors_per_cluster),
            ctypes.byref(bytes_per_sector),
            ctypes.byref(free_clusters),
            ctypes.byref(total_clusters),
        )
        if ok:
            return max(1, sectors_per_cluster.value * bytes_per_sector.value)
    except Exception:
        pass

    return 4096


FILE_ATTRIBUTE_COMPRESSED = 0x800


def has_compressed_attribute(path):
    if os.name != "nt":
        return False

    try:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith("\\\\?\\"):
            if abs_path.startswith("\\\\"):
                win_path = "\\\\?\\UNC\\" + abs_path[2:]
            else:
                win_path = "\\\\?\\" + abs_path
        else:
            win_path = abs_path

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetFileAttributesW.argtypes = [ctypes.wintypes.LPCWSTR]
        kernel32.GetFileAttributesW.restype = ctypes.wintypes.DWORD
        attrs = kernel32.GetFileAttributesW(win_path)
        if attrs == 0xFFFFFFFF:
            return False
        return bool(attrs & FILE_ATTRIBUTE_COMPRESSED)
    except Exception:
        return False


def scan_compressed_attribute_count(path, progress_callback=None, cancel_check=None):
    compressed_count = 0
    total_count = 0
    last_emit = time.time()

    for folder, _, files in os.walk(path):
        if cancel_check and cancel_check():
            break

        for name in files:
            if cancel_check and cancel_check():
                break

            file_path = os.path.join(folder, name)
            total_count += 1
            if has_compressed_attribute(file_path):
                compressed_count += 1

            now = time.time()
            if progress_callback and now - last_emit >= 0.2:
                progress_callback(compressed_count, total_count)
                last_emit = now

    if progress_callback:
        progress_callback(compressed_count, total_count)

    return compressed_count, total_count


def run_compact_process(args, process_list, process_lock, log_callback=None, cancel_check=None, cwd=None):
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
        encoding="utf-8",
        errors="ignore",
        creationflags=creationflags,
        cwd=cwd,
    )

    with process_lock:
        process_list.append(process)

    output_lines = []
    try:
        while True:
            if cancel_check and cancel_check() and process.poll() is None:
                try:
                    taskkill_flags = 0
                    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                        taskkill_flags = subprocess.CREATE_NO_WINDOW
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        check=False,
                        creationflags=taskkill_flags,
                    )
                except Exception:
                    pass
                break

            line = process.stdout.readline() if process.stdout else ""
            if line:
                clean = line.rstrip()
                output_lines.append(clean)
                if log_callback and clean:
                    log_callback(clean)
                continue

            if process.poll() is not None:
                break
            time.sleep(0.1)

        remainder = process.stdout.read() if process.stdout else ""
        if remainder:
            for line in remainder.splitlines():
                clean = line.rstrip()
                output_lines.append(clean)
                if log_callback and clean:
                    log_callback(clean)

        returncode = process.wait()
        return returncode, "\n".join(output_lines)
    finally:
        with process_lock:
            if process in process_list:
                process_list.remove(process)

def estimate_folder_allocated_size(path):
    total = 0
    file_count = 0
    cluster_size = get_drive_cluster_size(path)

    for folder, _, files in os.walk(path):
        for name in files:
            try:
                logical_size = os.path.getsize(os.path.join(folder, name))
                if logical_size > 0:
                    total += ((logical_size + cluster_size - 1) // cluster_size) * cluster_size
                file_count += 1
            except Exception:
                pass

    return total, file_count


def scan_folder_size_on_disk(path, progress_callback=None, cancel_check=None):
    total = 0
    file_count = 0
    last_emit = time.time()

    for folder, _, files in os.walk(path):
        if cancel_check and cancel_check():
            break

        for name in files:
            if cancel_check and cancel_check():
                break

            file_path = os.path.join(folder, name)
            total += get_file_size_on_disk(file_path)
            file_count += 1

            now = time.time()
            if progress_callback and now - last_emit >= 0.2:
                progress_callback(total, file_count)
                last_emit = now

    if progress_callback:
        progress_callback(total, file_count)

    return total, file_count

