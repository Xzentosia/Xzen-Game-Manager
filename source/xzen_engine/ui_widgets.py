from __future__ import annotations

import os

from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PyQt5.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QHBoxLayout, QWidget

from source.xzen_engine.constants import APP_ICON_FILE, APP_NAME
from source.xzen_engine.formatting import format_game_size
from source.xzen_engine.theme import color as theme_color, themed_qss


class DashboardGauge(QWidget):
    def __init__(self):
        super().__init__()
        self.saved_bytes = 0
        self.total_possible_bytes = 0
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, saved_bytes, total_possible_bytes):
        self.saved_bytes = int(saved_bytes or 0)
        self.total_possible_bytes = int(total_possible_bytes or 0)
        self.update()

    def fitted_font(self, family, text, max_point_size, min_point_size, width, weight=QFont.Normal):
        for point_size in range(int(max_point_size), int(min_point_size) - 1, -1):
            font = QFont(family, point_size, weight)
            metrics = QFontMetrics(font)
            if metrics.horizontalAdvance(text) <= width:
                return font
        return QFont(family, int(min_point_size), weight)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h) - 50
        x = (w - size) / 2
        y = (h - size) / 2 + 10
        rect = QRectF(x, y, size, size)

        start_angle = 225 * 16
        span_angle = -270 * 16

        outer_rect = rect.adjusted(-15, -15, 15, 15)
        outer_pen = QPen(QColor(theme_color("border_strong")), 2, Qt.DashLine)
        painter.setPen(outer_pen)
        painter.drawArc(outer_rect, start_angle, span_angle)

        track_pen = QPen(QColor(theme_color("border_soft")), 22, Qt.SolidLine, Qt.FlatCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, start_angle, span_angle)

        percent = 0
        if self.total_possible_bytes > 0:
            percent = max(0, min(1, self.saved_bytes / self.total_possible_bytes))

        active_span = int(span_angle * percent)
        if percent > 0:
            glow_pen = QPen(QColor(theme_color("accent")), 34, Qt.SolidLine, Qt.FlatCap)
            glow_pen.setColor(QColor(192, 113, 255, 30))
            painter.setPen(glow_pen)
            painter.drawArc(rect, start_angle, active_span)

            core_pen = QPen(QColor(theme_color("accent")), 16, Qt.SolidLine, Qt.FlatCap)
            painter.setPen(core_pen)
            painter.drawArc(rect, start_angle, active_span)

        text_width = max(80, int(size * 0.78))
        value_font_size = max(16, min(34, int(size * 0.16)))
        label_font_size = max(8, min(11, int(size * 0.055)))
        value_rect = QRectF(x + (size - text_width) / 2, y + (size * 0.38), text_width, size * 0.18)
        label_rect = QRectF(x + (size - text_width) / 2, y + (size * 0.56), text_width, size * 0.12)

        painter.setPen(QColor(theme_color("text")))
        val_str = format_game_size(self.saved_bytes).replace(".00", "")
        painter.setFont(
            self.fitted_font(
                "Segoe UI Variable Display",
                val_str,
                value_font_size,
                14,
                text_width,
                QFont.Black,
            )
        )
        painter.drawText(value_rect, Qt.AlignCenter, val_str)

        painter.setPen(QColor(theme_color("accent")))
        label_text = "RECLAIMED SPACE"
        painter.setFont(
            self.fitted_font(
                "Segoe UI Variable",
                label_text,
                label_font_size,
                8,
                text_width,
                QFont.Bold,
            )
        )
        painter.drawText(label_rect, Qt.AlignCenter, label_text)


class DashboardMiniCard(QFrame):
    def __init__(self, title, value, accent_color=None):
        super().__init__()
        self.setObjectName("DashboardMiniCard")
        accent_color = accent_color or theme_color("accent")
        self.accent_color = accent_color
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {accent_color};")

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"color: {theme_color('text')};")
        self.value_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.value_label)
        self.adjust_fonts()

    def fitted_label_font(self, text, max_point_size, min_point_size, weight):
        available_width = max(60, self.width() - 40)
        for point_size in range(int(max_point_size), int(min_point_size) - 1, -1):
            font = QFont("Segoe UI Variable", point_size, weight)
            metrics = QFontMetrics(font)
            if metrics.horizontalAdvance(str(text or "")) <= available_width:
                return font
        return QFont("Segoe UI Variable", int(min_point_size), weight)

    def adjust_fonts(self):
        title_font = self.fitted_label_font(self.title_label.text(), 11, 8, QFont.Bold)
        title_font.setCapitalization(QFont.AllUppercase)
        value_font = self.fitted_label_font(self.value_label.text(), 28, 14, QFont.Black)
        self.title_label.setFont(title_font)
        self.value_label.setFont(value_font)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_fonts()

    def set_value(self, value):
        self.value_label.setText(str(value))
        self.adjust_fonts()


class CustomTitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._drag_active = False
        self._drag_offset = QPoint()
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(8)

        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName("CustomTitleLabel")

        self.min_button = QPushButton("-")
        self.min_button.setObjectName("TitleBarButton")
        self.min_button.setFixedSize(34, 24)
        self.min_button.clicked.connect(self._window.showMinimized)

        self.max_button = QPushButton("□")
        self.max_button.setObjectName("TitleBarButton")
        self.max_button.setFixedSize(34, 24)
        self.max_button.clicked.connect(self._window.toggle_maximize_restore)

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("TitleBarCloseButton")
        self.close_button.setFixedSize(34, 24)
        self.close_button.clicked.connect(self._window.close)

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

    def _start_system_move(self):
        window_handle = self._window.windowHandle()
        if not window_handle or not hasattr(window_handle, "startSystemMove"):
            return False
        try:
            return bool(window_handle.startSystemMove())
        except Exception:
            return False

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        child = self.childAt(event.pos())
        if isinstance(child, QPushButton):
            super().mousePressEvent(event)
            return

        if os.name == "nt":
            self._start_system_move()
            self._drag_active = False
            event.accept()
            return

        if self._start_system_move():
            self._drag_active = False
            event.accept()
            return

        self._drag_active = True
        self._drag_offset = event.globalPos() - self._window.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag_active or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return

        if self._window.isMaximized():
            ratio = max(0.0, min(1.0, event.x() / max(1, self.width())))
            self._window.showNormal()
            target_x = event.globalX() - int(self._window.width() * ratio)
            target_y = event.globalY() - 12
            self._window.move(target_x, target_y)
            self._drag_offset = QPoint(int(self._window.width() * ratio), 12)
        else:
            self._window.move(event.globalPos() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_active = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._window.toggle_maximize_restore()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class QuickStatsFloatingWindow(QWidget):
    def __init__(self):
        super().__init__(None)
        self._drag_active = False
        self._drag_offset = QPoint()
        self.user_moved = False

        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("QuickStatsOverlay")
        self.resize(250, 172)
        self.setMinimumWidth(250)
        if APP_ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_FILE)))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame(self)
        self.panel.setObjectName("QuickStatsPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(6)

        title = QLabel("Quick Stats")
        title.setObjectName("QuickStatsTitle")

        saved_label = QLabel("Saved Storage")
        saved_label.setObjectName("QuickStatsLabel")
        self.saved_value = QLabel("--")
        self.saved_value.setObjectName("QuickStatsValue")

        status_label = QLabel("Status")
        status_label.setObjectName("QuickStatsLabel")
        self.status_value = QLabel("Idle")
        self.status_value.setObjectName("QuickStatsStatus")
        self.status_value.setWordWrap(True)
        self.suspended_header = QLabel("Suspended Utilities")
        self.suspended_header.setObjectName("QuickStatsLabel")
        self.suspended_list = QLabel("")
        self.suspended_list.setObjectName("QuickStatsSuspendedList")
        self.suspended_list.setWordWrap(True)
        self.worker_header = QLabel("Workers")
        self.worker_header.setObjectName("QuickStatsLabel")
        self.worker_value = QLabel("")
        self.worker_value.setObjectName("QuickStatsSuspendedList")
        self.worker_header.hide()
        self.worker_value.hide()
        self.suspended_header.hide()
        self.suspended_list.hide()

        panel_layout.addWidget(title)
        panel_layout.addWidget(saved_label)
        panel_layout.addWidget(self.saved_value)
        panel_layout.addWidget(status_label)
        panel_layout.addWidget(self.status_value)
        panel_layout.addWidget(self.suspended_header)
        panel_layout.addWidget(self.suspended_list)
        panel_layout.addWidget(self.worker_header)
        panel_layout.addWidget(self.worker_value)
        root.addWidget(self.panel)

        for child in (
            title,
            saved_label,
            self.saved_value,
            status_label,
            self.status_value,
            self.suspended_header,
            self.suspended_list,
            self.worker_header,
            self.worker_value,
        ):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.setStyleSheet(
            themed_qss("""
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
            #QuickStatsSuspendedList {
                color: #FF6B8A;
                font-size: 12px;
                font-weight: 850;
            }
            """)
        )

    def _try_start_system_move(self):
        window_handle = self.windowHandle()
        if not window_handle or not hasattr(window_handle, "startSystemMove"):
            return False
        try:
            started = bool(window_handle.startSystemMove())
            if started:
                self.user_moved = True
            return started
        except Exception:
            return False

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if os.name == "nt":
            self._try_start_system_move()
            event.accept()
            return

        if self._try_start_system_move():
            event.accept()
            return
        self._drag_active = True
        self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._drag_active or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        self.move(event.globalPos() - self._drag_offset)
        self.user_moved = True
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_active = False
        super().mouseReleaseEvent(event)
