import os

from PyQt5.QtCore import Qt, QSize, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from source.xzen_engine.constants import (
    POSTER_CACHE_DIR,
    USER_SETTINGS_DIR,
    automatic_worker_count,
    estimated_cpu_core_count,
)
from source.tabs.game_library import PURPLE_SCROLLBAR_STYLE, SmoothScrollArea


COMBO_VIEW_QSS = """
    QListView {
        background-color: #0B0A10;
        border: 1px solid #2B2640;
        border-radius: 8px;
        color: #eeeeee;
        padding: 6px;
        outline: 0;
    }

    QListView::item {
        min-height: 38px;
        padding: 9px 12px;
        border-bottom: 1px solid #1A1825;
    }

    QListView::item:selected {
        background-color: rgba(192, 113, 255, 0.18);
        color: #ffffff;
        border: 1px solid rgba(192, 113, 255, 0.5);
    }
"""


SETTINGS_PAGE_QSS = """
    #SettingsScroll {
        background: transparent;
        border: none;
    }

    #SettingsContent {
        background: transparent;
    }

    #SettingsContent QLabel,
    #SettingsContent QWidget {
        background: transparent;
    }

    #SettingsHeroTitle {
        color: #ffffff;
        font-size: 26px;
        font-weight: 900;
        background: transparent;
    }

    #SettingsHeroHint {
        color: #888899;
        font-size: 12px;
        font-weight: 700;
        background: transparent;
    }

    #SettingsSection {
        background: rgba(18, 16, 28, 0.72);
        border: 1px solid #221E30;
        border-radius: 10px;
    }

    #SettingsSectionTitle {
        color: #ffffff;
        font-size: 16px;
        font-weight: 900;
        background: transparent;
    }

    #SettingsSectionHint,
    #SettingsFieldHint {
        color: #888899;
        font-size: 12px;
        font-weight: 650;
        background: transparent;
    }

    #SettingsFieldLabel {
        color: #eeeeee;
        font-size: 12px;
        font-weight: 900;
        background: transparent;
    }

    #SettingsControl {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #2B2640;
        border-radius: 8px;
        padding: 0 14px;
        font-weight: 800;
        min-height: 42px;
    }

    #SettingsControl:hover {
        border-color: rgba(192, 113, 255, 0.65);
        background: #171421;
    }

    #SettingsControl::drop-down {
        border: none;
        width: 30px;
    }

    #SettingsSpin {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #2B2640;
        border-radius: 8px;
        padding: 0 14px;
        font-weight: 800;
        min-height: 42px;
    }

    #SettingsSpin:hover {
        border-color: rgba(192, 113, 255, 0.65);
        background: #171421;
    }

    #SettingsSlider {
        min-height: 32px;
        background: transparent;
    }

    #SettingsSlider::groove:horizontal {
        height: 8px;
        background: #12101C;
        border: 1px solid #2B2640;
        border-radius: 4px;
    }

    #SettingsSlider::sub-page:horizontal {
        background: #B38AFF;
        border-radius: 4px;
    }

    #SettingsSlider::handle:horizontal {
        background: #ffffff;
        border: 3px solid #B38AFF;
        width: 18px;
        height: 18px;
        margin: -7px 0;
        border-radius: 9px;
    }

    #SettingsValuePill {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #2B2640;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 900;
        padding: 8px 14px;
    }

    QCheckBox#ToggleOption {
        background: transparent;
        color: #eeeeee;
        spacing: 12px;
        font-size: 13px;
        font-weight: 900;
        min-height: 24px;
    }

    QCheckBox#ToggleOption::indicator {
        width: 36px;
        height: 20px;
        border-radius: 10px;
        background-color: #1A1825;
        border: 1px solid #2B2640;
    }

    QCheckBox#ToggleOption::indicator:checked {
        background-color: #C071FF;
        border: 1px solid #C071FF;
    }

    QCheckBox#ToggleOption:hover {
        color: #ffffff;
    }

    #SettingsFolderButton {
        background: #12101C;
        color: #ffffff;
        border: 1px solid #2B2640;
        border-radius: 8px;
        padding: 0 14px;
        font-size: 12px;
        font-weight: 900;
        min-height: 42px;
    }

    #SettingsFolderButton:hover {
        border-color: rgba(192, 113, 255, 0.65);
        background: #171421;
        color: #ffffff;
    }
"""


class XGCRSettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)

    CONTROL_HEIGHT = 44

    def __init__(
        self,
        algorithms,
        current_algorithm,
        show_terminal,
        launch_as_admin,
        smart_game_pause=True,
        close_to_tray=False,
        worker_mode="auto",
        worker_count=4,
    ):
        super().__init__()
        self.algorithms = algorithms
        self.cpu_threads = max(1, os.cpu_count() or 1)
        self.cpu_cores = estimated_cpu_core_count(self.cpu_threads)
        self.custom_worker_row = None
        self.setObjectName("SettingsPage")
        self.setStyleSheet(SETTINGS_PAGE_QSS)
        self.build_ui(
            current_algorithm,
            show_terminal,
            launch_as_admin,
            smart_game_pause,
            close_to_tray,
            worker_mode,
            worker_count,
        )

    def build_ui(
        self,
        current_algorithm,
        show_terminal,
        launch_as_admin,
        smart_game_pause,
        close_to_tray,
        worker_mode,
        worker_count,
    ):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = SmoothScrollArea(self)
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(PURPLE_SCROLLBAR_STYLE)

        content = QWidget(scroll)
        content.setObjectName("SettingsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(18)

        title = QLabel("Settings", content)
        title.setObjectName("SettingsHeroTitle")

        subtitle = QLabel(
            "Tune compression, background behavior, and window handling.",
            content,
        )
        subtitle.setObjectName("SettingsHeroHint")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)

        compression_section, compression_layout = self.create_section(
            content,
            "Compression",
            "Choose the compression method used for manual and background tasks.",
        )
        self.algorithm_combo = QComboBox(compression_section)
        self.prepare_combo(self.algorithm_combo)
        self.algorithm_combo.setMaxVisibleItems(len(self.algorithms))

        current_index = 0
        for index, (key, label, _) in enumerate(self.algorithms):
            self.algorithm_combo.addItem(label, key)
            self.algorithm_combo.setItemData(index, QSize(0, 42), Qt.SizeHintRole)
            if key == current_algorithm:
                current_index = index

        self.algorithm_combo.setCurrentIndex(current_index)
        compression_layout.addWidget(self.field_label("Algorithm", compression_section))
        compression_layout.addWidget(self.algorithm_combo)
        compression_layout.addWidget(
            self.hint_label(
                "X8 is the default balance. LZX is strongest, but slower on huge files.",
                compression_section,
            )
        )
        layout.addWidget(compression_section)

        workers_section, workers_layout = self.create_section(
            content,
            "Compression Workers",
            "Control how many compact workers can run in parallel.",
        )
        self.worker_combo = QComboBox(workers_section)
        self.prepare_combo(self.worker_combo)

        worker_options = [
            ("auto", "Auto - recommended workers"),
            ("1", "1 worker - safest / HDD friendly"),
            ("2", "2 workers - light parallel mode"),
            ("4", "4 workers - fast default"),
            ("custom", f"Custom - choose 1 to {self.cpu_threads}"),
        ]

        selected_worker_index = 0
        worker_mode = str(worker_mode or "auto")
        for index, (key, label) in enumerate(worker_options):
            self.worker_combo.addItem(label, key)
            self.worker_combo.setItemData(index, QSize(0, 42), Qt.SizeHintRole)
            if worker_mode == key:
                selected_worker_index = index

        self.worker_combo.setCurrentIndex(selected_worker_index)

        self.worker_slider = QSlider(Qt.Horizontal, workers_section)
        self.worker_slider.setObjectName("SettingsSlider")
        self.worker_slider.setMinimum(1)
        self.worker_slider.setMaximum(self.cpu_threads)
        self.worker_slider.setValue(self.clamp_worker_count(worker_count))
        self.worker_slider.setSingleStep(1)
        self.worker_slider.setPageStep(1)
        self.worker_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.worker_value_label = QLabel(str(self.worker_slider.value()), workers_section)
        self.worker_value_label.setObjectName("SettingsValuePill")
        self.worker_value_label.setAlignment(Qt.AlignCenter)
        self.worker_value_label.setFixedWidth(58)

        self.custom_worker_row = QWidget(workers_section)
        custom_worker_layout = QHBoxLayout(self.custom_worker_row)
        custom_worker_layout.setContentsMargins(0, 8, 0, 0)
        custom_worker_layout.setSpacing(14)
        custom_worker_layout.addWidget(self.field_label("Worker count", self.custom_worker_row))
        custom_worker_layout.addWidget(self.worker_slider, stretch=1)
        custom_worker_layout.addWidget(self.worker_value_label)
        self.custom_worker_row.setVisible(worker_mode == "custom")

        auto_workers = automatic_worker_count(self.cpu_threads)
        workers_layout.addWidget(self.field_label("Mode", workers_section))
        workers_layout.addWidget(self.worker_combo)
        workers_layout.addWidget(self.custom_worker_row)
        workers_layout.addWidget(
            self.hint_label(
                f"Auto will use {auto_workers} worker(s), based on about {self.cpu_cores} CPU core(s). Custom can still use up to {self.cpu_threads} thread(s).",
                workers_section,
            )
        )
        layout.addWidget(workers_section)

        interface_section, interface_layout = self.create_section(
            content,
            "Interface",
            "Choose how much status information the app shows while you work.",
        )
        self.terminal_toggle = self.option_toggle(
            "Show terminal log",
            "Shows detailed scan and compression messages in the Game Library and Dashboard.",
            show_terminal,
            interface_section,
            interface_layout,
        )
        self.close_to_tray_toggle = self.option_toggle(
            "Close button hides to tray",
            "When enabled, the X button hides the app in the Windows tray instead of exiting.",
            close_to_tray,
            interface_section,
            interface_layout,
        )
        layout.addWidget(interface_section)

        data_section, data_layout = self.create_section(
            content,
            "Data",
            "Open the folders used for app state and cached game posters.",
        )
        data_actions = QWidget(data_section)
        data_actions_layout = QHBoxLayout(data_actions)
        data_actions_layout.setContentsMargins(0, 0, 0, 0)
        data_actions_layout.setSpacing(12)
        data_actions_layout.addWidget(
            self.folder_button("Open saved data", USER_SETTINGS_DIR, data_actions),
            stretch=1,
        )
        data_actions_layout.addWidget(
            self.folder_button("Open posters", POSTER_CACHE_DIR, data_actions),
            stretch=1,
        )
        data_layout.addWidget(data_actions)
        layout.addWidget(data_section)

        behavior_section, behavior_layout = self.create_section(
            content,
            "Behavior",
            "Background safety settings for compression and Windows permissions.",
        )
        self.smart_pause_toggle = self.option_toggle(
            "Smart gaming pause",
            "When a game is active, wait before starting more compact workers.",
            smart_game_pause,
            behavior_section,
            behavior_layout,
        )
        self.admin_toggle = self.option_toggle(
            "Launch as admin",
            "Turn this off if Print Screen or Snipping Tool does not trigger while the app is focused.",
            launch_as_admin,
            behavior_section,
            behavior_layout,
        )
        layout.addWidget(behavior_section)
        layout.addStretch()

        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        self.algorithm_combo.currentIndexChanged.connect(self.emit_settings)
        self.worker_combo.currentIndexChanged.connect(self.on_worker_mode_changed)
        self.worker_slider.valueChanged.connect(self.on_worker_slider_changed)
        self.terminal_toggle.toggled.connect(self.emit_settings)
        self.smart_pause_toggle.toggled.connect(self.emit_settings)
        self.close_to_tray_toggle.toggled.connect(self.emit_settings)
        self.admin_toggle.toggled.connect(self.emit_settings)

    def create_section(self, parent, title, description):
        section = QFrame(parent)
        section.setObjectName("SettingsSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(18, 16, 18, 16)
        section_layout.setSpacing(10)

        title_label = QLabel(title, section)
        title_label.setObjectName("SettingsSectionTitle")

        description_label = QLabel(description, section)
        description_label.setObjectName("SettingsSectionHint")
        description_label.setWordWrap(True)
        description_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        section_layout.addWidget(title_label)
        section_layout.addWidget(description_label)
        section_layout.addSpacing(4)
        return section, section_layout

    def prepare_combo(self, combo):
        combo.setObjectName("SettingsControl")
        combo.setView(QListView(combo))
        combo.view().setStyleSheet(COMBO_VIEW_QSS)
        combo.setFixedHeight(self.CONTROL_HEIGHT)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def field_label(self, text, parent):
        label = QLabel(text, parent)
        label.setObjectName("SettingsFieldLabel")
        return label

    def hint_label(self, text, parent):
        label = QLabel(text, parent)
        label.setObjectName("SettingsFieldHint")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return label

    def option_toggle(self, title, hint, checked, parent, layout):
        toggle = QCheckBox(title, parent)
        toggle.setObjectName("ToggleOption")
        toggle.setChecked(bool(checked))

        hint_label = self.hint_label(hint, parent)

        group = QWidget(parent)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 4, 0, 6)
        group_layout.setSpacing(4)
        group_layout.addWidget(toggle)
        group_layout.addWidget(hint_label)

        layout.addWidget(group)
        return toggle

    def folder_button(self, text, path, parent):
        button = QPushButton(text, parent)
        button.setObjectName("SettingsFolderButton")
        button.setFixedHeight(self.CONTROL_HEIGHT)
        button.clicked.connect(lambda checked=False, folder=path: self.open_folder(folder))
        return button

    def open_folder(self, path):
        target = os.fspath(path)
        os.makedirs(target, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def clamp_worker_count(self, value):
        try:
            value = int(value or 4)
        except Exception:
            value = 4

        return max(1, min(value, self.cpu_threads))

    def on_worker_mode_changed(self, *_):
        if self.custom_worker_row:
            self.custom_worker_row.setVisible(self.worker_combo.currentData() == "custom")
        self.emit_settings()

    def on_worker_slider_changed(self, value):
        self.worker_value_label.setText(str(value))
        self.emit_settings()

    def values(self):
        worker_mode = self.worker_combo.currentData()

        return {
            "compression_algorithm": self.algorithm_combo.currentData(),
            "worker_mode": worker_mode,
            "worker_count": self.worker_slider.value(),
            "show_terminal": self.terminal_toggle.isChecked(),
            "smart_game_pause": self.smart_pause_toggle.isChecked(),
            "close_to_tray": self.close_to_tray_toggle.isChecked(),
            "launch_as_admin": self.admin_toggle.isChecked(),
        }

    def emit_settings(self, *_):
        self.settings_changed.emit(self.values())
