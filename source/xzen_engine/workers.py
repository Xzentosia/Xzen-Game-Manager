import os
import time
import subprocess
import threading
import concurrent.futures

from PyQt5.QtCore import QThread, pyqtSignal

from .constants import (
    POSTER_DOWNLOAD_WORKERS,
    DEFAULT_WORKER_MODE,
    DEFAULT_WORKER_COUNT,
    AUTO_PAUSE_WHEN_GAME_RUNNING,
    GAME_DETECT_CHECK_SECONDS,
    IDLE_RESUME_SECONDS,
    MAX_SPEED_CHUNK_SIZE,
    MAX_SPEED_CHUNK_BYTES,
    HUGE_FILE_SEQUENTIAL_BYTES,
    HUGE_FILE_WARNING_BYTES,
    compression_algorithm_compact_value,
    normalized_worker_mode,
    normalized_worker_count,
    resolve_worker_count,
)
from .formatting import (
    format_game_size,
    format_elapsed,
    global_progress_text,
    drive_space_progress_text,
    get_drive_free_bytes,
)
from .posters import get_poster_for_game, is_portrait_poster_file
from .steam import get_steam_path, get_steam_manifest_size
from .stores import scan_all_store_games
from .storage import (
    scan_manual_folder_size,
    scan_compressed_attribute_count,
    run_compact_process,
    scan_folder_size_on_disk,
    estimate_folder_allocated_size,
)
from .system import (
    build_game_detection_roots,
    detect_game_activity,
    get_process_tree_pids,
    throttle_process_for_pause,
    restore_process_after_pause,
    suspend_process_tree,
    resume_process_tree,
)
class PosterFetchWorker(QThread):
    poster_done = pyqtSignal(int, str, str)
    log = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, games):
        super().__init__()
        self.games = [dict(game) for game in games]
        self.cancel_requested = False

    def cancel(self):
        self.cancel_requested = True

    def fetch_one(self, index, game, steam_path):
        poster_key = game.get("appid") or game.get("path", "") or str(index)
        if self.cancel_requested:
            return index, poster_key, ""

        appid = game.get("appid", "")
        name = game.get("name", "Unknown")

        self.log.emit(f"Fetching best poster: {name}")
        poster = get_poster_for_game(steam_path, appid, name, game.get("source", ""))
        if poster and os.path.exists(poster):
            return index, poster_key, poster

        return index, poster_key, ""

    def run(self):
        steam_path = get_steam_path()
        jobs = []

        for index, game in enumerate(self.games):
            if not game.get("name"):
                continue

            old_poster = game.get("poster", "")
            if old_poster and os.path.exists(old_poster) and is_portrait_poster_file(old_poster):
                continue

            jobs.append((index, game))

        if not jobs:
            self.log.emit("No missing game posters to fetch.")
            self.finished_all.emit()
            return

        worker_count = min(POSTER_DOWNLOAD_WORKERS, max(1, len(jobs)))
        self.log.emit(f"Poster fetch started in parallel with {worker_count} worker(s)...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(self.fetch_one, index, game, steam_path) for index, game in jobs]
            for future in concurrent.futures.as_completed(futures):
                if self.cancel_requested:
                    break

                try:
                    index, appid, poster = future.result()
                except Exception as e:
                    self.log.emit(f"Poster fetch failed: {e}")
                    continue

                name = "Unknown"
                if 0 <= index < len(self.games):
                    name = self.games[index].get("name", "Unknown")

                if poster:
                    self.poster_done.emit(index, appid, poster)
                    self.log.emit(f"Best poster ready: {name}")
                else:
                    self.poster_done.emit(index, appid, "")
                    self.log.emit(f"No poster found: {name}")

        self.log.emit("Poster fetch finished.")
        self.finished_all.emit()


class StoreScanWorker(QThread):
    scan_done = pyqtSignal(object)
    log = pyqtSignal(str)

    def run(self):
        self.log.emit("Auto-scanning installed games from stores...")
        try:
            self.scan_done.emit(scan_all_store_games())
        except Exception as e:
            self.log.emit(f"Store scan failed: {e}")
            self.scan_done.emit([])


class SizeScanWorker(QThread):
    game_started = pyqtSignal(int, str, int, int)
    size_progress = pyqtSignal(int, int, object, int)
    size_done = pyqtSignal(int, object, int, str)
    log = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, games):
        super().__init__()
        self.games = [dict(game) for game in games]

    def run(self):
        total_games = len(self.games)
        self.log.emit("Size scan started...")

        for index, game in enumerate(self.games):
            name = game.get("name", "Unknown")
            source = game.get("source", "")

            self.game_started.emit(index, name, index + 1, total_games)

            if source == "Steam":
                manifest_size = get_steam_manifest_size(game.get("appid", ""))
                if manifest_size <= 0:
                    manifest_size = int(game.get("manifest_size", 0) or 0)

            else:
                manifest_size = 0

            if source == "Steam" and manifest_size > 0:
                self.log.emit(f"Using Steam installed manifest size for {name}: {format_game_size(manifest_size)}")
                self.size_done.emit(index, manifest_size, 0, "Steam manifest")
                continue

            path = game.get("path", "")
            if not os.path.isdir(path):
                self.size_done.emit(index, 0, 0, "Missing folder")
                continue

            def progress_callback(current_size, file_count):
                self.size_progress.emit(index, 50, current_size, file_count)

            size, file_count = scan_manual_folder_size(path, progress_callback)
            self.size_done.emit(index, size, file_count, "Folder scan")

        self.log.emit("Size scan finished.")
        self.finished_all.emit()


class CompactWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, str, int, int)
    active_files = pyqtSignal(int, str, object)
    worker_usage = pyqtSignal(int, int)
    pause_state = pyqtSignal(bool, str, str)
    done = pyqtSignal(bool, bool, object, int)

    def __init__(
        self,
        target_path,
        action_label,
        compression_algorithm,
        worker_mode=DEFAULT_WORKER_MODE,
        worker_count=DEFAULT_WORKER_COUNT,
        game_paths=None,
        auto_pause_when_game_running=AUTO_PAUSE_WHEN_GAME_RUNNING,
        file_order="large_first",
    ):
        super().__init__()
        self.target_path = target_path
        self.action_label = action_label
        self.compression_algorithm = compression_algorithm
        self.worker_mode = normalized_worker_mode(worker_mode)
        self.worker_count = normalized_worker_count(worker_count)
        self.cpu_workers = max(1, os.cpu_count() or 1)
        self.max_workers = resolve_worker_count(self.worker_mode, self.worker_count)

        self.processes = []
        self.process_lock = threading.Lock()
        self.active_lock = threading.Lock()
        self.cancel_lock = threading.Lock()
        self.active_chunks = {}

        self.cancel_requested = False
        self.cancel_kill_started = False
        self.task_start_time = time.time()
        self.cancel_cleanup_requested = False

        self.auto_pause_when_game_running = bool(auto_pause_when_game_running)
        self.game_roots = build_game_detection_roots(game_paths or [])
        self.file_order = str(file_order or "large_first")

        self.pause_lock = threading.Lock()
        self.pause_active = False
        self.manual_pause_requested = False
        self.pause_game_name = ""
        self.pause_reason = ""
        self.pause_idle_seconds = 0
        self.suspended_pids = set()
        self.paused_process_states = {}
        self.last_game_check = 0

    def get_active_processes(self):
        with self.process_lock:
            return [process for process in self.processes if process and process.poll() is None]

    def active_worker_count(self):
        if self.pause_active:
            return 0
        process_count = len(self.get_active_processes())
        with self.active_lock:
            chunk_count = len(self.active_chunks)
        return max(process_count, chunk_count)

    def emit_worker_usage(self):
        self.worker_usage.emit(self.active_worker_count(), self.max_workers)

    def emit_pause_state(self, paused, game_name="", reason=""):
        self.pause_state.emit(bool(paused), str(game_name or ""), str(reason or ""))

    def suspend_active_compact_processes(self):
        suspended = 0
        for process in self.get_active_processes():
            pid = int(process.pid)
            for tree_pid in get_process_tree_pids(pid):
                tree_pid = int(tree_pid)
                if tree_pid not in self.paused_process_states:
                    self.paused_process_states[tree_pid] = throttle_process_for_pause(tree_pid) or {}
            tree_pids = suspend_process_tree(pid)
            new_pids = {int(item) for item in tree_pids if int(item) not in self.suspended_pids}
            if new_pids:
                self.suspended_pids.update(new_pids)
                suspended += len(new_pids)
        return suspended

    def resume_suspended_compact_processes(self):
        resumed = 0
        for pid in list(self.suspended_pids):
            resumed_pids = resume_process_tree(pid)
            if resumed_pids:
                resumed += len(resumed_pids)
                self.suspended_pids.difference_update(int(item) for item in resumed_pids)
            self.suspended_pids.discard(pid)
        for pid, state in list(self.paused_process_states.items()):
            restore_process_after_pause(pid, state)
            self.paused_process_states.pop(pid, None)
        return resumed

    def check_auto_pause_for_game(self, force=False):
        if self.manual_pause_requested:
            with self.pause_lock:
                suspended_count = self.suspend_active_compact_processes()
                if not self.pause_active:
                    self.pause_active = True
                    self.pause_reason = "Manual pause"
                    self.pause_game_name = "manual pause"
                    self.emit_pause_state(True, self.pause_game_name, self.pause_reason)
                    self.emit_worker_usage()
                    self.log.emit(f"{self.action_label} manually paused.")
                elif suspended_count:
                    self.emit_pause_state(True, self.pause_game_name, self.pause_reason)
                    self.emit_worker_usage()
                    self.log.emit("Paused another compact worker because manual pause is active.")
            return True

        if not self.auto_pause_when_game_running or os.name != "nt":
            return False

        now = time.time()
        if not force and now - self.last_game_check < GAME_DETECT_CHECK_SECONDS:
            return self.pause_active

        self.last_game_check = now

        with self.pause_lock:
            game_active, game_name, idle_seconds, reason = detect_game_activity(self.game_roots)
            self.pause_idle_seconds = idle_seconds
            self.pause_reason = reason

            if game_active:
                self.pause_game_name = game_name or "game"
                suspended_count = self.suspend_active_compact_processes()
                if not self.pause_active:
                    self.pause_active = True
                    self.emit_pause_state(True, self.pause_game_name, reason)
                    self.emit_worker_usage()
                    self.log.emit(f"Gaming detected: {self.pause_game_name}. compact.exe paused.")
                elif suspended_count:
                    self.emit_pause_state(True, self.pause_game_name, reason)
                    self.emit_worker_usage()
                    self.log.emit(f"Paused another compact.exe worker because gaming is active: {self.pause_game_name}")
                return True

            if self.pause_active:
                resumed_count = self.resume_suspended_compact_processes()
                self.log.emit(f"{self.action_label} resumed. Reason: {reason}. Resumed {resumed_count} compact.exe process(es).")

            self.pause_active = False
            if reason == "PC idle, compression allowed":
                self.pause_game_name = game_name or "idle"
            else:
                self.pause_game_name = ""
            self.emit_pause_state(False, self.pause_game_name, reason)
            self.emit_worker_usage()

        return False

    def set_manual_pause(self, paused):
        self.manual_pause_requested = bool(paused)

        if self.manual_pause_requested:
            self.check_auto_pause_for_game(force=True)
            return

        with self.pause_lock:
            if self.pause_active and self.pause_reason == "Manual pause":
                resumed_count = self.resume_suspended_compact_processes()
                self.pause_active = False
                self.pause_game_name = ""
                self.pause_reason = "Manual pause released"
                self.emit_pause_state(False, "", self.pause_reason)
                self.emit_worker_usage()
                self.log.emit(f"{self.action_label} manually resumed. Resumed {resumed_count} compact process(es).")

    def wait_if_game_active_before_starting_chunk(self):
        while not self.cancel_requested:
            if not self.check_auto_pause_for_game(force=True):
                return
            time.sleep(0.5)

    def cancel(self, cleanup_decompress=False):
        self.cancel_requested = True
        self.cancel_cleanup_requested = bool(cleanup_decompress)

        with self.cancel_lock:
            if self.cancel_kill_started:
                return
            self.cancel_kill_started = True

        threading.Thread(
            target=self.kill_compact_processes_for_cancel,
            name="xzen-compact-cancel",
            daemon=True,
        ).start()

    def kill_compact_processes_for_cancel(self):
        with self.process_lock:
            processes = list(self.processes)

                                                                                  
                                                                                     
                              
        for process in processes:
            if process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass

        taskkill_flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            taskkill_flags = subprocess.CREATE_NO_WINDOW

        if os.name == "nt":
            try:
                subprocess.Popen(
                    ["taskkill", "/F", "/T", "/IM", "compact.exe"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    shell=False,
                    creationflags=taskkill_flags,
                )
                self.log.emit("Cancel requested: killing compact.exe now.")
            except Exception as e:
                self.log.emit(f"Cancel failed to launch compact.exe kill: {e}")

        for process in processes:
            if process.poll() is not None:
                continue

            try:
                subprocess.Popen(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    shell=False,
                    creationflags=taskkill_flags,
                )
            except Exception as e:
                self.log.emit(f"Cancel failed: {e}")

        self.suspended_pids.clear()
        self.paused_process_states.clear()

    def emit_global_progress(self, percent, status, processed_files, total_files, allow_eta=True):
        self.progress.emit(
            percent,
            global_progress_text(status, percent, self.task_start_time, allow_eta),
            processed_files,
            total_files,
        )

    def decompress_status_text(self, start_free=None):
        lines = ["Decompressing"]
        space_line = drive_space_progress_text(self.target_path, start_free)
        if space_line:
            lines.append(space_line)
        return "\n".join(lines)

    def emit_decompress_progress(self, percent, processed_files, total_files, start_free=None, allow_eta=True):
        self.progress.emit(
            percent,
            global_progress_text(
                self.decompress_status_text(start_free),
                percent,
                self.task_start_time,
                allow_eta,
            ),
            processed_files,
            total_files,
        )

    def active_summary(self):
        with self.active_lock:
            active = dict(self.active_chunks)

        active_bytes = 0
        active_biggest = 0
        active_count = 0
        active_file_name = ""
        active_elapsed = 0
        huge_active = False
        normal_active = False

        for _, meta in active.items():
            files = meta.get("files", [])
            started_at = float(meta.get("started_at", time.time()))
            lane = meta.get("lane", "normal")
            active_elapsed = max(active_elapsed, time.time() - started_at)
            active_count += 1

            if lane == "huge":
                huge_active = True
            else:
                normal_active = True

            for file_path, file_size in files:
                file_size = int(file_size or 0)
                active_bytes += file_size
                if file_size > active_biggest:
                    active_biggest = file_size
                    active_file_name = os.path.basename(file_path)

        return {
            "count": active_count,
            "bytes": active_bytes,
            "biggest": active_biggest,
            "file_name": active_file_name,
            "elapsed": active_elapsed,
            "huge_active": huge_active,
            "normal_active": normal_active,
        }

    def collect_files(self):
        files = []
        for folder, _, names in os.walk(self.target_path):
            if self.cancel_requested:
                break
            for name in names:
                if self.cancel_requested:
                    break
                file_path = os.path.join(folder, name)
                try:
                    size = os.path.getsize(file_path)
                except Exception:
                    size = 0
                files.append((file_path, size))
        if self.file_order == "balanced_small_first":
            files = self.balanced_small_first_files(files)
        else:
            files.sort(key=lambda item: item[1], reverse=True)
        return files

    def balanced_small_first_files(self, files):
        small = sorted(
            [item for item in files if item[1] < HUGE_FILE_SEQUENTIAL_BYTES],
            key=lambda item: item[1],
        )
        huge = sorted(
            [item for item in files if item[1] >= HUGE_FILE_SEQUENTIAL_BYTES],
            key=lambda item: item[1],
        )

        if not huge:
            return small

        ordered = []
        small_batch = 10
        while small or huge:
            for _ in range(small_batch):
                if small:
                    ordered.append(small.pop(0))
            if huge:
                ordered.append(huge.pop(0))

        return ordered

    def rebalance_normal_chunks(self, normal_chunks, target_count, max_items=MAX_SPEED_CHUNK_SIZE, max_chars=24000):
        normal_files = [item for chunk in normal_chunks for item in chunk]
        if not normal_files:
            return normal_chunks

        target_count = max(1, min(int(target_count or 1), len(normal_files)))
        if len(normal_chunks) >= target_count:
            return normal_chunks

        buckets = [{"files": [], "bytes": 0, "chars": 0} for _ in range(target_count)]
        for file_path, file_size in sorted(normal_files, key=lambda item: item[1], reverse=True):
            path_chars = len(file_path) + 3
            placed = False
            for bucket in sorted(buckets, key=lambda item: item["bytes"]):
                if bucket["files"] and (
                    len(bucket["files"]) >= max_items
                    or bucket["bytes"] + file_size > MAX_SPEED_CHUNK_BYTES
                    or bucket["chars"] + path_chars > max_chars
                ):
                    continue

                bucket["files"].append((file_path, file_size))
                bucket["bytes"] += file_size
                bucket["chars"] += path_chars
                placed = True
                break

            if not placed:
                buckets.append({
                    "files": [(file_path, file_size)],
                    "bytes": file_size,
                    "chars": path_chars,
                })

        return [bucket["files"] for bucket in buckets if bucket["files"]]

    def split_chunks(self, files, max_items=MAX_SPEED_CHUNK_SIZE, max_chars=24000):
        normal_chunks = []
        huge_chunks = []
        current = []
        current_bytes = 0
        current_chars = 0

        for file_path, file_size in files:
            path_chars = len(file_path) + 3

            if file_size >= HUGE_FILE_SEQUENTIAL_BYTES:
                if current:
                    normal_chunks.append(current)
                    current = []
                    current_bytes = 0
                    current_chars = 0
                huge_chunks.append([(file_path, file_size)])
                continue

            if current and (
                len(current) >= max_items
                or current_bytes + file_size > MAX_SPEED_CHUNK_BYTES
                or current_chars + path_chars > max_chars
            ):
                normal_chunks.append(current)
                current = []
                current_bytes = 0
                current_chars = 0

            current.append((file_path, file_size))
            current_bytes += file_size
            current_chars += path_chars

        if current:
            normal_chunks.append(current)

        target_normal_workers = self.max_workers
        if huge_chunks and self.max_workers > 1:
            target_normal_workers = self.max_workers - 1
        elif huge_chunks:
            target_normal_workers = 0

        if target_normal_workers > 0:
            normal_chunks = self.rebalance_normal_chunks(normal_chunks, target_normal_workers, max_items, max_chars)

        return normal_chunks, huge_chunks

    def compact_args(self, files):
        if self.action_label == "Compressing":
            compact_value = compression_algorithm_compact_value(self.compression_algorithm)
            return ["compact.exe", "/c", "/a", "/i", f"/exe:{compact_value}"] + files
        return ["compact.exe", "/u", "/a", "/i", "/f"] + files

    def compact_decompress_folder_args(self):
        return ["compact.exe", "/u", f"/s:{self.target_path}", "/i", "/f", "*"]

    def run_compact_chunk(self, chunk_id, files, lane="normal"):
        if self.cancel_requested:
            return False, 0, 0, ""

        self.wait_if_game_active_before_starting_chunk()
        if self.cancel_requested:
            return False, 0, 0, ""

        file_paths = [file_path for file_path, _ in files]
        chunk_bytes = sum(file_size for _, file_size in files)

        with self.active_lock:
            self.active_chunks[chunk_id] = {"files": files, "started_at": time.time(), "lane": lane}

        self.active_files.emit(chunk_id, "start", files)
        self.emit_worker_usage()
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        try:
            process = subprocess.Popen(
                self.compact_args(file_paths),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
                encoding="utf-8",
                errors="ignore",
                creationflags=creationflags,
            )
        except Exception:
            with self.active_lock:
                self.active_chunks.pop(chunk_id, None)
            self.active_files.emit(chunk_id, "done", files)
            self.emit_worker_usage()
            raise

        with self.process_lock:
            self.processes.append(process)

        if self.pause_active:
            for tree_pid in get_process_tree_pids(process.pid):
                tree_pid = int(tree_pid)
                if tree_pid not in self.paused_process_states:
                    self.paused_process_states[tree_pid] = throttle_process_for_pause(tree_pid) or {}
            self.suspended_pids.update(suspend_process_tree(process.pid))
            self.emit_worker_usage()

        output = ""
        try:
            output, _ = process.communicate()
        finally:
            with self.process_lock:
                if process in self.processes:
                    self.processes.remove(process)
            with self.active_lock:
                self.active_chunks.pop(chunk_id, None)
            self.emit_worker_usage()

            self.suspended_pids.discard(int(process.pid))
            self.active_files.emit(chunk_id, "done", files)

        if self.cancel_requested:
            return False, 0, 0, output

        return process.returncode == 0, len(files), chunk_bytes, output

    def run_forced_recursive_decompress(self, total_files, total_bytes):
        start_free = get_drive_free_bytes(self.target_path)
        self.emit_decompress_progress(1, 0, total_files, start_free)

        def before_progress(compressed_count, scanned_count):
            percent = 1
            if total_files:
                percent = 1 + min(8, int((scanned_count / total_files) * 8))
            self.emit_decompress_progress(percent, scanned_count, total_files, start_free)

        before_compressed, before_total = scan_compressed_attribute_count(
            self.target_path,
            before_progress,
            lambda: self.cancel_requested,
        )

        if self.cancel_requested:
            return False, True, 0, 0

        self.log.emit(f"Compressed files before decompression: {before_compressed}/{before_total}")

        self.emit_decompress_progress(10, 0, total_files, start_free, False)

        with self.active_lock:
            self.active_chunks[1] = {
                "files": [(self.target_path, total_bytes)],
                "started_at": time.time(),
                "lane": "huge",
            }
        self.active_files.emit(1, "start", [(self.target_path, total_bytes)])
        self.emit_worker_usage()

        monitor_stop = threading.Event()

        def monitor_drive_space():
            while not monitor_stop.wait(0.5):
                if self.cancel_requested:
                    break
                self.emit_decompress_progress(10, 0, total_files, start_free, False)
                self.emit_worker_usage()

        monitor_thread = threading.Thread(target=monitor_drive_space, daemon=True)
        monitor_thread.start()

        try:
            returncode, output = run_compact_process(
                self.compact_decompress_folder_args(),
                self.processes,
                self.process_lock,
                log_callback=lambda line: self.log.emit(line),
                cancel_check=lambda: self.cancel_requested,
                cwd=self.target_path,
            )
        finally:
            monitor_stop.set()
            monitor_thread.join(timeout=1.0)
            with self.active_lock:
                self.active_chunks.pop(1, None)
            self.active_files.emit(1, "done", [(self.target_path, total_bytes)])
            self.emit_worker_usage()

        if self.cancel_requested:
            return False, True, 0, 0

        if returncode != 0:
            if output:
                self.log.emit(output.strip())
            return False, False, before_compressed, before_total

        self.emit_decompress_progress(90, total_files, total_files, start_free)

        def after_progress(compressed_count, scanned_count):
            percent = 90
            if total_files:
                percent = 90 + min(9, int((scanned_count / total_files) * 9))
            self.emit_decompress_progress(percent, scanned_count, total_files, start_free)

        after_compressed, after_total = scan_compressed_attribute_count(
            self.target_path,
            after_progress,
            lambda: self.cancel_requested,
        )

        if self.cancel_requested:
            return False, True, after_compressed, after_total

        if after_compressed > 0:
            self.log.emit(
                f"Decompression finished but {after_compressed}/{after_total} file(s) still have the compressed attribute. "
                "They may be locked/in use or Windows may have skipped them."
            )
        else:
            self.log.emit("Decompression verified: 0 compressed files remain.")

        return True, False, after_compressed, after_total

    def process_mixed_chunks(self, normal_chunks, huge_chunks, processed_files, processed_bytes, total_files, total_bytes, failed):
        if not normal_chunks and not huge_chunks:
            return processed_files, processed_bytes, failed

        if huge_chunks:
            if normal_chunks and self.max_workers > 1:
                reserved_normal_workers = max(1, min(len(normal_chunks), self.max_workers // 3))
                huge_worker_budget = max(1, self.max_workers - reserved_normal_workers)
                huge_worker_count = min(len(huge_chunks), huge_worker_budget)
                normal_worker_count = min(len(normal_chunks), max(1, self.max_workers - huge_worker_count))
            else:
                huge_worker_count = min(len(huge_chunks), self.max_workers)
                normal_worker_count = 0
        else:
            normal_worker_count = min(self.max_workers, max(1, len(normal_chunks))) if normal_chunks else 0
            huge_worker_count = 0

        normal_executor = None
        huge_executor = None
        pending = set()
        chunk_id = 1

        try:
            if normal_worker_count > 0:
                normal_executor = concurrent.futures.ThreadPoolExecutor(max_workers=normal_worker_count)
                for chunk in normal_chunks:
                    future = normal_executor.submit(self.run_compact_chunk, chunk_id, chunk, "normal")
                    pending.add(future)
                    chunk_id += 1

            if huge_worker_count > 0:
                huge_executor = concurrent.futures.ThreadPoolExecutor(max_workers=huge_worker_count)
                for chunk in huge_chunks:
                    future = huge_executor.submit(self.run_compact_chunk, chunk_id, chunk, "huge")
                    pending.add(future)
                    chunk_id += 1

            last_heartbeat = 0

            while pending:
                done_futures, pending = concurrent.futures.wait(
                    pending,
                    timeout=1,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                for future in done_futures:
                    if future.cancelled():
                        continue
                    try:
                        ok, count, chunk_bytes, output = future.result()
                    except Exception as e:
                        ok, count, chunk_bytes, output = False, 0, 0, str(e)

                    if output and not ok and not self.cancel_requested:
                        self.log.emit(output.strip())

                    processed_files = min(processed_files + count, total_files)
                    processed_bytes = min(processed_bytes + chunk_bytes, total_bytes)
                    if not ok:
                        failed = True

                percent = 1
                if total_bytes > 0:
                    percent = 1 + min(89, int((processed_bytes / total_bytes) * 89))

                now = time.time()
                self.check_auto_pause_for_game()

                if done_futures or now - last_heartbeat >= 1:
                    last_heartbeat = now
                    self.emit_worker_usage()
                    active = self.active_summary()
                    active_biggest = int(active.get("biggest", 0) or 0)
                    active_file_name = active.get("file_name", "")
                    active_elapsed = float(active.get("elapsed", 0) or 0)
                    huge_active = bool(active.get("huge_active", False))
                    normal_active = bool(active.get("normal_active", False))

                    if self.pause_active:
                        idle = format_elapsed(self.pause_idle_seconds)
                        status = (
                            f"{self.action_label}: compact.exe paused while gaming\n"
                            f"Detected: {self.pause_game_name or 'game'}\n"
                            f"Idle: {idle} / resumes at {format_elapsed(IDLE_RESUME_SECONDS)} idle\n"
                            f"Completed: {format_game_size(processed_bytes)} / {format_game_size(total_bytes)}"
                        )
                        allow_eta = False
                    elif self.pause_reason == "PC idle, compression allowed":
                        status = (
                            f"{self.action_label}: PC idle, compression allowed\n"
                            f"Idle: {format_elapsed(self.pause_idle_seconds)}\n"
                            f"Completed: {format_game_size(processed_bytes)} / {format_game_size(total_bytes)}"
                        )
                        allow_eta = processed_bytes > 0
                    elif huge_active:
                        size_note = "very huge file" if active_biggest >= HUGE_FILE_WARNING_BYTES else "huge file"
                        lane_note = "Small files are still processing in the other worker slots." if normal_active else "Waiting on the huge-file lane."
                        status = (
                            f"{self.action_label}: {size_note} active\n"
                            f"Current huge file: {active_file_name}\n"
                            f"File size: {format_game_size(active_biggest)} | File elapsed: {format_elapsed(active_elapsed)}\n"
                            f"{lane_note}\n"
                            f"Completed: {format_game_size(processed_bytes)} / {format_game_size(total_bytes)}"
                        )
                        allow_eta = False
                    elif normal_active:
                        status = (
                            f"{self.action_label}: processing small/normal chunks\n"
                            f"Completed: {format_game_size(processed_bytes)} / {format_game_size(total_bytes)}"
                        )
                        allow_eta = processed_bytes > 0
                    else:
                        status = (
                            f"{self.action_label}: waiting for worker update\n"
                            f"Completed: {format_game_size(processed_bytes)} / {format_game_size(total_bytes)}"
                        )
                        allow_eta = processed_bytes > 0

                    self.progress.emit(
                        percent,
                        global_progress_text(status, percent, self.task_start_time, allow_eta),
                        processed_files,
                        total_files,
                    )

                if self.cancel_requested:
                    break

        finally:
            if normal_executor:
                normal_executor.shutdown(wait=True, cancel_futures=True)
            if huge_executor:
                huge_executor.shutdown(wait=True, cancel_futures=True)

        return processed_files, processed_bytes, failed

    def run(self):
        self.task_start_time = time.time()
        mode = "compress" if self.action_label == "Compressing" else "decompress"
        algorithm_note = f" using {self.compression_algorithm}" if self.action_label == "Compressing" else ""

        self.log.emit(
            f"Starting compact {mode}{algorithm_note}. Using {self.max_workers} worker(s) "
            f"from settings, CPU threads available: {self.cpu_workers} "
            f"[mode={self.worker_mode}, custom={self.worker_count}]: {self.target_path}"
        )

        if self.auto_pause_when_game_running:
            self.log.emit(
                "Smart gaming pause enabled. Pauses compact.exe while gaming "
                f"and resumes after {IDLE_RESUME_SECONDS}s PC idle."
            )
        if self.file_order == "balanced_small_first":
            self.log.emit("Background file order enabled: starts with small files and periodically mixes in huge files.")

        self.emit_global_progress(0, f"{self.action_label}: preparing files...", 0, 0)

        try:
            files = self.collect_files()
            total_files = len(files)
            total_bytes = sum(file_size for _, file_size in files)

            if self.cancel_requested:
                self.done.emit(False, True, 0, 0)
                return

            if total_files == 0:
                self.emit_global_progress(100, f"{self.action_label}: no files found", 0, 0)
                self.done.emit(True, False, 0, 0)
                return

            if self.action_label == "Decompressing":
                start_free = get_drive_free_bytes(self.target_path)
                self.emit_decompress_progress(1, 0, total_files, start_free)

                def before_progress(compressed_count, scanned_count):
                    percent = 1
                    if total_files:
                        percent = 1 + min(4, int((scanned_count / total_files) * 4))
                    self.emit_decompress_progress(percent, scanned_count, total_files, start_free)

                before_compressed, before_total = scan_compressed_attribute_count(
                    self.target_path,
                    before_progress,
                    lambda: self.cancel_requested,
                )

                if self.cancel_requested:
                    self.resume_suspended_compact_processes()
                    self.emit_global_progress(0, f"{self.action_label}: cancelled", 0, total_files)
                    self.done.emit(False, True, 0, 0)
                    return

                self.log.emit(f"Compressed files before decompression: {before_compressed}/{before_total}")

                normal_chunks, huge_chunks = self.split_chunks(files)
                processed_files = 0
                processed_bytes = 0
                failed = False

                if huge_chunks:
                    huge_total = sum(chunk[0][1] for chunk in huge_chunks)
                    if normal_chunks and self.max_workers > 1:
                        reserved_normal_workers = max(1, min(len(normal_chunks), self.max_workers // 3))
                        huge_lane_workers = min(len(huge_chunks), max(1, self.max_workers - reserved_normal_workers))
                        normal_lane_workers = min(len(normal_chunks), max(1, self.max_workers - huge_lane_workers))
                    else:
                        huge_lane_workers = min(len(huge_chunks), self.max_workers)
                        normal_lane_workers = 0
                    self.log.emit(
                        f"Decompression huge-file lane: {len(huge_chunks)} huge file(s), {format_game_size(huge_total)} total. "
                        f"Running up to {huge_lane_workers} huge file(s) at a time."
                    )
                    self.log.emit(f"Worker split: {huge_lane_workers} huge-file worker(s) + {normal_lane_workers} normal worker(s).")

                self.emit_global_progress(
                    5,
                    f"{self.action_label}: starting parallel file decompression\nNormal chunks: {len(normal_chunks)} | Huge files: {len(huge_chunks)}",
                    0,
                    total_files,
                )

                processed_files, processed_bytes, failed = self.process_mixed_chunks(
                    normal_chunks, huge_chunks, processed_files, processed_bytes, total_files, total_bytes, failed
                )

                if self.cancel_requested:
                    self.resume_suspended_compact_processes()
                    self.emit_global_progress(0, f"{self.action_label}: cancelled", processed_files, total_files)
                    self.done.emit(False, True, 0, 0)
                    return

                self.resume_suspended_compact_processes()
                self.emit_decompress_progress(90, total_files, total_files, start_free)

                def after_progress(compressed_count, scanned_count):
                    percent = 90
                    if total_files:
                        percent = 90 + min(9, int((scanned_count / total_files) * 9))
                    self.emit_decompress_progress(percent, scanned_count, total_files, start_free)

                remaining_compressed, verified_total = scan_compressed_attribute_count(
                    self.target_path,
                    after_progress,
                    lambda: self.cancel_requested,
                )

                if self.cancel_requested:
                    self.resume_suspended_compact_processes()
                    self.emit_global_progress(0, f"{self.action_label}: cancelled", processed_files, total_files)
                    self.done.emit(False, True, 0, 0)
                    return

                self.resume_suspended_compact_processes()
                final_status = "Decompressing: done"
                if remaining_compressed:
                    final_status = f"Decompressing: done, but {remaining_compressed}/{verified_total} file(s) still look compressed"
                elif failed:
                    final_status = "Decompressing: done, but some compact tasks reported errors"
                self.emit_global_progress(100 if not failed else 0, final_status, total_files, total_files)
                self.done.emit(not failed, False, 0, 0)
                return

            normal_chunks, huge_chunks = self.split_chunks(files)
            processed_files = 0
            processed_bytes = 0
            failed = False

            if huge_chunks:
                huge_total = sum(chunk[0][1] for chunk in huge_chunks)
                if normal_chunks and self.max_workers > 1:
                    reserved_normal_workers = max(1, min(len(normal_chunks), self.max_workers // 3))
                    huge_lane_workers = min(len(huge_chunks), max(1, self.max_workers - reserved_normal_workers))
                    normal_lane_workers = min(len(normal_chunks), max(1, self.max_workers - huge_lane_workers))
                else:
                    huge_lane_workers = min(len(huge_chunks), self.max_workers)
                    normal_lane_workers = 0
                self.log.emit(
                    f"Huge-file lane active: {len(huge_chunks)} huge file(s), {format_game_size(huge_total)} total. "
                    f"Running up to {huge_lane_workers} huge file(s) at a time."
                )
                self.log.emit(f"Worker split: {huge_lane_workers} huge-file worker(s) + {normal_lane_workers} normal worker(s).")
                for chunk in huge_chunks:
                    file_path, file_size = chunk[0]
                    self.log.emit(f"Huge queued: {os.path.basename(file_path)} | {format_game_size(file_size)}")

            self.emit_global_progress(
                1,
                f"{self.action_label}: starting\nNormal chunks: {len(normal_chunks)} | Huge files: {len(huge_chunks)}",
                0,
                total_files,
            )

            processed_files, processed_bytes, failed = self.process_mixed_chunks(
                normal_chunks, huge_chunks, processed_files, processed_bytes, total_files, total_bytes, failed
            )

            if self.cancel_requested:
                self.resume_suspended_compact_processes()
                self.emit_global_progress(0, f"{self.action_label}: cancelled", processed_files, total_files)
                self.done.emit(False, True, 0, 0)
                return

            ok = not failed
            compressed_size = 0
            compressed_file_count = 0
            self.resume_suspended_compact_processes()

            if ok and self.action_label == "Compressing":
                self.emit_global_progress(90, "Checking compressed size on disk...", processed_files, total_files)

                def disk_progress(current_size, current_count):
                    percent = 90
                    if total_files:
                        percent = 90 + min(8, int((current_count / total_files) * 8))
                    self.progress.emit(
                        percent,
                        global_progress_text(f"Checking compressed size: {format_game_size(current_size)}", percent, self.task_start_time, True),
                        current_count,
                        total_files,
                    )

                compressed_size, compressed_file_count = scan_folder_size_on_disk(
                    self.target_path, disk_progress, lambda: self.cancel_requested
                )

                if compressed_size <= 0 and not self.cancel_requested:
                    self.log.emit("Windows compressed-size API returned 0; using allocated-size fallback.")
                    self.emit_global_progress(98, "Finalizing compressed size with allocated-size fallback...", processed_files, total_files)
                    compressed_size, compressed_file_count = estimate_folder_allocated_size(self.target_path)

                if self.cancel_requested:
                    self.resume_suspended_compact_processes()
                    self.emit_global_progress(0, f"{self.action_label}: cancelled", processed_files, total_files)
                    self.done.emit(False, True, 0, 0)
                    return

            self.resume_suspended_compact_processes()
            self.emit_global_progress(100 if ok else 0, f"{self.action_label}: done", processed_files, total_files)
            self.done.emit(ok, False, compressed_size, compressed_file_count)

        except Exception as e:
            try:
                self.resume_suspended_compact_processes()
            except Exception:
                pass
            self.log.emit(f"Command failed: {e}")
            self.done.emit(False, self.cancel_requested, 0, 0)

