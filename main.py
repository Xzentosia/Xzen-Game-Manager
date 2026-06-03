import os
import ctypes
import sys
import time
from ctypes import wintypes

from PyQt5.QtCore import (
    Qt,
    QRectF,
    QRect,
    QPoint,
    QEvent,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QAbstractAnimation,
)
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics, QKeySequence, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QMainWindow,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QFrame,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QDialog,
    QScrollArea,
    QCheckBox,
    QLineEdit,
    QGraphicsOpacityEffect,
    QShortcut,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QSizePolicy,
)

from source.tabs.settings import XGCRSettingsPage
from source.tabs.game_library import PosterCropDialog, XGCRGameLibraryPage
from source.xzen_engine.core import *
from source.xzen_engine.app_state import (
    add_or_update_game as state_add_or_update_game,
    background_compress_candidates as state_background_compress_candidates,
    background_decompress_candidates as state_background_decompress_candidates,
    background_game_key as state_background_game_key,
    background_is_decompress_checked as state_background_is_decompress_checked,
    background_is_game_checked as state_background_is_game_checked,
    background_saved_bytes as state_background_saved_bytes,
    dedupe_games as state_dedupe_games,
    is_game_compressed as state_is_game_compressed,
    load_app_settings,
    load_games as state_load_games,
    original_game_size as state_original_game_size,
    prune_uninstalled_games as state_prune_uninstalled_games,
    save_app_settings,
    save_games as state_save_games,
    saved_game_is_installed as state_saved_game_is_installed,
)
from source.xzen_engine.background_jobs import (
    build_background_queue as state_build_background_queue,
    build_game_detection_paths as state_build_game_detection_paths,
)
from source.xzen_engine.background_controller import BackgroundRunController
from source.xzen_engine.constants import APP_ICON_FILE
from source.xzen_engine.deps import get_logger
from source.xzen_engine.posters import safe_cache_name
from source.xzen_engine.theme import color as theme_color, status_pill_style, themed_qss
from source.xzen_engine.ui_widgets import (
    CustomTitleBar,
    DashboardGauge,
    DashboardMiniCard,
    QuickStatsFloatingWindow,
)
from source.logs import log_action, log_error, log_exception, log_success, log_warning, reset_logs
from source.xzen_engine.manual_library import (
    is_drive_root_path as state_is_drive_root_path,
    is_manual_library_folder as state_is_manual_library_folder,
    manual_game_from_folder as state_manual_game_from_folder,
    manual_games_from_selected_folder as state_manual_games_from_selected_folder,
    resolve_manual_game_folder as state_resolve_manual_game_folder,
)

class XzenGameManager(QMainWindow):
    def __init__(self):
        super().__init__()
        reset_logs()
        log_action("debug", "main", "app_start", "Application log files reset for a fresh session.")
        self.games = []
        self.selected_index = None
        self.size_worker = None
        self.poster_worker = None
        self.store_scan_worker = None
        self.compact_worker = None
        self.worker_refs = []
        self.game_library_busy_reasons = {}
        self.game_library_busy_overlay_suppressed = False
        self.busy = False
        self.background_compress_active = False
        self.background_compress_paused = False
        self.background_compress_cancel_requested = False
        self.background_queue = []
        self.background_total = 0
        self.background_current_index = None
        self.background_current_action = ""
        self.background_status_text = ""
        self.background_progress_summary = ""
        self.background_task_progress_value = 0
        self.background_task_progress_text = "Overall progress 0%"
        self.background_completed_progress_value = 0
        self.background_completed_progress_text = "Completed 0 GB / 0 GB"
        self.background_file_progress_value = 0
        self.background_file_progress_text = "Files 0/0"
        self.foreground_task_progress_value = 0
        self.foreground_task_progress_text = "Overall progress 0%"
        self.foreground_status_text = ""
        self.foreground_file_progress_value = 0
        self.foreground_file_progress_text = "Files 0/0"
        self.foreground_pause_active = False
        self.foreground_pause_name = ""
        self.foreground_pause_reason = ""
        self.background_worker_active = 0
        self.background_worker_capacity = 0
        self.background_game_pause_active = False
        self.background_game_pause_name = ""
        self.background_game_pause_reason = ""
        self.last_grid_refresh = 0
        self.game_library_refresh_pending = False
        self.app_settings = self.load_settings()
        self.background_selection_mode = self.app_settings.get("background_selection_mode", "all")
        self.background_selected_paths = set(self.app_settings.get("background_selected_paths", []))
        self.background_decompress_selected_paths = set(self.app_settings.get("background_decompress_selected_paths", []))
        self.background_controller = BackgroundRunController(self)
        self.event_logger = get_logger("xzen_game_compressor")
        self.global_insert_hotkey_id = 0xA117
        self.global_insert_hotkey_registered = False
        self.tray_icon = None
        self.force_exit = False

        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
            | Qt.WindowCloseButtonHint
        )
        self.setWindowTitle(APP_NAME)
        if APP_ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_FILE)))
        self.resize(1150, 700)
        self.setMinimumSize(1150, 700)
        self.apply_style()
        self.build_ui()
        self.setup_tray_icon()
        self.load_games()
        self.run_first_launch_scan_if_needed()
        self.refresh_grid()
        self.update_dashboard()

    def apply_style(self):
        self.setStyleSheet(themed_qss("""
            
            QMainWindow { background: #0B0A10; } 
            QWidget { 
                background: #0B0A10; color: #eeeeee; 
                font-family: "Segoe UI Variable", "Inter", system-ui, sans-serif; font-size: 13px; 
            }
            QLabel { background: transparent; }

            
            QPushButton { 
                background: #181525; color: #FFFFFF; 
                border: 1px solid #2B2640; border-radius: 8px; 
                padding: 10px 18px; font-weight: 800; font-size: 12px;
            }
            QPushButton:hover { background: #231E36; border: 1px solid #C071FF; color: #C071FF; }
            QPushButton:disabled { background: transparent; color: #444455; border: 1px dashed #2B2640; }

            #CustomTitleBar {
                background: #0F0E17;
                border-bottom: 1px solid #1A1825;
            }
            #CustomTitleLabel {
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 900;
                padding-left: 4px;
            }
            #TitleBarButton {
                background: transparent;
                color: #cccccc;
                border: 1px solid #2B2640;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 900;
                padding: 0;
            }
            #TitleBarButton:hover {
                background: #1B1830;
                color: #FFFFFF;
                border-color: #C071FF;
            }
            #TitleBarCloseButton {
                background: transparent;
                color: #FFB3B3;
                border: 1px solid rgba(255, 107, 107, 0.45);
                border-radius: 6px;
                font-size: 13px;
                font-weight: 900;
                padding: 0;
            }
            #TitleBarCloseButton:hover {
                background: #FF4D6D;
                color: #ffffff;
                border-color: #FF4D6D;
            }

            #DashboardHotPill {
                background: rgba(16, 13, 24, 0.96);
                border: 1px solid #C071FF;
                border-radius: 20px;
            }
            #DashboardHotPillGame {
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 900;
            }
            #DashboardHotPillSaved {
                color: #C071FF;
                font-size: 13px;
                font-weight: 900;
            }

            #QuickStatsOverlay {
                background: transparent;
            }
            #QuickStatsPanel {
                background: rgba(9, 8, 14, 0.78);
                border: 1px solid rgba(192, 113, 255, 0.55);
                border-radius: 12px;
            }
            #QuickStatsTitle {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 900;
            }
            #QuickStatsLabel {
                color: #888899;
                font-size: 11px;
                font-weight: 800;
            }
            #QuickStatsValue {
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 900;
            }
            #QuickStatsStatus {
                color: #C071FF;
                font-size: 12px;
                font-weight: 900;
            }

            
            QPushButton#PrimaryActionBtn, QPushButton#BackgroundCompressButton, QPushButton#BackgroundPickerPrimary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9D4EDD, stop:1 #C071FF);
                color: #FFFFFF; border: none; font-size: 14px; padding: 12px 24px; font-weight: 900;
            }
            QPushButton#PrimaryActionBtn:hover, QPushButton#BackgroundCompressButton:hover, QPushButton#BackgroundPickerPrimary:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #B060F0, stop:1 #D28BFF);
                color: #FFFFFF; border: none;
            }

            
            QComboBox { background: #12101C; color: #eeeeee; border: 1px solid #221E30; border-radius: 8px; padding: 10px 14px; font-weight: 700; }
            QComboBox::drop-down { border: none; width: 28px; }
            QComboBox QAbstractItemView { background: #12101C; color: #eeeeee; border: 1px solid #2B2640; selection-background-color: rgba(192, 113, 255, 0.2); selection-color: #C071FF; }
            
            QCheckBox#ToggleOption { background: transparent; color: #eeeeee; spacing: 12px; font-weight: 700; }
            QCheckBox#ToggleOption::indicator { width: 36px; height: 20px; border-radius: 10px; background-color: #1A1825; border: 1px solid #2B2640; }
            QCheckBox#ToggleOption::indicator:checked { background-color: #C071FF; border: 1px solid #C071FF; }
            QCheckBox#ToggleOption:hover { color: #ffffff; }
            
            QCheckBox#BackgroundGameCheck { background: transparent; color: #ffffff; spacing: 12px; font-size: 14px; font-weight: 800; }
            QCheckBox#BackgroundGameCheck::indicator { width: 20px; height: 20px; border-radius: 6px; background: #12101C; border: 1px solid #2B2640; }
            QCheckBox#BackgroundGameCheck::indicator:checked { background: #C071FF; border-color: #C071FF; }
            QCheckBox#BackgroundGameCheck:hover { color: #C071FF; }
            QCheckBox#BackgroundEmergencyCheck { background: transparent; color: #FF6B6B; spacing: 12px; font-size: 14px; font-weight: 900; }
            QCheckBox#BackgroundEmergencyCheck::indicator { width: 20px; height: 20px; border-radius: 6px; background: #12101C; border: 1px solid rgba(255, 107, 107, 0.6); }
            QCheckBox#BackgroundEmergencyCheck::indicator:checked { background: #FF4D6D; border-color: #FF4D6D; }
            QCheckBox#BackgroundEmergencyCheck:hover { color: #FF8FA3; }
            QCheckBox#BackgroundDecompressCheck { background: transparent; color: #FFD166; spacing: 12px; font-size: 14px; font-weight: 900; }
            QCheckBox#BackgroundDecompressCheck::indicator { width: 20px; height: 20px; border-radius: 6px; background: #12101C; border: 1px solid rgba(255, 209, 102, 0.6); }
            QCheckBox#BackgroundDecompressCheck::indicator:checked { background: #FFD166; border-color: #FFD166; }
            QCheckBox#BackgroundDecompressCheck:hover { color: #FFE08A; }

            QSpinBox { background: #12101C; color: #eeeeee; border: 1px solid #2B2640; border-radius: 8px; padding: 10px 14px; font-weight: 700; }
            QSpinBox:disabled { color: #555566; border-color: #1A1825; background: #0F0E17; }

            
            QProgressBar { background: #15131C; border: 1px solid #221E30; border-radius: 6px; text-align: center; color: transparent; height: 14px; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(192, 113, 255, 0.6), stop:1 #C071FF); border-radius: 5px; }
            #FileProgressBar { height: 6px; border-radius: 3px; }
            #FileProgressBar::chunk { background: #00D4FF; border-radius: 3px; } 

            
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
            QScrollBar::handle:vertical { background: #221E30; min-height: 40px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #C071FF; }

            
            #Title { font-size: 24px; font-weight: 900; letter-spacing: -0.5px; color: #FFFFFF; }
            #AdminGood { color: #00E676; font-weight: 800; background: rgba(0, 230, 118, 0.1); padding: 6px 12px; border-radius: 12px; }
            #AdminBad { color: #FF6B6B; font-weight: 800; background: rgba(255, 107, 107, 0.1); padding: 6px 12px; border-radius: 12px; }

            
            #LeftPanel { background: #0F0E17; border-right: 1px solid #1A1825; border-radius: 0; }
            #NavTitle { color: #555566; font-size: 11px; font-weight: 900; letter-spacing: 1.5px; text-transform: uppercase; margin-top: 10px; }
            #PageNav { background: transparent; border: none; padding: 0; outline: 0; }
            #PageNav::item { color: #888899; padding: 14px 18px; border-radius: 8px; font-weight: 700; margin-bottom: 6px; border: 1px solid transparent; }
            #PageNav::item:selected { background: rgba(192, 113, 255, 0.1); color: #C071FF; font-weight: 900; border-left: 3px solid #C071FF; }
            #PageNav::item:hover:!selected { background: #15131C; color: #E0E0E0; }

            #DashboardPage, #SettingsPage { background: transparent; }
            #SettingsDialogTitle { color: #FFFFFF; font-size: 22px; font-weight: 900; }
            #SettingsDialogHint { color: #888899; font-size: 12px; }
            #PlainSectionTitle { color: #FFFFFF; font-size: 16px; font-weight: 900; }

            
            #DashboardHero { background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.7, fx: 0.5, fy: 0.5, stop: 0 rgba(192, 113, 255, 0.05), stop: 1 #12101C); border: 1px solid #221E30; border-radius: 16px; }
            #DashboardHeroInner { background: transparent; }
            #DashboardMiniCard { background: #12101C; border: 1px solid #221E30; border-radius: 16px; }
            #DashboardMiniCard:hover { border: 1px solid rgba(192, 113, 255, 0.4); background: #161422; }
            #DashboardStatus { color: #00E676; font-size: 13px; font-weight: 800; background: rgba(0, 230, 118, 0.1); padding: 6px 14px; border-radius: 12px; }
            
            
            #BackgroundCompressPanel { background: transparent; border: none; }
            #PanelTitle { color: #FFFFFF; font-size: 18px; font-weight: 900; }
            #PanelDesc { color: #888899; font-size: 12px; font-weight: 600; }
            #BackgroundPauseButton, #BackgroundCancelButton { border-radius: 8px; font-weight: 800; }
            #BackgroundEngineProgress, #BackgroundEngineDataProgress, #BackgroundEngineFileProgress {
                background: #0F0E17; border: 1px solid #221E30; border-radius: 7px;
                color: #FFFFFF; font-size: 11px; font-weight: 900; height: 26px; text-align: center;
            }
            #BackgroundEngineProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(192, 113, 255, 0.65), stop:1 #C071FF);
                border-radius: 6px;
            }
            #BackgroundEngineDataProgress::chunk { background: #00D4FF; border-radius: 6px; }
            #BackgroundEngineFileProgress::chunk { background: #00E676; border-radius: 6px; }

            
            #BackgroundPickerDialog { background: #0B0A10; }
            #BackgroundPickerTitle { color: #FFFFFF; font-size: 26px; font-weight: 900; }
            #BackgroundPickerHint { color: #888899; font-size: 13px; font-weight: 600; }
            #BackgroundPickerSection { color: #FFFFFF; font-size: 16px; font-weight: 900; margin-top: 10px; }
            #BackgroundPickerScroll { background: transparent; border: none; }
            #BackgroundPickerScroll QScrollBar:vertical {
                background: #0F0E17;
                width: 50px;
                margin: 0 0 0 12px;
                border: 1px solid #221E30;
                border-radius: 16px;
            }
            #BackgroundPickerScroll QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #C071FF, stop:1 #7B2CBF);
                min-height: 72px;
                border-radius: 15px;
                border: 8px solid #0F0E17;
            }
            #BackgroundPickerScroll QScrollBar::handle:vertical:hover {
                background: #D28BFF;
            }
            #BackgroundPickerScroll QScrollBar::add-line:vertical,
            #BackgroundPickerScroll QScrollBar::sub-line:vertical {
                height: 0;
                background: transparent;
                border: none;
            }
            #BackgroundPickerScroll QScrollBar::add-page:vertical,
            #BackgroundPickerScroll QScrollBar::sub-page:vertical {
                background: transparent;
            }
            #BackgroundPickerContent { background: transparent; }
            
            #BackgroundGameRow { background: #12101C; border: 1px solid #221E30; border-radius: 12px; }
            #BackgroundGameRow:hover { border-color: #C071FF; background: #161422; }
            #BackgroundGameName { color: #FFFFFF; font-size: 15px; font-weight: 900; }
            #BackgroundGameMeta { color: #888899; font-size: 12px; font-weight: 700; }
            #BackgroundRowProgress { background: #0F0E17; border: 1px solid #221E30; border-radius: 6px; color: #FFFFFF; font-size: 11px; font-weight: 900; height: 24px; text-align: center; }
            #BackgroundRowProgress::chunk { background: #C071FF; border-radius: 5px; }
            #BackgroundRowProgress[state="ready"]::chunk { background: rgba(192, 113, 255, 0.3); }
            #BackgroundRowProgress[state="compressed"]::chunk { background: #00D4FF; }
            #BackgroundRowProgress[state="decompress"]::chunk { background: #00D4FF; }
            #BackgroundRowProgress[state="emergency"]::chunk { background: #FF4D6D; }
            
            #BackgroundPickerGhost { background: transparent; color: #eeeeee; border: 1px solid #2B2640; border-radius: 8px; padding: 10px 16px; font-weight: 800; }
            #BackgroundPickerGhost:hover { background: #161422; border-color: #C071FF; color: #C071FF; }

            
            #ManualAddDialog { background: #0B0A10; }
            #ManualAddTitle { color: #FFFFFF; font-size: 24px; font-weight: 900; }
            #ManualAddHint { color: #888899; font-size: 13px; font-weight: 600; }
            #ManualAddFieldLabel { color: #FFFFFF; font-size: 13px; font-weight: 900; }
            #ManualAddInput {
                background: #12101C; color: #FFFFFF; border: 1px solid #2B2640;
                border-radius: 8px; padding: 12px 14px; font-weight: 700;
            }
            #ManualAddInput:focus { border-color: #C071FF; background: #161422; }
            #ManualAddBrowse, #ManualAddCancel {
                background: transparent; color: #eeeeee; border: 1px solid #2B2640;
                border-radius: 8px; padding: 10px 16px; font-weight: 800;
            }
            #ManualAddBrowse:hover, #ManualAddCancel:hover {
                background: #161422; border-color: #C071FF; color: #C071FF;
            }
            #ManualAddPrimary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9D4EDD, stop:1 #C071FF);
                color: #FFFFFF; border: none; border-radius: 8px; padding: 11px 20px; font-weight: 900;
            }
            #ManualAddPrimary:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #B060F0, stop:1 #D28BFF);
            }

            
            #GameCard { background: #12101C; border: 1px solid #221E30; border-radius: 12px; }
            #GameCard:hover { border: 1px solid rgba(192, 113, 255, 0.5); background: #161422; }
            #GameCardSelected { background: #161422; border: 2px solid #C071FF; border-radius: 12px; }
            #Poster { background: transparent; border-radius: 8px; }
            #CardName { font-size: 11px; font-weight: 900; }
            #CardMeta { font-size: 10px; color: #888899; font-weight: 600; }
            #SavedMeta { font-size: 10px; color: #C071FF; font-weight: 800; }
            
            #RowName { font-size: 14px; font-weight: 900; color: #ffffff; }
            #RowMeta { font-size: 12px; color: #888899; font-weight: 700; }
            #RowSavedMeta { font-size: 12px; color: #C071FF; font-weight: 900; }
            
            #CardActionButton { padding: 8px 12px; border-radius: 8px; font-size: 11px; font-weight: 800; color: #C071FF; border: 1px solid rgba(192, 113, 255, 0.3); background: rgba(192, 113, 255, 0.05); }
            #CardActionButton:hover { background: rgba(192, 113, 255, 0.2); border-color: #C071FF; color: #FFFFFF; }
            #CardActionButton[state="disable"] { color: #FF6B6B; border: 1px solid rgba(255, 107, 107, 0.3); background: rgba(255, 107, 107, 0.05); }
            #CardActionButton[state="disable"]:hover { background: rgba(255, 107, 107, 0.2); border-color: #FF6B6B; color: #FFFFFF; }

            
            QTextEdit { background: #0F0E17; color: #bbbbcc; border: 1px solid #221E30; border-radius: 8px; font-family: Consolas, monospace; font-size: 11px; padding: 12px; }
            #TaskOverlay { background: rgba(5, 4, 10, 230); }
            #TaskOverlayPanel { background: #12101C; border: 1px solid #2B2640; border-radius: 20px; }
            #TaskOverlayTitle { color: #FFFFFF; font-size: 24px; font-weight: 900; }
            #TaskOverlayStatus { color: #888899; font-size: 13px; font-weight: 600; }
            #OverlayCancelButton { background: rgba(255, 107, 107, 0.1); border: 1px solid #FF6B6B; color: #FF6B6B; border-radius: 8px; font-weight: 800; }
            #OverlayCancelButton:hover { background: rgba(255, 107, 107, 0.25); color: #FFFFFF; }
            #OverlayDebugBox { background: #0B0A10; color: #aaaaaa; border: 1px solid #221E30; border-radius: 8px; font-family: Consolas; font-size: 10px; padding: 10px; }
            
            #TopActionButton { background: #181525; color: #FFFFFF; border: 1px solid #2B2640; border-radius: 8px; padding: 10px 14px; font-weight: 800; }
            #TopActionButton:hover { background: #231E36; color: #C071FF; border-color: #C071FF; }
            #ViewModeButton { background: transparent; color: #777788; border: 1px solid #2B2640; border-radius: 8px; padding: 10px 12px; font-weight: 800; }
            #ViewModeButton:hover { background: #161422; color: #FFFFFF; border-color: #777788; }
            #ViewModeButton:checked { background: rgba(192, 113, 255, 0.15); color: #C071FF; border-color: #C071FF; }
        """))

    def build_dashboard_page(self):
        page = QWidget()
        page.setObjectName("DashboardPage")
        layout = QVBoxLayout(page)
        self.dashboard_layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

                          
        top = QHBoxLayout()
        title = QLabel("Overview")
        title.setObjectName("Title")
        
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.dashboard_status = QLabel("● System Online")
        self.dashboard_status.setObjectName("DashboardStatus")
        status_row.addWidget(self.dashboard_status)
        
        top.addWidget(title)
        top.addStretch()
        top.addLayout(status_row)
        layout.addLayout(top)

                                               
        hero = QFrame()
        self.dashboard_hero = hero
        hero.setObjectName("DashboardHero")
        hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 20, 30, 20)

        self.dashboard_gauge = DashboardGauge()

                                                                
        background_panel = QFrame()
        background_panel.setObjectName("BackgroundCompressPanel")
        background_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        background_layout = QVBoxLayout(background_panel)
        background_layout.setAlignment(Qt.AlignVCenter)
        background_layout.setSpacing(12)

        self.background_compress_title = QLabel("Background Service")
        self.background_compress_title.setObjectName("PanelTitle")
        self.background_compress_title.setWordWrap(True)

        self.background_compress_hint = QLabel("Idle-aware autonomous compression\nfor undiscovered game libraries.")
        self.background_compress_hint.setObjectName("PanelDesc")

        self.background_task_progress = QProgressBar()
        self.background_task_progress.setObjectName("BackgroundEngineProgress")
        self.background_task_progress.setRange(0, 100)
        self.background_task_progress.setValue(0)
        self.background_task_progress.setTextVisible(True)
        self.background_task_progress.setFormat("Overall progress 0%")
        self.background_task_progress.setFixedHeight(26)

        self.background_completed_progress = QProgressBar()
        self.background_completed_progress.setObjectName("BackgroundEngineDataProgress")
        self.background_completed_progress.setRange(0, 100)
        self.background_completed_progress.setValue(0)
        self.background_completed_progress.setTextVisible(True)
        self.background_completed_progress.setFormat("Completed 0 GB / 0 GB")
        self.background_completed_progress.setFixedHeight(26)

        self.background_file_progress = QProgressBar()
        self.background_file_progress.setObjectName("BackgroundEngineFileProgress")
        self.background_file_progress.setRange(0, 100)
        self.background_file_progress.setValue(0)
        self.background_file_progress.setTextVisible(True)
        self.background_file_progress.setFormat("Files 0/0")
        self.background_file_progress.setFixedHeight(26)

        background_buttons = QVBoxLayout()
        background_buttons.setSpacing(10)

        self.background_compress_btn = QPushButton("Choose Games")
        self.background_compress_btn.setObjectName("PrimaryActionBtn")
        self.background_compress_btn.clicked.connect(self.open_background_compress_popup)

        self.background_worker_amount_label = QLabel("")
        self.background_worker_amount_label.setObjectName("PanelDesc")
        self.background_worker_amount_label.setAlignment(Qt.AlignCenter)

                                                                           
        active_actions = QHBoxLayout()
        active_actions.setSpacing(10)
        
        self.background_pause_btn = QPushButton("Pause")
        self.background_pause_btn.setObjectName("BackgroundPauseButton")
        self.background_pause_btn.clicked.connect(self.toggle_background_pause)

        self.background_cancel_btn = QPushButton("Cancel")
        self.background_cancel_btn.setObjectName("BackgroundCancelButton")
        self.background_cancel_btn.clicked.connect(self.cancel_background_compress_all)

        active_actions.addWidget(self.background_pause_btn)
        active_actions.addWidget(self.background_cancel_btn)

        background_buttons.addWidget(self.background_compress_btn)
        background_buttons.addWidget(self.background_worker_amount_label)
        background_buttons.addLayout(active_actions)

        background_layout.addWidget(self.background_compress_title)
        background_layout.addWidget(self.background_compress_hint)
        background_layout.addWidget(self.background_task_progress)
        background_layout.addWidget(self.background_completed_progress)
        background_layout.addWidget(self.background_file_progress)
        background_layout.addSpacing(15)
        background_layout.addLayout(background_buttons)
        
        hero_layout.addWidget(self.dashboard_gauge, stretch=1)
        hero_layout.addSpacing(20)
        hero_layout.addWidget(background_panel, stretch=1)
        
        self.update_background_controls()
        layout.addWidget(hero, stretch=2)
        self.dashboard_hero_index = layout.indexOf(hero)

                    
        cards = QHBoxLayout()
        self.dashboard_cards_layout = cards
        cards.setSpacing(20)
        self.dashboard_terminal_card = QFrame()
        self.dashboard_terminal_card.setObjectName("DashboardMiniCard")
        self.dashboard_terminal_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        terminal_layout = QVBoxLayout(self.dashboard_terminal_card)
        terminal_layout.setContentsMargins(20, 20, 20, 20)
        terminal_layout.setSpacing(8)

        self.dashboard_terminal_title = QLabel("Terminal")
        self.dashboard_terminal_title.setStyleSheet(f"color: {theme_color('info')}; font-weight: 800;")

        self.dashboard_terminal_box = QTextEdit()
        self.dashboard_terminal_box.setReadOnly(True)
        self.dashboard_terminal_box.setFixedHeight(130)

        terminal_layout.addWidget(self.dashboard_terminal_title)
        terminal_layout.addWidget(self.dashboard_terminal_box, stretch=1)

        cards.addWidget(self.dashboard_terminal_card, stretch=1)
        layout.addLayout(cards, stretch=1)
        self.dashboard_cards_index = layout.count() - 1
        
        return page

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, stretch=1)

                              
        left = QFrame()
        left.setObjectName("LeftPanel")
        left.setFixedWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(20, 30, 20, 20)
        left_layout.setSpacing(12)

        app_title = QLabel("X Z E N")
        app_title.setStyleSheet(f"color: {theme_color('text')}; font-size: 20px; font-weight: 900; letter-spacing: 4px; margin-bottom: 20px;")

        left_title = QLabel("MENU")
        left_title.setObjectName("NavTitle")

        self.nav = QListWidget()
        self.nav.setObjectName("PageNav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for label in ("Dashboard", "Game Library", "Upscaler Mods", "Settings"):
            self.nav.addItem(QListWidgetItem(label))
        
        left_layout.addWidget(app_title)
        left_layout.addWidget(left_title)
        left_layout.addWidget(self.nav)
        left_layout.addStretch()

                                                                          
        admin = QLabel("Admin Access: Yu-uh" if is_admin() else "Admin Access: Nu-uh")
        admin.setObjectName("AdminGood" if is_admin() else "AdminBad")
        admin.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(admin)

        body.addWidget(left)

                           
        main_content = QWidget()
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(30, 30, 30, 30)

        self.pages = QStackedWidget()
        self.overview_page = self.build_dashboard_page()
        self.game_library_page = XGCRGameLibraryPage(
            format_game_size,
            self.card_action_text,
            self.app_settings.get("library_view_mode", "grid"),
        )
        self.game_library_page.scan_steam_requested.connect(self.scan_steam_clicked)
        self.game_library_page.add_folder_requested.connect(self.add_folder)
        self.game_library_page.remove_selected_requested.connect(self.remove_selected)
        self.game_library_page.refresh_sizes_requested.connect(self.refresh_sizes_clicked)
        self.game_library_page.refresh_posters_requested.connect(self.start_poster_fetch)
        self.game_library_page.game_selected.connect(self.select_game)
        self.game_library_page.game_action_requested.connect(self.run_card_action)
        self.game_library_page.custom_poster_requested.connect(self.set_custom_poster)
        self.game_library_page.view_mode_changed.connect(self.apply_library_view_mode)
        self.apply_terminal_visibility()

        self.fsr_mods_page = None
        self.fsr_mods_placeholder = self.build_fsr_placeholder()

        self.settings_page = XGCRSettingsPage(
            COMPRESSION_ALGORITHMS,
            self.selected_compression_algorithm(),
            bool(self.app_settings.get("show_terminal", False)),
            bool(self.app_settings.get("launch_as_admin", DEFAULT_LAUNCH_AS_ADMIN)),
            bool(self.app_settings.get("smart_game_pause", AUTO_PAUSE_WHEN_GAME_RUNNING)),
            bool(self.app_settings.get("close_to_tray", False)),
            normalized_worker_mode(self.app_settings.get("worker_mode", DEFAULT_WORKER_MODE)),
            normalized_worker_count(self.app_settings.get("worker_count", DEFAULT_WORKER_COUNT)),
        )
        self.settings_page.settings_changed.connect(self.apply_settings_values)

        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.game_library_page)
        self.pages.addWidget(self.fsr_mods_placeholder)
        self.pages.addWidget(self.settings_page)
        self.nav.currentRowChanged.connect(self.handle_page_changed)
        self.nav.currentRowChanged.connect(self.update_loading_overlay_visibility)
        self.nav.setCurrentRow(0)
        
        main_layout.addWidget(self.pages)
        body.addWidget(main_content, stretch=1)
        
        self.build_loading_overlay()
        self.build_saved_space_toast()
        self.build_quick_stats_overlay()
        self.setup_quick_stats_shortcuts()
        self.sync_titlebar_state()

    def build_fsr_placeholder(self):
        page = QWidget()
        page.setObjectName("DashboardPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch()
        label = QLabel("Upscaler Mods")
        label.setObjectName("Title")
        label.setAlignment(Qt.AlignCenter)
        hint = QLabel("Loading when opened...")
        hint.setObjectName("DashboardStatus")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        layout.addWidget(hint)
        layout.addStretch()
        return page

    def setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = self.windowIcon()
        if icon.isNull() and APP_ICON_FILE.exists():
            icon = QIcon(str(APP_ICON_FILE))

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(APP_NAME)

        tray_menu = QMenu(self)
        open_action = QAction("Open Xzen", self)
        hide_action = QAction("Hide to Tray", self)
        exit_action = QAction("Exit", self)

        open_action.triggered.connect(self.restore_from_tray)
        hide_action.triggered.connect(self.hide_to_tray)
        exit_action.triggered.connect(self.exit_application)

        tray_menu.addAction(open_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def hide_to_tray(self):
        if self.tray_icon:
            self.hide()
        else:
            self.showMinimized()

    def exit_application(self):
        self.force_exit = True
        app = QApplication.instance()
        if app:
            app.quit()
        else:
            self.close()

    def restore_from_tray(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_from_tray()

    def ensure_fsr_mods_page(self):
        if self.fsr_mods_page is not None:
            return

        from source.tabs.xgcr_fsr_mods import XGCRFsrModsPage

        self.fsr_mods_page = XGCRFsrModsPage(
            get_games_func=lambda: self.games,
            get_selected_index_func=lambda: self.selected_index if self.selected_index is not None else -1,
            external_log_func=self.log,
        )
        placeholder_index = self.pages.indexOf(self.fsr_mods_placeholder)
        self.pages.removeWidget(self.fsr_mods_placeholder)
        self.fsr_mods_placeholder.deleteLater()
        self.pages.insertWidget(placeholder_index, self.fsr_mods_page)

    def handle_page_changed(self, index):
        if index < 0:
            return

        if index == 2:
            self.ensure_fsr_mods_page()
        self.pages.setCurrentIndex(index)
        if hasattr(self, "game_library_page") and index != 1:
            self.game_library_page.set_busy_overlay(False)
        if index == 1 and self.game_library_refresh_pending:
            QTimer.singleShot(0, lambda: self.refresh_grid(force=True))
        self.update_game_library_busy_overlay()

    def build_loading_overlay(self):
        self.loading_overlay = QWidget(self.centralWidget())
        self.loading_overlay.setObjectName("TaskOverlay")
        self.loading_overlay.setAttribute(Qt.WA_StyledBackground, True)
        self.loading_overlay.hide()
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setContentsMargins(24, 24, 24, 24)
        overlay_layout.addStretch()

        panel = QFrame()
        panel.setObjectName("TaskOverlayPanel")
        panel.setFixedWidth(500)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(32, 28, 32, 28)
        panel_layout.setSpacing(14)

        self.loading_title = QLabel("Compressing")
        self.loading_title.setObjectName("TaskOverlayTitle")
        self.loading_title.setAlignment(Qt.AlignCenter)
        self.loading_status = QLabel("Preparing...")
        self.loading_status.setObjectName("TaskOverlayStatus")
        self.loading_status.setAlignment(Qt.AlignCenter)
        self.loading_status.setWordWrap(True)
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 100)
        self.loading_progress.setValue(0)
        self.loading_file_progress = QProgressBar()
        self.loading_file_progress.setObjectName("FileProgressBar")
        self.loading_file_progress.setRange(0, 100)
        self.loading_file_progress.setValue(0)
        self.loading_file_progress.setTextVisible(False)
        self.loading_debug_box = QTextEdit()
        self.loading_debug_box.setObjectName("OverlayDebugBox")
        self.loading_debug_box.setReadOnly(True)
        self.loading_debug_box.setFixedHeight(120)
        self.loading_cancel_btn = QPushButton("Cancel")
        self.loading_cancel_btn.setObjectName("OverlayCancelButton")
        self.loading_cancel_btn.clicked.connect(self.cancel_compact_task)

        panel_layout.addWidget(self.loading_title)
        panel_layout.addWidget(self.loading_status)
        panel_layout.addWidget(self.loading_progress)
        panel_layout.addWidget(self.loading_file_progress)
        panel_layout.addWidget(self.loading_debug_box)
        panel_layout.addWidget(self.loading_cancel_btn)
        overlay_layout.addWidget(panel, alignment=Qt.AlignCenter)
        overlay_layout.addStretch()
        self.position_loading_overlay()

    def position_loading_overlay(self):
        if hasattr(self, "loading_overlay"):
            if hasattr(self, "pages"):
                top_left = self.pages.mapTo(self.centralWidget(), self.pages.rect().topLeft())
                page_rect = QRect(top_left, self.pages.size())
            else:
                page_rect = self.centralWidget().rect()
            self.loading_overlay.setGeometry(page_rect)
            self.loading_overlay.raise_()

    def toggle_maximize_restore(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.sync_titlebar_state()

    def sync_titlebar_state(self):
        if not hasattr(self, "title_bar"):
            return
        self.title_bar.max_button.setText("❐" if self.isMaximized() else "□")

    def update_loading_overlay_visibility(self):
        if not hasattr(self, "loading_overlay"):
            return
        if getattr(self, "loading_overlay_active", False) and self.nav.currentRow() == 1:
            self.position_loading_overlay()
            self.loading_overlay.show()
        else:
            self.loading_overlay.hide()

    def build_saved_space_toast(self):
        self.saved_space_toast = QFrame(self.centralWidget())
        self.saved_space_toast.setObjectName("DashboardHotPill")
        self.saved_space_toast.setFixedHeight(74)
        self.saved_space_toast.hide()
        self.saved_space_toast_anchor_pos = QPoint(0, 0)
        self.saved_space_toast_hidden_pos = QPoint(0, 0)

        toast_layout = QVBoxLayout(self.saved_space_toast)
        toast_layout.setContentsMargins(22, 12, 22, 12)
        toast_layout.setSpacing(2)

        self.saved_space_toast_game = QLabel("")
        self.saved_space_toast_game.setObjectName("DashboardHotPillGame")
        self.saved_space_toast_saved = QLabel("")
        self.saved_space_toast_saved.setObjectName("DashboardHotPillSaved")

        toast_layout.addWidget(self.saved_space_toast_game)
        toast_layout.addWidget(self.saved_space_toast_saved)

        self.saved_space_toast_opacity = QGraphicsOpacityEffect(self.saved_space_toast)
        self.saved_space_toast.setGraphicsEffect(self.saved_space_toast_opacity)
        self.saved_space_toast_opacity.setOpacity(0.0)

        self.saved_space_toast_slide_in = QPropertyAnimation(self.saved_space_toast, b"pos", self)
        self.saved_space_toast_slide_in.setDuration(260)
        self.saved_space_toast_slide_in.setEasingCurve(QEasingCurve.OutCubic)

        self.saved_space_toast_slide_out = QPropertyAnimation(self.saved_space_toast, b"pos", self)
        self.saved_space_toast_slide_out.setDuration(360)
        self.saved_space_toast_slide_out.setEasingCurve(QEasingCurve.InCubic)

        self.saved_space_toast_fade_out = QPropertyAnimation(self.saved_space_toast_opacity, b"opacity", self)
        self.saved_space_toast_fade_out.setDuration(360)
        self.saved_space_toast_fade_out.setEasingCurve(QEasingCurve.InOutCubic)

        self.saved_space_toast_exit_group = QParallelAnimationGroup(self)
        self.saved_space_toast_exit_group.addAnimation(self.saved_space_toast_slide_out)
        self.saved_space_toast_exit_group.addAnimation(self.saved_space_toast_fade_out)
        self.saved_space_toast_exit_group.finished.connect(self.saved_space_toast.hide)

        self.saved_space_toast_timer = QTimer(self)
        self.saved_space_toast_timer.setSingleShot(True)
        self.saved_space_toast_timer.timeout.connect(self.start_saved_space_toast_exit)
        self.position_saved_space_toast()
        self.saved_space_toast.move(self.saved_space_toast_hidden_pos)

    def position_saved_space_toast(self):
        if not hasattr(self, "saved_space_toast"):
            return

        if hasattr(self, "pages"):
            top_left = self.pages.mapTo(self.centralWidget(), self.pages.rect().topLeft())
            page_rect = QRect(top_left, self.pages.size())
        else:
            page_rect = self.centralWidget().rect()

        margin = 24
        max_width = max(360, int(page_rect.width() * 0.62))
        self.saved_space_toast.setMaximumWidth(max_width)
        self.saved_space_toast.adjustSize()

        x = page_rect.x() + page_rect.width() - self.saved_space_toast.width() - margin
        y = page_rect.y() + margin
        self.saved_space_toast_anchor_pos = QPoint(max(margin, x), max(margin, y))
        self.saved_space_toast_hidden_pos = QPoint(
            page_rect.x() + page_rect.width() + self.saved_space_toast.width() + margin,
            self.saved_space_toast_anchor_pos.y(),
        )

        if not self.saved_space_toast.isVisible():
            self.saved_space_toast.move(self.saved_space_toast_hidden_pos)
            return

        if self.saved_space_toast_exit_group.state() == QAbstractAnimation.Running:
            return
        if self.saved_space_toast_slide_in.state() == QAbstractAnimation.Running:
            self.saved_space_toast_slide_in.setEndValue(self.saved_space_toast_anchor_pos)
            return
        self.saved_space_toast.move(self.saved_space_toast_anchor_pos)

    def show_saved_space_toast(self, game_name, saved_bytes):
        saved_text = format_game_size(max(0, int(saved_bytes or 0)))
        self.show_hotpill_toast(game_name, f"Saved {saved_text}")

    def show_hotpill_toast(self, game_name, detail_text):
        if not hasattr(self, "saved_space_toast"):
            return

        game_text = str(game_name or "Game")
        detail_line = str(detail_text or "").strip()
        self.saved_space_toast_game.setText(game_text)
        self.saved_space_toast_saved.setText(detail_line or "Done")

        self.saved_space_toast_timer.stop()
        self.saved_space_toast_slide_in.stop()
        self.saved_space_toast_exit_group.stop()
        self.saved_space_toast_slide_out.stop()
        self.saved_space_toast_fade_out.stop()
        self.saved_space_toast_timer.stop()
        self.saved_space_toast_opacity.setOpacity(1.0)
        self.position_saved_space_toast()
        self.saved_space_toast.move(self.saved_space_toast_hidden_pos)
        self.saved_space_toast.show()
        self.saved_space_toast.raise_()
        self.saved_space_toast_slide_in.setStartValue(self.saved_space_toast_hidden_pos)
        self.saved_space_toast_slide_in.setEndValue(self.saved_space_toast_anchor_pos)
        self.saved_space_toast_slide_in.start()
        self.saved_space_toast_timer.start(2800)

    def start_saved_space_toast_exit(self):
        if not hasattr(self, "saved_space_toast_exit_group"):
            return
        self.position_saved_space_toast()
        current_pos = self.saved_space_toast.pos()
        if self.saved_space_toast_slide_in.state() == QAbstractAnimation.Running:
            self.saved_space_toast_slide_in.stop()

        self.saved_space_toast_slide_out.setStartValue(current_pos)
        self.saved_space_toast_slide_out.setEndValue(self.saved_space_toast_hidden_pos)
        self.saved_space_toast_fade_out.setStartValue(float(self.saved_space_toast_opacity.opacity()))
        self.saved_space_toast_fade_out.setEndValue(0.0)
        self.saved_space_toast_exit_group.start()

    def setup_quick_stats_shortcuts(self):
        if os.name == "nt":
            QTimer.singleShot(0, self.setup_global_insert_hotkey)
        else:
            self.quick_stats_toggle_shortcut = QShortcut(QKeySequence("Insert"), self)
            self.quick_stats_toggle_shortcut.setContext(Qt.ApplicationShortcut)
            self.quick_stats_toggle_shortcut.activated.connect(self.toggle_quick_stats_window)

        self.quick_stats_close_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.quick_stats_close_shortcut.setContext(Qt.ApplicationShortcut)
        self.quick_stats_close_shortcut.activated.connect(self.hide_quick_stats_window)

    def setup_global_insert_hotkey(self):
        if os.name != "nt" or self.global_insert_hotkey_registered:
            return
        try:
            hwnd = int(self.winId())
            if hwnd <= 0:
                return
            user32 = ctypes.windll.user32
            MOD_NOREPEAT = 0x4000
            VK_INSERT = 0x2D
            if user32.RegisterHotKey(hwnd, self.global_insert_hotkey_id, MOD_NOREPEAT, VK_INSERT):
                self.global_insert_hotkey_registered = True
                return
                                                          
            if user32.RegisterHotKey(hwnd, self.global_insert_hotkey_id, 0, VK_INSERT):
                self.global_insert_hotkey_registered = True
                return
            self.log("Global Insert hotkey registration failed.")
        except Exception as e:
            self.log(f"Global Insert hotkey setup failed: {e}")

    def unregister_global_insert_hotkey(self):
        if os.name != "nt" or not self.global_insert_hotkey_registered:
            return
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, self.global_insert_hotkey_id)
        except Exception:
            pass
        self.global_insert_hotkey_registered = False

    def build_quick_stats_overlay(self):
        self.quick_stats_window = QuickStatsFloatingWindow()
        self.quick_stats_window.hide()
        self.position_quick_stats_overlay()

    def position_quick_stats_overlay(self):
        if not hasattr(self, "quick_stats_window") or self.quick_stats_window is None:
            return
        if self.quick_stats_window.user_moved:
            return
        pos = self.mapToGlobal(QPoint(self.width() - self.quick_stats_window.width() - 24, 64))
        self.quick_stats_window.move(pos)

    def toggle_quick_stats_window(self):
        if not hasattr(self, "quick_stats_window"):
            return
        if self.quick_stats_window.isVisible():
            self.hide_quick_stats_window()
            return
        self.show_quick_stats_window()

    def show_quick_stats_window(self):
        if not hasattr(self, "quick_stats_window"):
            return
        self.refresh_quick_stats_overlay()
        self.position_quick_stats_overlay()
        self.quick_stats_window.show()
        self.quick_stats_window.raise_()

    def hide_quick_stats_window(self):
        if hasattr(self, "quick_stats_window") and self.quick_stats_window.isVisible():
            self.quick_stats_window.hide()

    def refresh_quick_stats_overlay(self):
        if not hasattr(self, "quick_stats_window"):
            return

        total_saved = 0
        for game in self.games:
            total_saved += int(self.background_saved_bytes(game) or 0)
        self.quick_stats_window.saved_value.setText(format_game_size(total_saved))

        status_text = "Idle"
        status_color = theme_color("accent")
        suspended_lines = []
        worker_lines = []
        if self.background_compress_active:
            action_text = "Tasks"
            if self.background_current_action == "compress":
                action_text = "Compression"
            elif self.background_current_action == "decompress":
                action_text = "Decompression"
            elif self.background_current_action == "cleanup":
                action_text = "Cleanup"

            if getattr(self, "background_game_pause_active", False):
                status_text = f"Game Detected | Background {action_text} Paused"
                suspended_lines, worker_lines = self.compact_suspension_lines()
                status_color = theme_color("danger_text")
            elif self.background_compress_paused:
                status_text = f"Background {action_text} Paused"
                suspended_lines, worker_lines = self.compact_suspension_lines()
                status_color = theme_color("warning")
            else:
                status_text = f"Background {action_text} Running"
                status_color = theme_color("accent")
        elif self.busy and self.compact_worker:
            action_label = getattr(self.compact_worker, "action_label", "Working")
            game_name = "Current Selection"
            if self.selected_index is not None and 0 <= self.selected_index < len(self.games):
                game_name = self.games[self.selected_index].get("name", "Current Selection")
            if getattr(self, "foreground_pause_active", False):
                status_text = f"Game Detected | {action_label} Paused"
                suspended_lines, worker_lines = self.compact_suspension_lines()
                status_color = theme_color("danger_text")
            else:
                status_text = f"{action_label} {game_name}"
                status_color = theme_color("info")
        else:
            status_text = "System Online"
            status_color = theme_color("success")

        self.quick_stats_window.status_value.setText(status_text)
        self.quick_stats_window.status_value.setStyleSheet(
            f"color: {status_color}; font-size: 12px; font-weight: 900;"
        )
        if suspended_lines:
            self.quick_stats_window.suspended_header.show()
            self.quick_stats_window.suspended_list.setText("\n".join(suspended_lines))
            self.quick_stats_window.suspended_list.show()
        else:
            self.quick_stats_window.suspended_header.hide()
            self.quick_stats_window.suspended_list.clear()
            self.quick_stats_window.suspended_list.hide()
        if worker_lines:
            self.quick_stats_window.worker_header.show()
            self.quick_stats_window.worker_value.setText("\n".join(worker_lines))
            self.quick_stats_window.worker_value.show()
        else:
            self.quick_stats_window.worker_header.hide()
            self.quick_stats_window.worker_value.clear()
            self.quick_stats_window.worker_value.hide()

        self.quick_stats_window.adjustSize()
        if not self.quick_stats_window.user_moved:
            self.position_quick_stats_overlay()

    def compact_suspension_lines(self):
        worker = getattr(self, "compact_worker", None)
        if not worker:
            return [], []
        try:
            suspended_pids = sorted(int(pid) for pid in (getattr(worker, "suspended_pids", set()) or set()))
        except Exception:
            suspended_pids = []

        capacity = int(getattr(self, "background_worker_capacity", 0) or getattr(worker, "max_workers", 0) or 0)
        paused = (
            getattr(self, "background_game_pause_active", False)
            or getattr(self, "background_compress_paused", False)
            or getattr(self, "foreground_pause_active", False)
        )
        if not suspended_pids and not paused:
            return [], []

        label = "Compression"
        action = str(getattr(worker, "action_label", "") or "").lower()
        if "decompress" in action:
            label = "Decompression"
        elif getattr(self, "background_current_action", "") == "cleanup":
            label = "Cleanup"

        amount = len(suspended_pids)
        worker_lines = [f"Frozen: 0/{capacity}"] if capacity else []
        return [f"{label}: {amount} suspended"], worker_lines

    def show_loading_overlay(self, title, status):
        self.loading_title.setText(title)
        self.loading_status.setText(status)
        self.loading_progress.setValue(0)
        self.loading_file_progress.setValue(0)
        self.loading_active_chunks = {}
        self.loading_debug_box.setPlainText("Waiting for compact workers...")
        self.loading_cancel_btn.setEnabled(True)
        self.loading_cancel_btn.setText("Cancel")
        self.loading_overlay_active = True
        self.foreground_task_progress_value = 0
        self.foreground_task_progress_text = f"{title} 0%"
        self.foreground_status_text = status
        self.foreground_file_progress_value = 0
        self.foreground_file_progress_text = "Files 0/0"
        self.foreground_pause_active = False
        self.foreground_pause_name = ""
        self.foreground_pause_reason = ""
        self.update_loading_overlay_visibility()
        self.update_dashboard()

    def update_loading_overlay(self, percent, status, processed, total):
        percent = max(0, min(100, int(percent or 0)))
        self.loading_progress.setValue(percent)
        action_label = getattr(self.compact_worker, "action_label", "Working") if self.compact_worker else "Working"
        self.foreground_task_progress_value = percent
        self.foreground_task_progress_text = f"{action_label} {percent}%"
        self.foreground_status_text = str(status or action_label)
        if total:
            file_percent = int((processed / total) * 100)
            file_percent = max(0, min(100, file_percent))
            self.loading_file_progress.setValue(file_percent)
            self.loading_status.setText(f"{status}\n{processed}/{total} files")
            self.foreground_file_progress_value = file_percent
            self.foreground_file_progress_text = f"Files {processed}/{total}"
        else:
            self.loading_file_progress.setValue(0)
            self.loading_status.setText(status)
            self.foreground_file_progress_value = 0
            self.foreground_file_progress_text = "Files 0/0"
        self.update_dashboard()

    def update_active_files(self, chunk_id, state, files):
        if not hasattr(self, "loading_active_chunks"):
            self.loading_active_chunks = {}
        if state == "start":
            self.loading_active_chunks[chunk_id] = files
        else:
            self.loading_active_chunks.pop(chunk_id, None)
        if not self.loading_active_chunks:
            capacity = getattr(self.compact_worker, "max_workers", 0) if self.compact_worker else 0
            suffix = f" 0/{capacity}" if capacity else ""
            self.loading_debug_box.setPlainText(f"No active compact workers right now.{suffix}")
            return

        capacity = getattr(self.compact_worker, "max_workers", 0) if self.compact_worker else 0
        lines = [f"Active compact workers {len(self.loading_active_chunks)}/{capacity or len(self.loading_active_chunks)}"]
        for active_chunk_id, active_files in sorted(self.loading_active_chunks.items()):
            total_size = sum(file_size for _, file_size in active_files)
            lines.append(f"Worker chunk {active_chunk_id} | {len(active_files)} file(s) | {format_game_size(total_size)}")
            for file_path, file_size in active_files:
                relative_path = os.path.relpath(file_path, self.compact_worker.target_path)
                lines.append(f"  {format_game_size(file_size)}  {relative_path}")
        self.loading_debug_box.setPlainText("\n".join(lines))

    def hide_loading_overlay(self):
        self.loading_overlay_active = False
        self.loading_overlay.hide()
        self.foreground_task_progress_value = 0
        self.foreground_task_progress_text = "Overall progress 0%"
        self.foreground_status_text = ""
        self.foreground_file_progress_value = 0
        self.foreground_file_progress_text = "Files 0/0"
        self.foreground_pause_active = False
        self.foreground_pause_name = ""
        self.foreground_pause_reason = ""
        self.update_dashboard()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_loading_overlay()
        self.position_saved_space_toast()
        if hasattr(self, "quick_stats_window") and self.quick_stats_window.isVisible():
            self.position_quick_stats_overlay()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "quick_stats_window") and self.quick_stats_window.isVisible():
            self.position_quick_stats_overlay()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self.sync_titlebar_state()

    def nativeEvent(self, event_type, message):
        if os.name == "nt" and self.global_insert_hotkey_registered:
            try:
                if event_type not in ("windows_dispatcher_MSG", b"windows_dispatcher_MSG", "windows_generic_MSG", b"windows_generic_MSG"):
                    return super().nativeEvent(event_type, message)
                msg_ptr = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG))
                msg = msg_ptr.contents
                WM_HOTKEY = 0x0312
                if msg.message == WM_HOTKEY and int(msg.wParam) == self.global_insert_hotkey_id:
                    self.toggle_quick_stats_window()
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        if (
            not self.force_exit
            and bool(self.app_settings.get("close_to_tray", False))
            and self.tray_icon
        ):
            event.ignore()
            self.hide_to_tray()
            return

        self.unregister_global_insert_hotkey()
        if hasattr(self, "quick_stats_window") and self.quick_stats_window is not None:
            self.quick_stats_window.close()
        if self.tray_icon:
            self.tray_icon.hide()
        super().closeEvent(event)

    def log(self, text):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        self.game_library_page.log(line)
        if hasattr(self, "dashboard_terminal_box"):
            self.dashboard_terminal_box.append(line)
        if hasattr(self, "event_logger"):
            self.event_logger.info("ui_log", message=str(text))
        lower = str(text).lower()
        if any(token in lower for token in ("failed", "error", "exception", "could not", "invalid")):
            log_error("main", "ui_log", str(text))
        elif any(token in lower for token in ("warning", "skipped", "cancelled", "paused", "missing")):
            log_warning("main", "ui_log", str(text))
        elif any(token in lower for token in ("complete", "finished", "updated", "saved", "set:", "added", "removed")):
            log_success("main", "ui_log", str(text))
        else:
            log_action("debug", "main", "ui_log", str(text))

    def retain_worker_until_finished(self, worker):
        if worker is None:
            return
        self.worker_refs.append(worker)

        def release_worker():
            if worker in self.worker_refs:
                self.worker_refs.remove(worker)
            worker.deleteLater()

        worker.finished.connect(release_worker)

    def apply_terminal_visibility(self):
        visible = bool(self.app_settings.get("show_terminal", False))
        if hasattr(self, "game_library_page"):
            self.game_library_page.set_terminal_visible(visible)
        if hasattr(self, "dashboard_terminal_card"):
            self.dashboard_terminal_card.setVisible(visible)
        self.apply_dashboard_terminal_layout(visible)

    def apply_dashboard_terminal_layout(self, visible):
        if not hasattr(self, "dashboard_layout"):
            return
        hero_index = getattr(self, "dashboard_hero_index", -1)
        cards_index = getattr(self, "dashboard_cards_index", -1)
        if hero_index >= 0:
            self.dashboard_layout.setStretch(hero_index, 2 if visible else 6)
        if cards_index >= 0:
            self.dashboard_layout.setStretch(cards_index, 1 if visible else 0)
        if hasattr(self, "dashboard_cards_layout"):
            self.dashboard_cards_layout.setStretch(0, 1 if visible else 0)
        if hasattr(self, "dashboard_gauge"):
            self.dashboard_gauge.setMinimumHeight(280 if visible else 340)
            self.dashboard_gauge.updateGeometry()
            self.dashboard_gauge.update()
        if hasattr(self, "dashboard_hero"):
            self.dashboard_hero.updateGeometry()
        self.dashboard_layout.invalidate()

    def load_settings(self):
        return load_app_settings(SETTINGS_FILE)

    def save_settings(self):
        try:
            save_app_settings(self.app_settings, SETTINGS_FILE)
        except Exception as e:
            self.log(f"Settings save failed: {e}")

    def selected_compression_algorithm(self):
        key = self.app_settings.get("compression_algorithm", DEFAULT_COMPRESSION_ALGORITHM)
        if key not in compression_algorithm_keys():
            key = DEFAULT_COMPRESSION_ALGORITHM
        return key

    def selected_compression_label(self):
        return compression_algorithm_label(self.selected_compression_algorithm())

    def update_compress_button_text(self):
        if hasattr(self, "game_library_page"):
            self.refresh_grid()

    def is_game_compressed(self, game):
        return state_is_game_compressed(game)

    def background_game_key(self, game):
        return state_background_game_key(game)

    def card_action_text(self, game):
        if self.is_game_compressed(game):
            return "Decompress"
        return f"Compress {self.selected_compression_algorithm()}"

    def open_settings(self):
        if hasattr(self, "nav"):
            self.nav.setCurrentRow(3)

    def apply_settings_values(self, values):
        if values.get("compression_algorithm") in compression_algorithm_keys():
            self.app_settings["compression_algorithm"] = values["compression_algorithm"]
        self.app_settings["worker_mode"] = normalized_worker_mode(values.get("worker_mode", DEFAULT_WORKER_MODE))
        self.app_settings["worker_count"] = normalized_worker_count(values.get("worker_count", DEFAULT_WORKER_COUNT))
        self.app_settings["show_terminal"] = bool(values.get("show_terminal", False))
        self.app_settings["smart_game_pause"] = bool(values.get("smart_game_pause", AUTO_PAUSE_WHEN_GAME_RUNNING))
        self.app_settings["close_to_tray"] = bool(values.get("close_to_tray", False))
        self.app_settings["launch_as_admin"] = bool(values.get("launch_as_admin", DEFAULT_LAUNCH_AS_ADMIN))
        self.save_settings()
        self.apply_terminal_visibility()
        self.update_compress_button_text()
        self.update_dashboard()
        resolved_workers = resolve_worker_count(
            self.app_settings.get("worker_mode", DEFAULT_WORKER_MODE),
            self.app_settings.get("worker_count", DEFAULT_WORKER_COUNT),
        )
        self.log(f"Settings updated. Compression algorithm: {self.selected_compression_algorithm()}. Workers: {resolved_workers}.")

    def apply_library_view_mode(self, mode):
        self.app_settings["library_view_mode"] = "rows" if mode == "rows" else "grid"
        self.save_settings()

    def save_games(self):
        try:
            state_save_games(self.games, DATA_FILE)
        except Exception as e:
            self.log(f"Save failed: {e}")

    def saved_game_is_installed(self, game):
        return state_saved_game_is_installed(game)

    def prune_uninstalled_games(self):
        self.games, removed = state_prune_uninstalled_games(self.games, self.saved_game_is_installed)

        if self.selected_index is not None and self.selected_index >= len(self.games):
            self.selected_index = None

        return removed

    def load_games(self):
        self.games = state_load_games(DATA_FILE)
        before_dedupe = len(self.games)
        self.games = state_dedupe_games(self.games)
        deduped_removed = max(0, before_dedupe - len(self.games))
        removed = self.prune_uninstalled_games()
        if deduped_removed or removed:
            self.save_games()
        if deduped_removed:
            self.log(f"Removed {deduped_removed} duplicate game entr{'y' if deduped_removed == 1 else 'ies'} from the library.")
        if removed:
            self.log(f"Removed {removed} uninstalled game(s) from the saved library.")

    def add_or_update_game(self, game):
        path_allowed = self.manual_path_allowed if hasattr(self, "manual_path_allowed") else safe_path
        return state_add_or_update_game(self.games, game, path_allowed)

    def update_dashboard(self):
        total_original = 0
        total_saved = 0
        for game in self.games:
            saved_bytes = int(self.background_saved_bytes(game) or 0)
            if saved_bytes > 0:
                total_original += int(state_original_game_size(game) or 0)
                total_saved += saved_bytes
        if hasattr(self, "dashboard_gauge"):
            self.dashboard_gauge.set_values(total_saved, total_original)
        if hasattr(self, "dashboard_status"):
            if self.background_compress_active:
                action_text = "Tasks"
                if self.background_current_action == "compress":
                    action_text = "Compression"
                elif self.background_current_action == "decompress":
                    action_text = "Decompression"
                elif self.background_current_action == "cleanup":
                    action_text = "Cleanup"
                if getattr(self, "background_game_pause_active", False):
                    self.dashboard_status.setText(f"● Game Detected - Background {action_text} Paused")
                    self.dashboard_status.setStyleSheet(status_pill_style("danger_text", 0.14))
                elif self.background_compress_paused:
                    self.dashboard_status.setText(f"● Background {action_text} Paused")
                    self.dashboard_status.setStyleSheet(status_pill_style("warning", 0.12))
                else:
                    self.dashboard_status.setText(f"● Background {action_text} Running")
                    self.dashboard_status.setStyleSheet(status_pill_style("accent", 0.10))
            elif self.busy and self.compact_worker:
                action_label = getattr(self.compact_worker, "action_label", "Working")
                if getattr(self, "foreground_pause_active", False):
                    self.dashboard_status.setText(f"● Game Detected - {action_label} Paused")
                    self.dashboard_status.setStyleSheet(status_pill_style("danger_text", 0.14))
                else:
                    self.dashboard_status.setText(f"● {action_label}")
                    self.dashboard_status.setStyleSheet(status_pill_style("info", 0.12))
            else:
                self.dashboard_status.setText("● System Online")
                self.dashboard_status.setStyleSheet(status_pill_style("success", 0.10))
        if hasattr(self, "background_compress_btn"):
            self.update_background_controls()
        if hasattr(self, "quick_stats_window") and self.quick_stats_window.isVisible():
            self.refresh_quick_stats_overlay()

    def update_background_controls(self):
        active = bool(getattr(self, "background_compress_active", False))
        foreground_active = bool(getattr(self, "busy", False) and getattr(self, "compact_worker", None))
        manual_paused = bool(getattr(self, "background_compress_paused", False))
        game_paused = bool(getattr(self, "background_game_pause_active", False))
        paused = manual_paused or game_paused

        if foreground_active and not active:
            foreground_paused = bool(getattr(self, "foreground_pause_active", False))
            self.background_compress_btn.setVisible(False)
            self.background_worker_amount_label.setVisible(False)
            self.background_pause_btn.setVisible(False)
            self.background_cancel_btn.setVisible(False)
            self.background_task_progress.setVisible(True)
            self.background_completed_progress.setVisible(False)
            self.background_file_progress.setVisible(True)

            action_label = getattr(self.compact_worker, "action_label", "Working")
            game_name = "current game"
            if self.selected_index is not None and 0 <= self.selected_index < len(self.games):
                game_name = self.games[self.selected_index].get("name", game_name)

            title_prefix = "Paused" if foreground_paused else action_label
            self.background_compress_title.setText(f"{title_prefix}: {game_name}")
            if foreground_paused:
                detected_name = getattr(self, "foreground_pause_name", "") or "game"
                capacity = int(getattr(self, "background_worker_capacity", 0) or 0)
                worker_text = f" | Workers frozen 0/{capacity}" if capacity else ""
                self.background_compress_hint.setText(f"Game detected: {detected_name}{worker_text}")
            else:
                self.background_compress_hint.setText((self.foreground_status_text or action_label).splitlines()[0])
            self.background_task_progress.setValue(max(0, min(100, int(self.foreground_task_progress_value or 0))))
            self.background_task_progress.setFormat(self.foreground_task_progress_text)
            self.background_file_progress.setValue(max(0, min(100, int(self.foreground_file_progress_value or 0))))
            self.background_file_progress.setFormat(self.foreground_file_progress_text)
            return

        self.background_compress_btn.setVisible(not active)
        self.background_worker_amount_label.setVisible(not active)
        self.background_pause_btn.setVisible(active)
        self.background_cancel_btn.setVisible(active)
        self.background_pause_btn.setText("Resume" if manual_paused else "Pause")

        if not active:
            self.background_compress_title.setText("Background Service")
            self.background_compress_hint.setText("Idle-aware autonomous compression\nfor undiscovered game libraries.")
            self.background_task_progress.setVisible(False)
            self.background_completed_progress.setVisible(False)
            self.background_file_progress.setVisible(False)
            self.update_background_picker_label()
            return

        self.background_task_progress.setVisible(True)
        self.background_completed_progress.setVisible(True)
        self.background_file_progress.setVisible(True)
        self.background_task_progress.setValue(max(0, min(100, int(self.background_task_progress_value or 0))))
        self.background_task_progress.setFormat(self.background_task_progress_text)
        self.background_completed_progress.setValue(max(0, min(100, int(self.background_completed_progress_value or 0))))
        self.background_completed_progress.setFormat(self.background_completed_progress_text)
        self.background_file_progress.setValue(max(0, min(100, int(self.background_file_progress_value or 0))))
        self.background_file_progress.setFormat(self.background_file_progress_text)

        current = max(0, self.background_total - len(self.background_queue))
        action_text = {
            "compress": "Compressing",
            "decompress": "Decompressing",
            "cleanup": "Cleaning up",
        }.get(getattr(self, "background_current_action", ""), "Processing")
        game_name = ""
        current_index = getattr(self, "background_current_index", None)
        if current_index is not None and 0 <= int(current_index) < len(self.games):
            game_name = self.games[int(current_index)].get("name", "")
        if not game_name and game_paused:
            game_name = getattr(self, "background_game_pause_name", "")
        game_name = str(game_name or "current game")
        title_prefix = "Paused" if paused else action_text
        if paused:
            self.background_compress_title.setText(f"{title_prefix}: {action_text} {game_name}")
        else:
            self.background_compress_title.setText(f"{action_text}: {game_name}")

        if self.background_progress_summary:
            worker_text = ""
            if self.background_worker_capacity:
                worker_text = f" | Workers {self.background_worker_active}/{self.background_worker_capacity}"
            game_text = ""
            if game_paused:
                detected_name = getattr(self, "background_game_pause_name", "") or game_name
                game_text = f" | Game detected: {detected_name}"
            self.background_compress_hint.setText(f"{self.background_progress_summary}{worker_text}{game_text}")
        elif self.background_status_text:
            self.background_compress_hint.setText(self.background_status_text.splitlines()[0])
        else:
            self.background_compress_hint.setText(
                f"{'Paused' if paused else 'Running'} | Game {current}/{self.background_total}"
            )

    def reset_background_progress_bars(self, summary, task_text="Overall progress 0%", completed_text="Completed 0 GB / 0 GB", files_text="Files 0/0"):
        self.background_progress_summary = summary
        self.background_task_progress_value = 0
        self.background_task_progress_text = task_text
        self.background_completed_progress_value = 0
        self.background_completed_progress_text = completed_text
        self.background_file_progress_value = 0
        self.background_file_progress_text = files_text
        self.background_worker_active = 0

    def update_background_worker_usage(self, active, capacity):
        self.background_worker_active = max(0, int(active or 0))
        self.background_worker_capacity = max(0, int(capacity or 0))
        self.update_dashboard()

    def update_background_pause_state(self, paused, game_name, reason):
        self.background_game_pause_active = bool(paused)
        self.background_game_pause_name = str(game_name or "")
        self.background_game_pause_reason = str(reason or "")
        if self.background_compress_active:
            self.update_dashboard()

    def update_foreground_pause_state(self, paused, game_name, reason):
        self.foreground_pause_active = bool(paused)
        self.foreground_pause_name = str(game_name or "")
        self.foreground_pause_reason = str(reason or "")
        if self.foreground_pause_active:
            detected_name = self.foreground_pause_name or "game"
            self.foreground_status_text = f"Game detected: {detected_name}. compact.exe workers frozen."
            capacity = int(getattr(self, "background_worker_capacity", 0) or 0)
            if hasattr(self, "loading_debug_box"):
                suffix = f" 0/{capacity}" if capacity else ""
                self.loading_debug_box.setPlainText(f"compact.exe workers frozen.{suffix}")
        elif reason:
            self.foreground_status_text = str(reason)
        self.update_dashboard()

    def ask_cancel_cleanup_choice(self, title="Cancel task"):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Warning)
        box.setText("How do you want to cancel this compression?")
        box.setInformativeText(
            "Cancel only stops the current compact process.\n"
            "Decompress whole cancels, then runs a full decompression cleanup for this game."
        )
        cancel_only_btn = box.addButton("Cancel Only", QMessageBox.AcceptRole)
        cleanup_btn = box.addButton("Decompress Whole", QMessageBox.DestructiveRole)
        keep_running_btn = box.addButton("Keep Running", QMessageBox.RejectRole)
        box.setDefaultButton(keep_running_btn)
        box.exec_()

        clicked = box.clickedButton()
        if clicked == cleanup_btn:
            return "cleanup"
        if clicked == cancel_only_btn:
            return "cancel"
        return "keep"

    def progress_status_line(self, status, prefix):
        for line in str(status or "").splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line
        return ""

    def background_compress_candidates(self):
        return state_background_compress_candidates(self.games, self.background_path_allowed)

    def background_decompress_candidates(self):
        return state_background_decompress_candidates(self.games, self.background_path_allowed)

    def dedupe_decompress_candidates_for_popup(self, candidates):
        deduped = {}

        def norm_path(value):
            raw = str(value or "").strip().strip('"')
            if not raw:
                return ""
            try:
                return os.path.normcase(os.path.abspath(raw))
            except Exception:
                return ""

        def norm_name(value):
            text = str(value or "").strip().lower()
            if not text:
                return ""
            cleaned = "".join(ch for ch in text if ch.isalnum())
            return cleaned

        def is_detected_source(game):
            source = str(game.get("source", "") or "").strip().lower()
            return source in {"detected folder", "manual folder", "manual"}

        def source_rank(game):
            return 0 if is_detected_source(game) else 1

        def candidate_key(game):
            appid = str(game.get("appid", "") or "").strip().lower()
            exe_path = norm_path(game.get("exe_path", ""))
            game_path = norm_path(game.get("path", ""))
            game_name = norm_name(game.get("name", ""))

            if appid:
                return f"appid:{appid}"
            if exe_path:
                return f"exe:{exe_path}"
            if game_name:
                return f"name:{game_name}"
            return f"path:{game_path}"

        def candidate_score(game):
            compressed_rank = 1 if self.is_game_compressed(game) else 0
            saved_bytes = int(self.background_saved_bytes(game) or 0)
            known_size = int(game.get("size", 0) or game.get("manifest_size", 0) or 0)
            return (compressed_rank, source_rank(game), saved_bytes, known_size)

        def should_merge_by_name(existing_game, incoming_game):
            existing_name = norm_name(existing_game.get("name", ""))
            incoming_name = norm_name(incoming_game.get("name", ""))
            if not existing_name or existing_name != incoming_name:
                return False

                                                                                         
            if is_detected_source(existing_game) != is_detected_source(incoming_game):
                return True

            existing_path = norm_path(existing_game.get("path", ""))
            incoming_path = norm_path(incoming_game.get("path", ""))
            if existing_path and incoming_path:
                return existing_path.startswith(incoming_path) or incoming_path.startswith(existing_path)
            return False

        for index, game in candidates:
            key = candidate_key(game)
            if key not in deduped:
                deduped[key] = (index, game)
                continue
            existing_index, existing_game = deduped[key]
            if candidate_score(game) > candidate_score(existing_game):
                deduped[key] = (index, game)

        merged = []
        for entry in deduped.values():
            index, game = entry
            merge_index = None
            for i, (_, existing_game) in enumerate(merged):
                if should_merge_by_name(existing_game, game):
                    merge_index = i
                    break
            if merge_index is None:
                merged.append((index, game))
            else:
                _, existing_game = merged[merge_index]
                if candidate_score(game) > candidate_score(existing_game):
                    merged[merge_index] = (index, game)

        return merged

    def background_path_allowed(self, path):
        return self.manual_path_allowed(path) if hasattr(self, "manual_path_allowed") else safe_path(path)

    def game_detection_paths(self):
        return state_build_game_detection_paths(self.games, os.path.isfile)

    def background_saved_bytes(self, game):
        return state_background_saved_bytes(game)

    def original_game_size(self, game):
        return state_original_game_size(game)

    def background_is_game_checked(self, game):
        return state_background_is_game_checked(
            game,
            self.background_selection_mode,
            self.background_selected_paths,
        )

    def background_is_decompress_checked(self, game):
        return state_background_is_decompress_checked(game, self.background_decompress_selected_paths)

    def save_background_selection(self):
        self.app_settings["background_selection_mode"] = self.background_selection_mode
        self.app_settings["background_selected_paths"] = sorted(self.background_selected_paths)
        self.app_settings["background_decompress_selected_paths"] = sorted(self.background_decompress_selected_paths)
        self.save_settings()
        self.update_background_picker_label()

    def update_background_picker_label(self):
        if not hasattr(self, "background_compress_btn"):
            return
        compress_candidates = self.background_compress_candidates()
        decompress_candidates = self.background_decompress_candidates()
        total = len(compress_candidates) + len(decompress_candidates)
        if self.background_selection_mode == "all":
            selected = len(compress_candidates)
        else:
            valid_keys = {self.background_game_key(game) for _, game in compress_candidates}
            selected = len(self.background_selected_paths.intersection(valid_keys))
        valid_decompress_keys = {self.background_game_key(game) for _, game in decompress_candidates}
        selected += len(self.background_decompress_selected_paths.intersection(valid_decompress_keys))
        if total <= 0:
            self.background_compress_btn.setText("Choose Games")
        else:
            self.background_compress_btn.setText(f"Choose Games ({selected}/{total})")

        workers = resolve_worker_count(
            self.app_settings.get("worker_mode", DEFAULT_WORKER_MODE),
            self.app_settings.get("worker_count", DEFAULT_WORKER_COUNT),
        )
        label = "worker" if workers == 1 else "workers"
        if hasattr(self, "background_worker_amount_label"):
            self.background_worker_amount_label.setText(f"Using {workers} {label}")

    def set_background_game_checked(self, game, checked):
        key = self.background_game_key(game)
        if not key:
            return
        if self.background_selection_mode == "all":
            self.background_selected_paths = {
                self.background_game_key(item)
                for _, item in self.background_compress_candidates()
                if self.background_game_key(item)
            }
            self.background_selection_mode = "custom"
        if checked:
            self.background_selected_paths.add(key)
        else:
            self.background_selected_paths.discard(key)
        self.save_background_selection()

    def set_background_decompress_game_checked(self, game, checked):
        key = self.background_game_key(game)
        if not key:
            return
        if checked:
            self.background_decompress_selected_paths.add(key)
            if not self.is_game_compressed(game):
                if self.background_selection_mode == "all":
                    self.background_selected_paths = {
                        self.background_game_key(item)
                        for _, item in self.background_compress_candidates()
                        if self.background_game_key(item)
                    }
                    self.background_selection_mode = "custom"
                self.background_selected_paths.discard(key)
        else:
            self.background_decompress_selected_paths.discard(key)
        self.save_background_selection()

    def select_all_background_games(self):
        self.background_selection_mode = "all"
        self.background_selected_paths = set()
        self.save_background_selection()

    def clear_background_games(self):
        self.background_selection_mode = "custom"
        self.background_selected_paths = set()
        self.background_decompress_selected_paths = set()
        self.save_background_selection()

    def open_background_compress_popup(self, refresh_detection=False):
        if self.busy:
            QMessageBox.warning(self, APP_NAME, "A task is already running.")
            return

                                                                     
                                                                                  
                                                                             
        if refresh_detection:
            self.refresh_background_game_detection()

        dialog = QDialog(self)
        dialog.setObjectName("BackgroundPickerDialog")
        dialog.setWindowTitle("Background Compression")
        dialog.setMinimumWidth(720)
        dialog.resize(760, 640)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Background Compression")
        title.setObjectName("BackgroundPickerTitle")
        hint = QLabel("Choose games to compress or decompress in the background queue.")
        hint.setObjectName("BackgroundPickerHint")
        root.addWidget(title)
        root.addWidget(hint)

        top_actions = QHBoxLayout()
        select_all_btn = QPushButton("Check All")
        select_all_btn.setObjectName("BackgroundPickerGhost")
        clear_btn = QPushButton("Uncheck All")
        clear_btn.setObjectName("BackgroundPickerGhost")
        refresh_btn = QPushButton("Refresh Stores")
        refresh_btn.setObjectName("BackgroundPickerGhost")
        top_actions.addWidget(select_all_btn)
        top_actions.addWidget(clear_btn)
        top_actions.addStretch()
        top_actions.addWidget(refresh_btn)
        root.addLayout(top_actions)

        scroll = QScrollArea()
        scroll.setObjectName("BackgroundPickerScroll")
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(360)
        scroll.setMaximumHeight(460)
        content = QWidget()
        content.setObjectName("BackgroundPickerContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        compress_checkbox_rows = []
        decompress_checkbox_rows = []

        def game_original_size(game):
            return self.original_game_size(game)

        def game_source_size_text(game):
            size = game_original_size(game)
            source = game.get("source", "Store")
            compressed_size = int(game.get("compressed_size", 0) or 0)
            if size > 0 and compressed_size > 0 and self.is_game_compressed(game):
                return f"{source} | {format_game_size(size)} -> {format_game_size(compressed_size)}"
            if size > 0:
                return f"{source} | {format_game_size(size)}"
            return f"{source} | Size unknown"

        def make_row_progress(value, text, state):
            progress = QProgressBar()
            progress.setObjectName("BackgroundRowProgress")
            progress.setProperty("state", state)
            progress.setRange(0, 100)
            progress.setValue(max(0, min(100, int(value or 0))))
            progress.setTextVisible(True)
            progress.setFormat(text)
            progress.setFixedHeight(24)
            return progress

        def compression_saved_percent(game):
            size = game_original_size(game)
            compressed_size = int(game.get("compressed_size", 0) or 0)
            if size <= 0 or compressed_size <= 0 or compressed_size >= size:
                return 0
            return int(((size - compressed_size) / size) * 100)

        def compression_saved_bytes(game):
            return self.background_saved_bytes(game)

        def compression_saved_text(game):
            size = game_original_size(game)
            compressed_size = int(game.get("compressed_size", 0) or 0)
            algorithm = game.get("compression_algorithm", "") or "Compressed"
            if size > 0 and compressed_size > 0 and self.is_game_compressed(game):
                return f"{algorithm} | {format_game_size(size)} -> {format_game_size(compressed_size)}"
            if self.is_game_compressed(game):
                return f"{algorithm} | Compressed"
            return "Emergency decompress | Clears Windows compression if present"

        compress_header = QLabel("Compress Choices")
        compress_header.setObjectName("BackgroundPickerSection")
        content_layout.addWidget(compress_header)

        compress_candidates = self.background_compress_candidates()
        if compress_candidates:
            for _, game in compress_candidates:
                row = QFrame()
                row.setObjectName("BackgroundGameRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(16, 14, 16, 14)
                row_layout.setSpacing(16)

                text_col = QVBoxLayout()
                text_col.setSpacing(8)
                check = QCheckBox(game.get("name", "Unknown"))
                check.setObjectName("BackgroundGameCheck")
                check.setChecked(self.background_is_game_checked(game))
                check.toggled.connect(lambda checked, item=game: self.set_background_game_checked(item, checked))
                meta = QLabel(game_source_size_text(game))
                meta.setObjectName("BackgroundGameMeta")
                meta.setWordWrap(True)
                progress = make_row_progress(0, f"Ready to compress | {game_source_size_text(game)}", "ready")
                text_col.addWidget(check)
                text_col.addWidget(meta)
                text_col.addWidget(progress)
                row_layout.addLayout(text_col, stretch=1)
                content_layout.addWidget(row)
                compress_checkbox_rows.append(check)
        else:
            empty = QLabel("No uncompressed games found.")
            empty.setObjectName("BackgroundEmptyText")
            content_layout.addWidget(empty)

        decompress_candidates = sorted(
            self.dedupe_decompress_candidates_for_popup(self.background_decompress_candidates()),
            key=lambda item: (
                0 if self.is_game_compressed(item[1]) else 1,
                -compression_saved_bytes(item[1]),
                item[1].get("name", "").lower(),
            ),
        )
        if decompress_candidates:
            decompress_header = QLabel("Decompress Choices")
            decompress_header.setObjectName("BackgroundPickerSection")
            content_layout.addWidget(decompress_header)

            for index, game in decompress_candidates:
                emergency = not self.is_game_compressed(game)
                row = QFrame()
                row.setObjectName("BackgroundGameRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(16, 14, 16, 14)
                row_layout.setSpacing(16)

                text_col = QVBoxLayout()
                text_col.setSpacing(8)
                check_prefix = "Emergency decompress" if emergency else "Decompress"
                check = QCheckBox(f"{check_prefix}: {game.get('name', 'Unknown')}")
                check.setObjectName("BackgroundEmergencyCheck" if emergency else "BackgroundDecompressCheck")
                check.setChecked(self.background_is_decompress_checked(game))
                check.toggled.connect(lambda checked, item=game: self.set_background_decompress_game_checked(item, checked))
                meta = QLabel(game_source_size_text(game))
                meta.setObjectName("BackgroundGameMeta")
                meta.setWordWrap(True)
                progress = make_row_progress(
                    compression_saved_percent(game),
                    compression_saved_text(game),
                    "emergency" if emergency else "decompress",
                )
                text_col.addWidget(check)
                text_col.addWidget(meta)
                text_col.addWidget(progress)

                row_layout.addLayout(text_col, stretch=1)
                content_layout.addWidget(row)
                decompress_checkbox_rows.append(check)

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        bottom = QHBoxLayout()
        cancel_btn = QPushButton("Close")
        cancel_btn.setObjectName("BackgroundPickerGhost")
        run_btn = QPushButton("Run Checked in Background")
        run_btn.setObjectName("BackgroundPickerPrimary")
        bottom.addWidget(cancel_btn)
        bottom.addStretch()
        bottom.addWidget(run_btn)
        root.addLayout(bottom)

        def set_popup_checks(checked):
            target_rows = compress_checkbox_rows if checked else compress_checkbox_rows + decompress_checkbox_rows
            for checkbox in target_rows:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
            if checked:
                self.select_all_background_games()
            else:
                self.clear_background_games()

        def refresh_and_reopen():
            dialog.accept()
            self.open_background_compress_popup(refresh_detection=True)

        select_all_btn.clicked.connect(lambda checked=False: set_popup_checks(True))
        clear_btn.clicked.connect(lambda checked=False: set_popup_checks(False))
        refresh_btn.clicked.connect(lambda checked=False: refresh_and_reopen())
        cancel_btn.clicked.connect(dialog.reject)
        run_btn.clicked.connect(lambda checked=False: (dialog.accept(), self.start_background_compress_all()))

        self.update_background_picker_label()
        dialog.exec_()

    def background_game_queue(self):
        queue, skipped = state_build_background_queue(
            self.games,
            self.background_selection_mode,
            self.background_selected_paths,
            self.background_decompress_selected_paths,
            self.background_path_allowed,
        )

        if skipped.get("invalid", 0):
            self.log(f"Background queue skipped {skipped['invalid']} game(s) with missing or unsafe paths.")
        if skipped.get("unchecked_compress", 0):
            self.log(f"Background queue skipped {skipped['unchecked_compress']} unchecked compress game(s).")
        if skipped.get("unchecked_decompress", 0):
            self.log(f"Background queue skipped {skipped['unchecked_decompress']} unchecked decompress game(s).")

        return queue

    def refresh_background_game_detection(self):
        self.log("Refreshing game detection before background compression...")
        try:
            found = scan_all_store_games()
        except Exception as e:
            self.log(f"Background detection refresh failed: {e}")
            return

        added = 0
        for game in found:
            if self.add_or_update_game(game):
                added += 1

        self.save_games()
        self.refresh_grid()
        self.log(
            f"Background detection refresh complete. Found {len(found)} game(s), "
            f"added {added}. Saved compressed metadata was kept."
        )

    def start_background_compress_all(self):
        self.background_controller.start_background_compress_all()

    def start_next_background_compress_game(self):
        self.background_controller.start_next_background_compress_game()

    def update_background_compress_progress(self, percent, status, processed, total):
        self.background_controller.update_background_compress_progress(percent, status, processed, total)

    def on_background_compress_done(self, index, algorithm, ok, cancelled, compressed_size, compressed_file_count):
        self.background_controller.on_background_compress_done(
            index,
            algorithm,
            ok,
            cancelled,
            compressed_size,
            compressed_file_count,
        )

    def on_background_decompress_done(self, index, ok, cancelled):
        self.background_controller.on_background_decompress_done(index, ok, cancelled)

    def start_background_cleanup(self, index):
        self.background_controller.start_background_cleanup(index)

    def on_background_cleanup_done(self, index, ok):
        self.background_controller.on_background_cleanup_done(index, ok)

    def toggle_background_pause(self):
        self.background_controller.toggle_background_pause()

    def cancel_background_compress_all(self):
        self.background_controller.cancel_background_compress_all()

    def finish_background_compress(self, message):
        self.background_controller.finish_background_compress(message)

    def game_library_page_is_active(self):
        return (
            hasattr(self, "pages")
            and hasattr(self, "game_library_page")
            and self.pages.currentWidget() is self.game_library_page
        )

    def refresh_grid(self, force=False):
        if hasattr(self, "game_library_page"):
            if not force and not self.game_library_page_is_active():
                self.game_library_refresh_pending = True
                self.update_dashboard()
                return
            self.game_library_refresh_pending = False
            self.game_library_page.refresh_grid(self.games, self.selected_index)
        self.update_dashboard()

    def refresh_grid_throttled(self):
        now = time.time()
        if now - self.last_grid_refresh >= 0.75:
            self.last_grid_refresh = now
            self.refresh_grid()

    def begin_game_library_busy(self, key, text):
        self.game_library_busy_reasons[str(key)] = str(text or "Working...")
        self.update_game_library_busy_overlay()

    def end_game_library_busy(self, key):
        self.game_library_busy_reasons.pop(str(key), None)
        self.update_game_library_busy_overlay()

    def update_game_library_busy_overlay(self):
        if not hasattr(self, "game_library_page"):
            return
        if (
            self.game_library_busy_reasons
            and self.game_library_page_is_active()
        ):
            text = list(self.game_library_busy_reasons.values())[-1]
            self.game_library_page.set_busy_overlay(True, text)
        else:
            self.game_library_page.set_busy_overlay(False)
            if not self.game_library_busy_reasons:
                self.game_library_busy_overlay_suppressed = False

    def select_game(self, index):
        self.selected_index = index
        if index < 0 or index >= len(self.games):
            return
        self.refresh_grid()

    def get_selected_game(self):
        if self.selected_index is None:
            QMessageBox.warning(self, APP_NAME, "Select a game first.")
            return None, None
        if self.selected_index < 0 or self.selected_index >= len(self.games):
            QMessageBox.warning(self, APP_NAME, "Invalid selected game.")
            return None, None
        return self.selected_index, self.games[self.selected_index]

    def auto_scan_stores(self, after_scan=None):
        if self.store_scan_worker and self.store_scan_worker.isRunning():
            self.log("Store scan already running.")
            return False

        self.begin_game_library_busy("store_scan", "Scanning installed games...")
        self.store_scan_after_scan = after_scan
        self.store_scan_worker = StoreScanWorker()
        self.retain_worker_until_finished(self.store_scan_worker)
        self.store_scan_worker.log.connect(self.log)
        self.store_scan_worker.scan_done.connect(self.on_store_scan_done)
        self.store_scan_worker.finished.connect(lambda: setattr(self, "store_scan_worker", None))
        self.store_scan_worker.start()
        return True

    def on_store_scan_done(self, found):
        found = list(found or [])
        removed = self.prune_uninstalled_games()
        added = 0
        for game in found:
            if self.add_or_update_game(game):
                added += 1
        self.save_games()
        self.update_dashboard()
        if found:
            sources = sorted({game.get("source", "Unknown") for game in found})
            self.log(
                f"Store scan complete. Found {len(found)} installed game(s), added {added} new. "
                f"Sources: {', '.join(sources)}"
            )
        else:
            self.log("Store scan found no installed games.")
        if removed:
            self.log(f"Removed {removed} uninstalled game(s) from the saved library.")
        self.refresh_grid()

        after_scan = getattr(self, "store_scan_after_scan", None)
        self.store_scan_after_scan = None
        if callable(after_scan):
            after_scan()
        self.end_game_library_busy("store_scan")

    def run_first_launch_scan_if_needed(self):
        if self.app_settings.get("initial_scan_done"):
            self.log("Startup scan skipped. Use Scan Stores to refresh games.")
            return

        def after_startup_scan():
            self.app_settings["initial_scan_done"] = True
            self.save_settings()
            if self.games:
                self.start_poster_fetch()
                self.start_size_scan()

        self.auto_scan_stores(after_startup_scan)

    def scan_steam_clicked(self):
        def after_scan():
            self.start_poster_fetch()
            self.start_size_scan()

        self.auto_scan_stores(after_scan)

    def refresh_sizes_clicked(self):
        self.start_size_scan()

    def set_custom_poster(self, index):
        if not (0 <= index < len(self.games)):
            return

        game = self.games[index]
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose custom poster",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not image_path:
            return

        if QPixmap(image_path).isNull():
            QMessageBox.warning(self, "Custom Poster", "That image could not be loaded.")
            return

        game_name = game.get("name", "Unknown")
        dialog = PosterCropDialog(image_path, game_name, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        cropped = dialog.cropped_pixmap()
        if cropped.isNull():
            QMessageBox.warning(self, "Custom Poster", "The crop could not be saved.")
            return

        os.makedirs(POSTER_CACHE_DIR, exist_ok=True)
        key = game.get("appid") or game.get("name") or game.get("path") or str(index)
        target = os.path.join(POSTER_CACHE_DIR, f"{safe_cache_name(key)}_custom.png")
        if not cropped.save(target, "PNG"):
            QMessageBox.warning(self, "Custom Poster", "The custom poster file could not be written.")
            return

        self.games[index]["poster"] = target
        self.games[index]["poster_status"] = "Custom"
        self.save_games()
        self.refresh_grid(force=True)
        self.log(f"Custom poster set: {game_name}")

    def start_poster_fetch(self):
        if self.poster_worker and self.poster_worker.isRunning():
            self.log("Poster fetch already running.")
            return
        if not self.games:
            self.log("No games to fetch posters for.")
            return

        poster_jobs = []
        skipped_count = 0
        for index, game in enumerate(self.games):
            poster_path = game.get("poster", "")
            has_file = bool(poster_path and os.path.exists(poster_path))
            has_poster = has_file and game.get("poster_status") in {"Ready", "Custom"}
            if has_file and not has_poster:
                has_poster = is_portrait_poster_file(poster_path)

            if game.get("name") and not has_poster:
                game["poster"] = ""
                game["poster_status"] = "Queued"
                poster_job = dict(game)
                poster_job["__poster_index"] = index
                poster_jobs.append(poster_job)
            elif has_poster:
                skipped_count += 1

        if not poster_jobs:
            self.log("All games already have cached posters.")
            return

        self.log(
            f"Fetching posters for {len(poster_jobs)} missing game(s); "
            f"skipped {skipped_count} cached poster(s)."
        )

        self.refresh_grid()
        self.begin_game_library_busy("poster_fetch", "Refreshing posters...")
        self.poster_worker = PosterFetchWorker(poster_jobs)
        self.poster_worker.log.connect(self.log)
        self.poster_worker.poster_done.connect(self.on_poster_done)
        self.poster_worker.finished_all.connect(self.on_poster_fetch_finished)
        self.poster_worker.start()

    def on_poster_done(self, index, poster_key, poster_path):
        if 0 <= index < len(self.games):
            expected_key = self.games[index].get("appid") or self.games[index].get("path", "") or str(index)
            if expected_key == poster_key:
                if poster_path:
                    self.games[index]["poster"] = poster_path
                    self.games[index]["poster_status"] = "Ready"
                else:
                    self.games[index]["poster_status"] = "Missing"
        self.refresh_grid_throttled()

    def on_poster_fetch_finished(self):
        self.save_games()
        self.refresh_grid()
        self.end_game_library_busy("poster_fetch")

    def start_size_scan(self):
        if self.size_worker and self.size_worker.isRunning():
            self.log("Size scan already running.")
            return
        if not self.games:
            self.log("No games to scan.")
            return
        self.log("Size scan: preparing...")
        self.refresh_grid()
        self.begin_game_library_busy("size_scan", "Scanning game sizes...")
        self.size_worker = SizeScanWorker(self.games)
        self.size_worker.log.connect(self.log)
        self.size_worker.game_started.connect(self.on_scan_game_started)
        self.size_worker.size_progress.connect(self.on_size_progress)
        self.size_worker.size_done.connect(self.on_size_done)
        self.size_worker.finished_all.connect(self.on_size_scan_finished)
        self.size_worker.start()

    def on_scan_game_started(self, index, name, current_game, total_games):
        self.log(f"Checking {current_game}/{total_games}: {name}")

    def on_size_progress(self, index, percent, current_size, file_count):
        if 0 <= index < len(self.games):
            if self.games[index].get("source") == "Steam":
                return
            if self.is_game_compressed(self.games[index]):
                original_size = max(int(self.games[index].get("original_size", 0) or 0), int(current_size or 0))
                self.games[index]["original_size"] = original_size
                self.games[index]["size"] = original_size
                self.games[index]["file_count"] = file_count
                self.games[index]["scan_progress"] = percent
                self.games[index]["size_source"] = "Folder scan"
                return
            self.games[index]["scan_progress"] = percent
            self.games[index]["status"] = "Scanning"
            self.games[index]["size"] = current_size
            self.games[index]["file_count"] = file_count
            self.games[index]["size_source"] = "Folder scan"
        self.refresh_grid_throttled()

    def on_size_done(self, index, size, file_count, size_source):
        if 0 <= index < len(self.games):
            if self.is_game_compressed(self.games[index]):
                original_size = max(
                    int(self.games[index].get("original_size", 0) or 0),
                    int(size or 0),
                    int(self.games[index].get("manifest_size", 0) or 0),
                    int(self.games[index].get("compressed_size", 0) or 0),
                )
                self.games[index]["original_size"] = original_size
                self.games[index]["size"] = original_size
                if size_source == "Steam manifest":
                    self.games[index]["manifest_size"] = size
                self.games[index]["file_count"] = file_count
                self.games[index]["scan_progress"] = 100
                self.games[index]["status"] = "Compressed"
                self.games[index]["size_source"] = size_source
                self.refresh_grid_throttled()
                return
            if self.games[index].get("source") == "Steam" and size_source == "Steam manifest":
                self.games[index]["manifest_size"] = size
                self.games[index]["size"] = size
                self.games[index]["file_count"] = 0
                self.games[index]["scan_progress"] = 100
                self.games[index]["status"] = "Steam Size"
                self.games[index]["size_source"] = "Steam manifest"
            else:
                self.games[index]["size"] = size
                self.games[index]["file_count"] = file_count
                self.games[index]["scan_progress"] = 100
                self.games[index]["status"] = "Normal" if size_source == "Folder scan" else size_source
                self.games[index]["size_source"] = size_source
        self.refresh_grid_throttled()

    def on_size_scan_finished(self):
        self.log("Size scan: complete")
        self.save_games()
        self.refresh_grid()
        self.end_game_library_busy("size_scan")

    def is_drive_root_path(self, path):
        return state_is_drive_root_path(path)

    def manual_path_allowed(self, path):
        path = os.path.abspath(str(path or "").strip().strip('"'))

        if not path:
            return False, "Path is empty."

        if self.is_drive_root_path(path):
            return False, "Do not select a full drive root. Pick the game folder instead."

        if not os.path.isdir(path):
            return False, "Game folder does not exist."

        return True, "OK"

    def manual_game_from_folder(self, path, name=None, exe_path=None):
        return state_manual_game_from_folder(path, self.manual_path_allowed, name=name, exe_path=exe_path)

    def resolve_manual_game_folder(self, selected_folder, exe_path):
        return state_resolve_manual_game_folder(selected_folder, exe_path, self.manual_path_allowed)

    def is_manual_library_folder(self, name):
        return state_is_manual_library_folder(name)

    def manual_games_from_selected_folder(self, path):
        return state_manual_games_from_selected_folder(path, self.manual_path_allowed)

    def open_manual_add_dialog(self):
        dialog = QDialog(self)
        dialog.setObjectName("ManualAddDialog")
        dialog.setWindowTitle("Add Game Folder")
        dialog.setMinimumWidth(680)
        dialog.resize(720, 360)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(14)

        title = QLabel("Add Game Folder")
        title.setObjectName("ManualAddTitle")
        hint = QLabel("Choose the game folder and the executable that launches it.")
        hint.setObjectName("ManualAddHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)
        root.addSpacing(8)

        folder_label = QLabel("Game folder")
        folder_label.setObjectName("ManualAddFieldLabel")
        folder_input = QLineEdit()
        folder_input.setObjectName("ManualAddInput")
        folder_input.setPlaceholderText("Select the game folder")
        folder_browse = QPushButton("Browse")
        folder_browse.setObjectName("ManualAddBrowse")

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        folder_row.addWidget(folder_input, stretch=1)
        folder_row.addWidget(folder_browse)

        exe_label = QLabel("Game executable")
        exe_label.setObjectName("ManualAddFieldLabel")
        exe_input = QLineEdit()
        exe_input.setObjectName("ManualAddInput")
        exe_input.setPlaceholderText("Select the game's executable")
        exe_browse = QPushButton("Browse")
        exe_browse.setObjectName("ManualAddBrowse")

        exe_row = QHBoxLayout()
        exe_row.setSpacing(10)
        exe_row.addWidget(exe_input, stretch=1)
        exe_row.addWidget(exe_browse)

        root.addWidget(folder_label)
        root.addLayout(folder_row)
        root.addSpacing(8)
        root.addWidget(exe_label)
        root.addLayout(exe_row)
        root.addStretch()

        bottom = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ManualAddCancel")
        add_btn = QPushButton("Add Game")
        add_btn.setObjectName("ManualAddPrimary")
        bottom.addStretch()
        bottom.addWidget(cancel_btn)
        bottom.addWidget(add_btn)
        root.addLayout(bottom)

        def pick_folder():
            picker = QFileDialog(dialog, "Choose Game Folder")
            picker.setFileMode(QFileDialog.Directory)
            picker.setOption(QFileDialog.ShowDirsOnly, True)
            if folder_input.text().strip():
                picker.setDirectory(folder_input.text().strip().strip('"'))
            if picker.exec_() == QDialog.Accepted and picker.selectedFiles():
                folder_input.setText(os.path.abspath(picker.selectedFiles()[0]))

        def pick_exe():
            picker = QFileDialog(dialog, "Choose Game Executable")
            picker.setFileMode(QFileDialog.ExistingFile)
            picker.setNameFilter("Executable files (*.exe);;All files (*.*)")
            start_dir = folder_input.text().strip().strip('"')
            if start_dir and os.path.isdir(start_dir):
                picker.setDirectory(start_dir)
            elif exe_input.text().strip():
                picker.setDirectory(os.path.dirname(exe_input.text().strip().strip('"')))
            if picker.exec_() == QDialog.Accepted and picker.selectedFiles():
                exe_input.setText(os.path.abspath(picker.selectedFiles()[0]))

        folder_browse.clicked.connect(pick_folder)
        exe_browse.clicked.connect(pick_exe)
        cancel_btn.clicked.connect(dialog.reject)
        add_btn.clicked.connect(dialog.accept)

        if dialog.exec_() != QDialog.Accepted:
            return None, None

        return folder_input.text().strip(), exe_input.text().strip()

    def add_folder(self):
        folder_path, exe_path = self.open_manual_add_dialog()

        if not folder_path:
            self.log("Manual add cancelled before folder path.")
            return

        folder_path = os.path.abspath(folder_path.strip().strip('"'))

        if not exe_path:
            self.log("Manual add cancelled before executable path.")
            return

        exe_path = os.path.abspath(exe_path.strip().strip('"'))

        game, reason = self.manual_game_from_folder(folder_path, exe_path=exe_path)

        if not game:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"Could not add that game.\\n\\n{reason}",
            )
            self.log(f"Manual add failed: {reason}")
            return

        added = self.add_or_update_game(game)

        self.save_games()
        self.refresh_grid()

        target_path = os.path.abspath(game.get("path", ""))

        for index, item in enumerate(self.games):
            if os.path.abspath(item.get("path", "")).lower() == target_path.lower():
                self.select_game(index)
                break

        self.log(
            f"Manual add complete. {'Added' if added else 'Updated'} "
            f"{game.get('name', 'Unknown')} from {target_path} "
            f"with executable {os.path.basename(exe_path)}."
        )

        self.start_size_scan()

    def remove_selected(self):
        index, game = self.get_selected_game()
        if game is None:
            return
        result = QMessageBox.question(
            self,
            APP_NAME,
            f"Remove from list?\n\n{game.get('name', 'Unknown')}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.games.pop(index)
        self.selected_index = None
        self.save_games()
        self.refresh_grid()
        self.log("Removed from list.")

    def run_card_action(self, index):
        if index < 0 or index >= len(self.games):
            return
        self.select_game(index)
        if self.is_game_compressed(self.games[index]):
            self.decompress_game(index)
        else:
            self.compress_game(index)

    def compress_selected(self):
        index, game = self.get_selected_game()
        if game is not None:
            self.compress_game(index)

    def compress_game(self, index):
        if index < 0 or index >= len(self.games):
            return

        game = self.games[index]

        ok, reason = self.manual_path_allowed(game["path"]) if hasattr(self, "manual_path_allowed") else safe_path(game["path"])
        if not ok:
            QMessageBox.critical(self, APP_NAME, reason)
            return

        if self.busy:
            QMessageBox.warning(self, APP_NAME, "A task is already running.")
            return

        algorithm = self.selected_compression_algorithm()
        self.run_compact_task(index, "Compressed", "Compressing", algorithm)

    def decompress_selected(self):
        index, game = self.get_selected_game()
        if game is not None:
            self.decompress_game(index)

    def decompress_game(self, index):
        if index < 0 or index >= len(self.games):
            return

        game = self.games[index]

        ok, reason = self.manual_path_allowed(game["path"]) if hasattr(self, "manual_path_allowed") else safe_path(game["path"])
        if not ok:
            QMessageBox.critical(self, APP_NAME, reason)
            return

        if self.busy:
            QMessageBox.warning(self, APP_NAME, "A task is already running.")
            return

        self.run_compact_task(index, "Normal", "Decompressing", self.selected_compression_algorithm())

    def run_compact_task(self, index, new_status, action_label, algorithm):
        self.busy = True
        self.set_buttons_enabled(False)
        self.update_dashboard()
        label = compression_algorithm_label(algorithm)
        status = f"{action_label} {self.games[index]['name']}..."
        if action_label == "Compressing":
            status = f"{action_label} {self.games[index]['name']} with {label}..."
        self.show_loading_overlay(action_label, status)

        self.compact_worker = CompactWorker(
            self.games[index]["path"],
            action_label,
            algorithm,
            normalized_worker_mode(self.app_settings.get("worker_mode", DEFAULT_WORKER_MODE)),
            normalized_worker_count(self.app_settings.get("worker_count", DEFAULT_WORKER_COUNT)),
            game_paths=self.game_detection_paths(),
            auto_pause_when_game_running=bool(self.app_settings.get("smart_game_pause", AUTO_PAUSE_WHEN_GAME_RUNNING)),
        )
        self.background_worker_capacity = getattr(self.compact_worker, "max_workers", 0)
        self.background_worker_active = 0
        self.compact_worker.log.connect(self.log)
        self.compact_worker.progress.connect(self.update_loading_overlay)
        self.compact_worker.active_files.connect(self.update_active_files)
        self.compact_worker.worker_usage.connect(self.update_background_worker_usage)
        self.compact_worker.pause_state.connect(self.update_foreground_pause_state)

        def finished(ok, cancelled, compressed_size, compressed_file_count):
            self.busy = False
            self.set_buttons_enabled(True)
            self.hide_loading_overlay()
            previous_saved_amount = max(
                0,
                int(self.games[index].get("size", 0) or 0) - int(self.games[index].get("compressed_size", 0) or 0),
            )

            if ok:
                self.games[index]["status"] = new_status
                if new_status == "Compressed":
                    original_size = self.original_game_size(self.games[index])
                    self.games[index]["compression_algorithm"] = algorithm
                    self.games[index]["original_size"] = original_size
                    self.games[index]["size"] = original_size
                    self.games[index]["compressed_size"] = compressed_size
                    self.games[index]["compressed_file_count"] = compressed_file_count
                    game_name = self.games[index].get("name", "Unknown")
                    saved_amount = self.background_saved_bytes(self.games[index])
                    self.log(
                        f"Task finished with {algorithm}. Saved: {format_game_size(saved_amount)}. "
                        f"Compressed size: {format_game_size(compressed_size)}"
                    )
                    self.show_saved_space_toast(game_name, saved_amount)
                else:
                    self.games[index]["compression_algorithm"] = ""
                    self.games[index]["compressed_size"] = 0
                    self.games[index]["compressed_file_count"] = 0
                    self.log("Decompression finished. App metadata cleared.")
                    self.show_hotpill_toast(
                        self.games[index].get("name", "Unknown"),
                        f"Restored | Lost {format_game_size(previous_saved_amount)}",
                    )
            elif cancelled:
                if (
                    action_label == "Compressing"
                    and self.compact_worker
                    and getattr(self.compact_worker, "cancel_cleanup_requested", False)
                ):
                    self.log("Compression cancelled. Starting cleanup decompression...")
                    self.games[index]["status"] = "Cleaning Up"
                    self.games[index]["compression_algorithm"] = ""
                    self.games[index]["compressed_size"] = 0
                    self.games[index]["compressed_file_count"] = 0
                    self.save_games()
                    self.refresh_grid()
                    self.update_dashboard()
                    self.run_compact_task(index, "Normal", "Decompressing", self.selected_compression_algorithm())
                    return
                self.log("Task cancelled.")
            else:
                self.log("Task failed.")

            self.save_games()
            self.refresh_grid()
            self.select_game(index)
            self.update_dashboard()

        self.compact_worker.done.connect(finished)
        self.compact_worker.start()

    def cancel_compact_task(self):
        if self.compact_worker and self.compact_worker.isRunning():
            cleanup_requested = False
            if getattr(self.compact_worker, "action_label", "") == "Compressing":
                choice = self.ask_cancel_cleanup_choice("Cancel compression")
                if choice == "keep":
                    return
                cleanup_requested = choice == "cleanup"

            self.loading_cancel_btn.setEnabled(False)
            self.loading_cancel_btn.setText("Cancelling...")

            if getattr(self.compact_worker, "action_label", "") == "Compressing":
                if cleanup_requested:
                    self.loading_status.setText(
                        "Cancelling compression...\nCleanup decompression will start after compact stops."
                    )
                else:
                    self.loading_status.setText("Cancelling compression without cleanup...")
                self.compact_worker.cancel(cleanup_decompress=cleanup_requested)
            else:
                self.loading_status.setText("Cancelling task...")
                self.compact_worker.cancel(cleanup_decompress=False)

            self.update_dashboard()

    def set_buttons_enabled(self, enabled):
        if hasattr(self, "game_library_page"):
            self.game_library_page.set_buttons_enabled(enabled)


if __name__ == "__main__":
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Xzen.GameManager")
        except Exception:
            pass

    if os.name == "nt" and not is_admin() and should_launch_as_admin():
        if relaunch_as_admin():
            sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    if APP_ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_FILE)))
    window = XzenGameManager()
    window.show()
    sys.exit(app.exec_())
