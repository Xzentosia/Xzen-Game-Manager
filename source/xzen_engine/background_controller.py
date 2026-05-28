from PyQt5.QtWidgets import QMessageBox

from .constants import (
    APP_NAME,
    AUTO_PAUSE_WHEN_GAME_RUNNING,
    DEFAULT_WORKER_COUNT,
    DEFAULT_WORKER_MODE,
    compression_algorithm_label,
    normalized_worker_count,
    normalized_worker_mode,
)
from .deps import StateMachine, get_logger, has_transitions
from .formatting import format_game_size
from .workers import CompactWorker

LOGGER = get_logger(__name__)


class BackgroundRunController:
    def __init__(self, host):
        self.host = host
        self.phase = "idle"
        self.machine = None
        if has_transitions() and StateMachine is not None:
            self.machine = StateMachine(
                model=self,
                model_attribute="phase",
                states=["idle", "running", "paused", "cancelling", "cleanup"],
                transitions=[
                    {"trigger": "begin", "source": "idle", "dest": "running"},
                    {"trigger": "set_paused", "source": "running", "dest": "paused"},
                    {"trigger": "resume_run", "source": "paused", "dest": "running"},
                    {"trigger": "begin_cancel", "source": "*", "dest": "cancelling"},
                    {"trigger": "begin_cleanup", "source": "*", "dest": "cleanup"},
                    {"trigger": "finish_run", "source": "*", "dest": "idle"},
                ],
                initial="idle",
                auto_transitions=False,
                ignore_invalid_triggers=True,
            )
        self._sync_host_state()

    def _transition(self, trigger_name, fallback_phase):
        if self.machine is not None and hasattr(self, trigger_name):
            try:
                getattr(self, trigger_name)()
            except Exception:
                self.phase = fallback_phase
        else:
            self.phase = fallback_phase
        self._sync_host_state()

    def _sync_host_state(self):
        h = self.host
        active = self.phase in {"running", "paused", "cancelling", "cleanup"}
        h.background_compress_active = active
        h.background_compress_paused = self.phase == "paused"
        h.background_compress_cancel_requested = self.phase in {"cancelling", "cleanup"}

    def start_background_compress_all(self):
        h = self.host
        if h.busy:
            QMessageBox.warning(h, APP_NAME, "A task is already running.")
            return

        h.refresh_background_game_detection()
        h.background_queue = h.background_game_queue()

        if not h.background_queue:
            h.log("No checked background compression or decompression tasks found.")
            return

        self._transition("begin", "running")
        h.background_total = len(h.background_queue)
        h.background_current_index = None
        h.background_status_text = f"Preparing {h.background_total} background task(s)..."
        h.reset_background_progress_bars(
            h.background_status_text,
            "Preparing queue 0%",
            "Game data waiting",
            "Files waiting",
        )
        h.busy = True
        h.set_buttons_enabled(False)
        compress_count = sum(1 for item in h.background_queue if item.get("action") == "compress")
        decompress_count = sum(1 for item in h.background_queue if item.get("action") == "decompress")
        h.log(
            f"Background queue started: {compress_count} compress task(s), "
            f"{decompress_count} decompress task(s)."
        )
        LOGGER.info("background_queue_started", compress_tasks=compress_count, decompress_tasks=decompress_count)
        h.update_dashboard()
        self.start_next_background_compress_game()

    def start_next_background_compress_game(self):
        h = self.host
        if h.background_compress_cancel_requested:
            self.finish_background_compress("Background tasks cancelled.")
            return

        if h.background_compress_paused:
            h.update_background_controls()
            return

        if not h.background_queue:
            self.finish_background_compress("Background tasks complete.")
            return

        task = h.background_queue.pop(0)
        if isinstance(task, dict):
            index = int(task.get("index", -1))
            action = task.get("action", "compress")
        else:
            index = int(task)
            action = "compress"

        if index < 0 or index >= len(h.games):
            self.start_next_background_compress_game()
            return
        if action not in {"compress", "decompress"}:
            action = "compress"

        game = h.games[index]
        h.background_current_index = index
        h.background_current_action = action
        h.background_game_pause_active = False
        h.background_game_pause_name = ""
        h.background_game_pause_reason = ""
        algorithm = h.selected_compression_algorithm()
        label = compression_algorithm_label(algorithm)
        action_label = "Decompressing" if action == "decompress" else "Compressing"

        if action == "decompress":
            h.log(f"Background decompressing {game.get('name', 'Unknown')}...")
        else:
            h.log(f"Background compressing {game.get('name', 'Unknown')} with {label}...")

        current = max(1, h.background_total - len(h.background_queue))
        h.background_status_text = (
            f"Task {current}/{h.background_total} | {action_label} {game.get('name', 'Unknown')}..."
        )
        progress_text = "Decompression progress 0%" if action == "decompress" else "Compression progress 0%"
        data_text = "Clearing Windows compression flags" if action == "decompress" else "Completed 0 GB / calculating"
        h.reset_background_progress_bars(
            h.background_status_text,
            progress_text,
            data_text,
            "Files waiting",
        )
        h.games[index]["status"] = "Background Decompressing" if action == "decompress" else "Background Compressing"
        h.refresh_grid()
        h.update_dashboard()

        h.compact_worker = CompactWorker(
            game["path"],
            action_label,
            algorithm,
            normalized_worker_mode(h.app_settings.get("worker_mode", DEFAULT_WORKER_MODE)),
            normalized_worker_count(h.app_settings.get("worker_count", DEFAULT_WORKER_COUNT)),
            game_paths=h.game_detection_paths(),
            auto_pause_when_game_running=bool(h.app_settings.get("smart_game_pause", AUTO_PAUSE_WHEN_GAME_RUNNING)),
            file_order="balanced_small_first",
        )
        h.retain_worker_until_finished(h.compact_worker)
        h.background_worker_capacity = getattr(h.compact_worker, "max_workers", 0)
        h.background_worker_active = 0
        h.compact_worker.log.connect(h.log)
        h.compact_worker.progress.connect(self.update_background_compress_progress)
        h.compact_worker.worker_usage.connect(h.update_background_worker_usage)
        h.compact_worker.pause_state.connect(h.update_background_pause_state)

        if action == "decompress":
            h.compact_worker.done.connect(
                lambda ok, cancelled, compressed_size, compressed_file_count, i=index: self.on_background_decompress_done(i, ok, cancelled)
            )
        else:
            h.compact_worker.done.connect(
                lambda ok, cancelled, compressed_size, compressed_file_count, i=index, a=algorithm: self.on_background_compress_done(
                    i, a, ok, cancelled, compressed_size, compressed_file_count
                )
            )
        h.compact_worker.start()

    def update_background_compress_progress(self, percent, status, processed, total):
        h = self.host
        current = max(1, h.background_total - len(h.background_queue))
        state = "Paused" if (h.background_compress_paused or h.background_game_pause_active) else "Running"
        action_text = {
            "compress": "Compressing",
            "decompress": "Decompressing",
            "cleanup": "Cleanup",
        }.get(h.background_current_action, "Processing")
        percent = max(0, min(100, int(percent or 0)))
        file_percent = 0
        if total:
            file_percent = int((processed / total) * 100)
        file_percent = max(0, min(100, file_percent))

        global_line = h.progress_status_line(status, "Global progress:")
        completed_line = h.progress_status_line(status, "Completed:")

        h.background_progress_summary = f"{state} | {action_text} | Task {current}/{h.background_total}"
        h.background_task_progress_value = percent
        if global_line:
            progress_prefix = "Decompression progress:" if h.background_current_action in {"decompress", "cleanup"} else "Compression progress:"
            h.background_task_progress_text = global_line.replace("Global progress:", progress_prefix, 1)
        else:
            h.background_task_progress_text = f"{action_text} progress {percent}%"

        h.background_completed_progress_value = percent
        h.background_completed_progress_text = (
            completed_line
            if completed_line
            else f"Completed {format_game_size(processed)} / {format_game_size(total)}"
        )

        h.background_file_progress_value = file_percent
        h.background_file_progress_text = f"Files {processed}/{total}" if total else f"Files {processed}"
        h.background_status_text = h.background_progress_summary
        h.update_dashboard()
        h.refresh_grid_throttled()

    def on_background_compress_done(self, index, algorithm, ok, cancelled, compressed_size, compressed_file_count):
        h = self.host
        cleanup_requested = bool(
            h.compact_worker and getattr(h.compact_worker, "cancel_cleanup_requested", False)
        )
        if ok and 0 <= index < len(h.games):
            h.games[index]["status"] = "Compressed"
            h.games[index]["compression_algorithm"] = algorithm
            h.games[index]["compressed_size"] = compressed_size
            h.games[index]["compressed_file_count"] = compressed_file_count
            game_name = h.games[index].get("name", "Unknown")
            saved_amount = max(0, int(h.games[index].get("size", 0) or 0) - int(compressed_size or 0))
            h.log(
                f"Background compressed {game_name} with {algorithm}. "
                f"Saved: {format_game_size(saved_amount)}."
            )
            if hasattr(h, "show_saved_space_toast"):
                h.show_saved_space_toast(game_name, saved_amount)
        elif cancelled and cleanup_requested and 0 <= index < len(h.games):
            h.log("Background compression cancelled. Cleaning up current game...")
            self._transition("begin_cleanup", "cleanup")
            h.background_queue = []
            h.games[index]["status"] = "Cleaning Up"
            h.games[index]["compression_algorithm"] = ""
            h.games[index]["compressed_size"] = 0
            h.games[index]["compressed_file_count"] = 0
            h.save_games()
            h.refresh_grid()
            self.start_background_cleanup(index)
            return
        elif cancelled:
            self.finish_background_compress("Background compression cancelled.")
            return
        else:
            if 0 <= index < len(h.games):
                h.games[index]["status"] = "Failed"
            h.log(f"Background compression failed for game index {index}. Continuing.")

        h.save_games()
        h.refresh_grid()
        h.update_dashboard()
        self.start_next_background_compress_game()

    def on_background_decompress_done(self, index, ok, cancelled):
        h = self.host
        if ok and 0 <= index < len(h.games):
            game_name = h.games[index].get("name", "Unknown")
            previous_saved_amount = max(
                0,
                int(h.games[index].get("size", 0) or 0) - int(h.games[index].get("compressed_size", 0) or 0),
            )
            h.games[index]["status"] = "Normal"
            h.games[index]["compression_algorithm"] = ""
            h.games[index]["compressed_size"] = 0
            h.games[index]["compressed_file_count"] = 0
            h.background_decompress_selected_paths.discard(h.background_game_key(h.games[index]))
            h.log(f"Background decompressed {game_name}.")
            if hasattr(h, "show_hotpill_toast"):
                h.show_hotpill_toast(
                    game_name,
                    f"Restored | Lost {format_game_size(previous_saved_amount)}",
                )
        elif cancelled:
            self.finish_background_compress("Background decompression cancelled.")
            return
        else:
            if 0 <= index < len(h.games):
                h.games[index]["status"] = "Decompress Failed"
            h.log(f"Background decompression failed for game index {index}. Continuing.")

        h.save_background_selection()
        h.save_games()
        h.refresh_grid()
        h.update_dashboard()
        self.start_next_background_compress_game()

    def start_background_cleanup(self, index):
        h = self.host
        self._transition("begin_cleanup", "cleanup")
        h.background_current_action = "cleanup"
        h.background_game_pause_active = False
        h.background_game_pause_name = ""
        h.background_game_pause_reason = ""
        h.compact_worker = CompactWorker(
            h.games[index]["path"],
            "Decompressing",
            h.selected_compression_algorithm(),
            normalized_worker_mode(h.app_settings.get("worker_mode", DEFAULT_WORKER_MODE)),
            normalized_worker_count(h.app_settings.get("worker_count", DEFAULT_WORKER_COUNT)),
            game_paths=h.game_detection_paths(),
            auto_pause_when_game_running=bool(h.app_settings.get("smart_game_pause", AUTO_PAUSE_WHEN_GAME_RUNNING)),
            file_order="balanced_small_first",
        )
        h.retain_worker_until_finished(h.compact_worker)
        h.background_worker_capacity = getattr(h.compact_worker, "max_workers", 0)
        h.background_worker_active = 0
        h.compact_worker.log.connect(h.log)
        h.compact_worker.progress.connect(self.update_background_compress_progress)
        h.compact_worker.worker_usage.connect(h.update_background_worker_usage)
        h.compact_worker.pause_state.connect(h.update_background_pause_state)
        h.compact_worker.done.connect(
            lambda ok, cancelled, compressed_size, compressed_file_count, i=index: self.on_background_cleanup_done(i, ok)
        )
        h.compact_worker.start()

    def on_background_cleanup_done(self, index, ok):
        h = self.host
        if ok and 0 <= index < len(h.games):
            h.games[index]["status"] = "Normal"
            h.log(f"Cleanup finished for {h.games[index].get('name', 'Unknown')}.")
        else:
            if 0 <= index < len(h.games):
                h.games[index]["status"] = "Cleanup Failed"
            h.log("Cleanup failed.")
        h.save_games()
        h.refresh_grid()
        h.update_dashboard()
        self.finish_background_compress("Background task cancelled and current game cleaned up.")

    def toggle_background_pause(self):
        h = self.host
        if not h.background_compress_active:
            return
        if h.background_compress_paused:
            self._transition("resume_run", "running")
        else:
            self._transition("set_paused", "paused")
        if h.compact_worker and h.compact_worker.isRunning():
            h.compact_worker.set_manual_pause(h.background_compress_paused)
        elif not h.background_compress_paused:
            self.start_next_background_compress_game()

        if h.background_status_text:
            if h.background_compress_paused:
                h.background_status_text = h.background_status_text.replace("Running |", "Paused |", 1)
            else:
                h.background_status_text = h.background_status_text.replace("Paused |", "Running |", 1)

        h.update_background_controls()
        h.log("Background compression paused." if h.background_compress_paused else "Background compression resumed.")

    def cancel_background_compress_all(self):
        h = self.host
        if not h.background_compress_active:
            return
        cleanup_requested = False
        if h.compact_worker and h.compact_worker.isRunning() and h.background_current_action == "compress":
            choice = h.ask_cancel_cleanup_choice("Cancel background compression")
            if choice == "keep":
                return
            cleanup_requested = choice == "cleanup"
        self._transition("begin_cancel", "cancelling")
        h.background_queue = []
        h.background_pause_btn.setEnabled(False)
        h.background_cancel_btn.setEnabled(False)
        h.background_status_text = "Cancelling background compression..."
        h.background_progress_summary = h.background_status_text
        h.background_task_progress_text = "Cancelling current task"
        h.background_completed_progress_text = "Cleanup will restore files" if cleanup_requested else "Stopping without cleanup"
        h.background_file_progress_text = "Stopping workers"
        h.update_background_controls()

        if h.compact_worker and h.compact_worker.isRunning():
            h.compact_worker.cancel(cleanup_decompress=cleanup_requested)
        else:
            self.finish_background_compress("Background tasks cancelled.")

    def finish_background_compress(self, message):
        h = self.host
        self._transition("finish_run", "idle")
        h.background_game_pause_active = False
        h.background_game_pause_name = ""
        h.background_game_pause_reason = ""
        h.background_queue = []
        h.background_total = 0
        h.background_current_index = None
        h.background_current_action = ""
        h.background_status_text = ""
        h.background_worker_active = 0
        h.background_worker_capacity = 0
        h.compact_worker = None
        h.busy = False
        h.background_pause_btn.setEnabled(True)
        h.background_cancel_btn.setEnabled(True)
        h.set_buttons_enabled(True)
        h.reset_background_progress_bars("")
        h.log(message)
        h.save_games()
        h.refresh_grid()
        h.update_dashboard()
