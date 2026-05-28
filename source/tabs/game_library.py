import os
from PyQt5.QtCore import QAbstractAnimation, QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QScrollArea,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QFrame,
    QDialog,
    QSizePolicy,
    QSlider,
)

from source.xzen_engine.posters import sanitize_png_file


MIN_CARD_W = 205
MAX_CARD_W = 235
CARD_H_EXTRA = 158
POSTER_W_PADDING = 30
POSTER_ASPECT = 260 / 175
GRID_SPACING = 12

SCROLLBAR_ACCENT = "#B38AFF"

PURPLE_SCROLLBAR_STYLE = f"""
    QScrollBar:vertical {{
        background: #080808;
        width: 11px;
        margin: 0;
        border: none;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical {{
        background: {SCROLLBAR_ACCENT};
        min-height: 34px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #c8aaff;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
        background: transparent;
        border: none;
    }}

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        background: #080808;
        height: 11px;
        margin: 0;
        border: none;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal {{
        background: {SCROLLBAR_ACCENT};
        min-width: 34px;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: #c8aaff;
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
        background: transparent;
        border: none;
    }}

    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
"""


class PosterLabel(QLabel):
    left_clicked = pyqtSignal()
    right_clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.right_clicked.emit()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.left_clicked.emit()
        super().mousePressEvent(event)


class PosterCropCanvas(QWidget):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.zoom = 1.0
        self.center = QPointF(pixmap.width() / 2, pixmap.height() / 2)
        self.drag_start = None
        self.drag_center = QPointF(self.center)
        self.setMinimumSize(360, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.OpenHandCursor)

    def crop_frame(self):
        margin = 28
        available_w = max(1, self.width() - margin * 2)
        available_h = max(1, self.height() - margin * 2)
        frame_h = min(available_h, available_w * 1.5)
        frame_w = frame_h * 2 / 3
        if frame_w > available_w:
            frame_w = available_w
            frame_h = frame_w * 1.5
        x = (self.width() - frame_w) / 2
        y = (self.height() - frame_h) / 2
        return QRectF(x, y, frame_w, frame_h)

    def image_scale(self):
        frame = self.crop_frame()
        min_scale = max(
            frame.width() / max(1, self.pixmap.width()),
            frame.height() / max(1, self.pixmap.height()),
        )
        return max(min_scale, min_scale * self.zoom)

    def image_rect(self):
        frame = self.crop_frame()
        scale = self.image_scale()
        image_w = self.pixmap.width() * scale
        image_h = self.pixmap.height() * scale
        x = frame.center().x() - self.center.x() * scale
        y = frame.center().y() - self.center.y() * scale
        return QRectF(x, y, image_w, image_h)

    def clamp_center(self):
        frame = self.crop_frame()
        scale = self.image_scale()
        crop_w = frame.width() / scale
        crop_h = frame.height() / scale
        min_x = crop_w / 2
        max_x = self.pixmap.width() - crop_w / 2
        min_y = crop_h / 2
        max_y = self.pixmap.height() - crop_h / 2
        if min_x > max_x:
            self.center.setX(self.pixmap.width() / 2)
        else:
            self.center.setX(max(min_x, min(max_x, self.center.x())))
        if min_y > max_y:
            self.center.setY(self.pixmap.height() / 2)
        else:
            self.center.setY(max(min_y, min(max_y, self.center.y())))

    def set_zoom_percent(self, value):
        self.zoom = max(1.0, min(3.0, value / 100.0))
        self.clamp_center()
        self.update()

    def crop_pixmap(self):
        self.clamp_center()
        frame = self.crop_frame()
        rect = self.image_rect()
        scale = self.image_scale()
        source = QRect(
            int(round((frame.left() - rect.left()) / scale)),
            int(round((frame.top() - rect.top()) / scale)),
            int(round(frame.width() / scale)),
            int(round(frame.height() / scale)),
        ).intersected(self.pixmap.rect())
        if source.isEmpty():
            return QPixmap()
        return self.pixmap.copy(source).scaled(600, 900, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = event.pos()
            self.drag_center = QPointF(self.center)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            scale = self.image_scale()
            delta = event.pos() - self.drag_start
            self.center = QPointF(
                self.drag_center.x() - delta.x() / scale,
                self.drag_center.y() - delta.y() / scale,
            )
            self.clamp_center()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.clamp_center()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#08070D"))
        rect = self.image_rect().toRect()
        painter.drawPixmap(rect, self.pixmap)
        frame = self.crop_frame()
        overlay = QColor(0, 0, 0, 150)
        painter.fillRect(QRectF(0, 0, self.width(), frame.top()), overlay)
        painter.fillRect(QRectF(0, frame.bottom(), self.width(), self.height() - frame.bottom()), overlay)
        painter.fillRect(QRectF(0, frame.top(), frame.left(), frame.height()), overlay)
        painter.fillRect(QRectF(frame.right(), frame.top(), self.width() - frame.right(), frame.height()), overlay)
        painter.setPen(QPen(QColor("#B38AFF"), 3))
        painter.drawRoundedRect(frame, 10, 10)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for step in (1, 2):
            x = frame.left() + frame.width() * step / 3
            y = frame.top() + frame.height() * step / 3
            painter.drawLine(int(x), int(frame.top()), int(x), int(frame.bottom()))
            painter.drawLine(int(frame.left()), int(y), int(frame.right()), int(y))


class PosterCropDialog(QDialog):
    def __init__(self, image_path, game_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Custom Poster")
        self.setModal(True)
        self.setMinimumSize(520, 720)
        self.source_pixmap = QPixmap(image_path)
        self.setStyleSheet("""
            QDialog { background: #0B0A10; color: #ffffff; }
            QLabel#CropTitle { color: #ffffff; font-size: 22px; font-weight: 900; }
            QLabel#CropHint { color: #888899; font-size: 12px; font-weight: 700; }
            QLabel#CropGame { color: #B38AFF; font-size: 13px; font-weight: 900; }
            QFrame#CropPanel { background: #12101C; border: 1px solid #2B2640; border-radius: 14px; }
            QSlider::groove:horizontal { height: 8px; background: #221E30; border-radius: 4px; }
            QSlider::sub-page:horizontal { background: #B38AFF; border-radius: 4px; }
            QSlider::handle:horizontal { background: #ffffff; border: 3px solid #B38AFF; width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; }
            QPushButton { background: #181525; color: #ffffff; border: 1px solid #2B2640; border-radius: 8px; padding: 10px 16px; font-weight: 900; }
            QPushButton:hover { background: #231E36; border-color: #B38AFF; }
            QPushButton#CropApply { background: #B38AFF; color: #08070D; border-color: #B38AFF; }
            QPushButton#CropApply:hover { background: #C8AAFF; }
        """)
        self.build_ui(game_name)

    def build_ui(self, game_name):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Custom Poster")
        title.setObjectName("CropTitle")

        game_label = QLabel(str(game_name or "Selected game"))
        game_label.setObjectName("CropGame")
        game_label.setWordWrap(True)

        hint = QLabel("Drag the image and adjust zoom. The saved poster is cropped to 2:3.")
        hint.setObjectName("CropHint")
        hint.setWordWrap(True)

        panel = QFrame(self)
        panel.setObjectName("CropPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(12)

        self.canvas = PosterCropCanvas(self.source_pixmap, panel)
        self.zoom_slider = QSlider(Qt.Horizontal, panel)
        self.zoom_slider.setRange(100, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.canvas.set_zoom_percent)

        panel_layout.addWidget(self.canvas, stretch=1)
        panel_layout.addWidget(self.zoom_slider)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel_btn = QPushButton("Cancel")
        apply_btn = QPushButton("Use Poster")
        apply_btn.setObjectName("CropApply")
        cancel_btn.clicked.connect(self.reject)
        apply_btn.clicked.connect(self.accept)
        actions.addWidget(cancel_btn)
        actions.addWidget(apply_btn)

        layout.addWidget(title)
        layout.addWidget(game_label)
        layout.addWidget(hint)
        layout.addWidget(panel, stretch=1)
        layout.addLayout(actions)

    def cropped_pixmap(self):
        return self.canvas.crop_pixmap()


class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.setFixedSize(54, 54)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def start(self):
        if not self.timer.isActive():
            self.timer.start(32)

    def stop(self):
        self.timer.stop()

    def tick(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = max(6, min(self.width(), self.height()) // 2 - 7)
        tick = max(3, int(radius * 0.4))
        for index in range(12):
            alpha = int(40 + (index / 11) * 215)
            color = QColor(179, 138, 255, alpha)
            painter.setPen(QPen(color, 4, Qt.SolidLine, Qt.RoundCap))
            painter.save()
            painter.translate(center)
            painter.rotate(self.angle + index * 30)
            painter.drawLine(0, -radius, 0, -radius + tick)
            painter.restore()


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll_target = 0
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(420)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        if not bar or bar.maximum() <= bar.minimum():
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if not delta:
            pixel_delta = event.pixelDelta().y()
            delta = pixel_delta if pixel_delta else 0

        if not delta:
            super().wheelEvent(event)
            return

        if self._scroll_animation.state() == QAbstractAnimation.Running:
            current = self._scroll_target
        else:
            current = bar.value()

        step = max(90, int(bar.pageStep() * 0.34))
        wheel_units = delta / 120.0
        if abs(delta) > 0 and abs(delta) < 120:
            wheel_units = delta / 64.0

        self._scroll_target = int(current - (wheel_units * step * 1.35))
        self._scroll_target = max(bar.minimum(), min(bar.maximum(), self._scroll_target))

        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(self._scroll_target)
        self._scroll_animation.start()
        event.accept()


class GameCard(QFrame):
    clicked = pyqtSignal(int)
    action_clicked = pyqtSignal(int)
    poster_context_requested = pyqtSignal(int)

    def __init__(
        self,
        index,
        game,
        format_size_func,
        selected=False,
        action_text="Compress",
        card_width=MIN_CARD_W,
        poster_width=None,
        poster_height=None,
    ):
        super().__init__()

        self.index = index
        self.game = game
        self.format_size = format_size_func
        self.poster_width = int(poster_width or max(1, card_width - POSTER_W_PADDING))
        self.poster_height = int(poster_height or self.poster_width * POSTER_ASPECT)

        self.setFixedSize(int(card_width), int(self.poster_height + CARD_H_EXTRA))
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("GameCardSelected" if selected else "GameCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(7)

        self.poster = PosterLabel()
        self.poster.setFixedSize(self.poster_width, self.poster_height)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("Poster")
        self.poster.left_clicked.connect(lambda: self.clicked.emit(self.index))
        self.poster.right_clicked.connect(lambda: self.poster_context_requested.emit(self.index))

        self.load_poster()

        self.name_label = QLabel(game.get("name", "Unknown"))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("CardName")
        self.name_label.setMinimumHeight(34)
        self.name_label.setMaximumHeight(38)

        status = game.get("status", "Unknown")
        size = game.get("size", 0)
        compressed_size = int(game.get("compressed_size", 0) or 0)

        meta_text = f"{status} | {self.format_size(size)}"

        if compressed_size > 0:
            meta_text = f"{status} | {self.format_size(size)} -> {self.format_size(compressed_size)}"

        self.meta_label = QLabel(meta_text)
        self.meta_label.setAlignment(Qt.AlignCenter)
        self.meta_label.setWordWrap(True)
        self.meta_label.setObjectName("CardMeta")
        self.meta_label.setMinimumHeight(30)
        self.meta_label.setMaximumHeight(36)

        self.poster_status_label = QLabel(game.get("poster_status", ""))
        self.poster_status_label.setAlignment(Qt.AlignCenter)
        self.poster_status_label.setObjectName("SavedMeta")
        self.poster_status_label.setMinimumHeight(16)
        self.poster_status_label.setMaximumHeight(18)

        self.action_btn = QPushButton(action_text)
        self.action_btn.setObjectName("CardActionButton")
        self.action_btn.setProperty(
            "state", "disable" if action_text == "Decompress" else "enable"
        )
        self.action_btn.setFixedHeight(34)
        self.action_btn.clicked.connect(lambda: self.action_clicked.emit(self.index))

        layout.addWidget(self.poster, alignment=Qt.AlignCenter)
        layout.addWidget(self.name_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.poster_status_label)
        layout.addWidget(self.action_btn)

    def load_poster(self):
        poster_path = self.game.get("poster", "")

        if poster_path and os.path.exists(poster_path):
            poster_path = sanitize_png_file(poster_path)
            pixmap = QPixmap(poster_path)

            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.poster_width,
                    self.poster_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )

                self.poster.setPixmap(pixmap)
                return

        status = self.game.get("poster_status", "Queued")
        self.poster.setText(status if status else "No Poster")
        self.poster.setStyleSheet("background: transparent; color:#ffffff; border:none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

        super().mousePressEvent(event)


class GameRow(QFrame):
    clicked = pyqtSignal(int)
    action_clicked = pyqtSignal(int)
    poster_context_requested = pyqtSignal(int)

    def __init__(self, index, game, format_size_func, selected=False, action_text="Compress"):
        super().__init__()

        self.index = index
        self.game = game
        self.format_size = format_size_func
        self.setObjectName("GameCardSelected" if selected else "GameCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(76)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(14)

        self.poster = PosterLabel()
        self.poster.setFixedSize(44, 58)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("Poster")
        self.poster.left_clicked.connect(lambda: self.clicked.emit(self.index))
        self.poster.right_clicked.connect(lambda: self.poster_context_requested.emit(self.index))
        self.load_poster()

        self.name_label = QLabel(game.get("name", "Unknown"))
        self.name_label.setObjectName("RowName")
        self.name_label.setWordWrap(False)
        self.name_label.setMinimumWidth(210)

        status = game.get("status", "Unknown")
        size = int(game.get("size", 0) or 0)
        compressed_size = int(game.get("compressed_size", 0) or 0)
        size_text = f"Size: {self.format_size(size)}"
        if compressed_size > 0:
            size_text = f"Size: {self.format_size(size)} -> {self.format_size(compressed_size)}"

        self.meta_label = QLabel(f"{status} | {size_text}")
        self.meta_label.setObjectName("RowMeta")
        self.meta_label.setWordWrap(False)

        saved_amount = max(0, size - compressed_size) if compressed_size > 0 else 0
        self.saved_label = QLabel(f"Saved: {self.format_size(saved_amount)}")
        self.saved_label.setObjectName("RowSavedMeta")

        self.action_btn = QPushButton(action_text)
        self.action_btn.setObjectName("CardActionButton")
        self.action_btn.setProperty(
            "state", "disable" if action_text == "Decompress" else "enable"
        )
        self.action_btn.setFixedWidth(130)
        self.action_btn.clicked.connect(lambda: self.action_clicked.emit(self.index))

        layout.addWidget(self.poster)
        layout.addWidget(self.name_label, stretch=2)
        layout.addWidget(self.meta_label, stretch=3)
        layout.addWidget(self.saved_label, stretch=1)
        layout.addStretch()
        layout.addWidget(self.action_btn)

    def load_poster(self):
        poster_path = self.game.get("poster", "")

        if poster_path and os.path.exists(poster_path):
            poster_path = sanitize_png_file(poster_path)
            pixmap = QPixmap(poster_path)
            if not pixmap.isNull():
                self.poster.setPixmap(
                    pixmap.scaled(44, 58, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
                return

        status = self.game.get("poster_status", "No Poster")
        self.poster.setText(status if status else "No Poster")
        self.poster.setStyleSheet("background: transparent; color:#ffffff; border:none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

        super().mousePressEvent(event)


class XGCRGameLibraryPage(QWidget):
    scan_steam_requested = pyqtSignal()
    add_folder_requested = pyqtSignal()
    remove_selected_requested = pyqtSignal()
    refresh_sizes_requested = pyqtSignal()
    refresh_posters_requested = pyqtSignal()
    game_selected = pyqtSignal(int)
    game_action_requested = pyqtSignal(int)
    custom_poster_requested = pyqtSignal(int)
    view_mode_changed = pyqtSignal(str)

    def __init__(self, format_size_func, card_action_text_func, initial_view_mode="grid"):
        super().__init__()
        self.format_size = format_size_func
        self.card_action_text = card_action_text_func
        self.current_games = []
        self.current_selected_index = None
        self.current_columns = 0
        self.current_card_width = 0
        self.reflow_pending = False
        self._initial_show_reflow_done = False
        self.view_mode = "rows" if initial_view_mode == "rows" else "grid"
        self.setObjectName("DashboardPage")
        self.busy_overlay = None
        self.busy_spinner = None
        self.busy_label = None
        self.build_ui()

    def grid_metrics(self):
        available = self.width()
        if hasattr(self, "scroll") and self.scroll.viewport():
                                                                                                 
            available = int(self.scroll.viewport().width() or available)
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
        QTimer.singleShot(180, self.reflow_current_grid)

    def reflow_current_grid(self):
        self.reflow_pending = False
        if not self.isVisible() or not self.current_games:
            return
        columns, card_width, _, _ = self.grid_metrics()
        if self.view_mode == "rows":
            columns = 1
        if columns != self.current_columns or abs(card_width - self.current_card_width) >= 4:
            self.refresh_grid(self.current_games, self.current_selected_index)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.scan_btn = QPushButton("Scan Stores")
        self.add_btn = QPushButton("Add Folder")
        self.remove_btn = QPushButton("Remove")
        self.size_btn = QPushButton("Refresh Sizes")
        self.poster_btn = QPushButton("Refresh Posters")
        self.grid_view_btn = QPushButton("Grid")
        self.row_view_btn = QPushButton("Rows")

        for action_button in (
            self.scan_btn,
            self.add_btn,
            self.remove_btn,
            self.size_btn,
            self.poster_btn,
        ):
            action_button.setObjectName("TopActionButton")

        for view_button in (self.grid_view_btn, self.row_view_btn):
            view_button.setObjectName("ViewModeButton")
            view_button.setCheckable(True)
            view_button.setFixedWidth(66)

        self.grid_view_btn.setChecked(self.view_mode == "grid")
        self.row_view_btn.setChecked(self.view_mode == "rows")

        self.scan_btn.clicked.connect(self.scan_steam_requested.emit)
        self.add_btn.clicked.connect(self.add_folder_requested.emit)
        self.remove_btn.clicked.connect(self.remove_selected_requested.emit)
        self.size_btn.clicked.connect(self.refresh_sizes_requested.emit)
        self.poster_btn.clicked.connect(self.refresh_posters_requested.emit)
        self.grid_view_btn.clicked.connect(lambda: self.set_view_mode("grid"))
        self.row_view_btn.clicked.connect(lambda: self.set_view_mode("rows"))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.scan_btn)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.remove_btn)
        actions.addSpacing(8)
        actions.addWidget(self.size_btn)
        actions.addWidget(self.poster_btn)
        actions.addStretch()
        actions.addWidget(self.grid_view_btn)
        actions.addWidget(self.row_view_btn)

        layout.addLayout(actions)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(PURPLE_SCROLLBAR_STYLE)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(GRID_SPACING)
        self.grid_layout.setVerticalSpacing(GRID_SPACING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, stretch=1)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(145)
        self.log_box.setStyleSheet(PURPLE_SCROLLBAR_STYLE)

        layout.addWidget(self.log_box)

        self.build_busy_overlay()

    def build_busy_overlay(self):
        self.busy_overlay = QFrame(self)
        self.busy_overlay.setWindowFlags(Qt.Widget)
        self.busy_overlay.setObjectName("GameLibraryBusyOverlay")
        self.busy_overlay.setAttribute(Qt.WA_StyledBackground, True)
        self.busy_overlay.setStyleSheet(
            """
            #GameLibraryBusyOverlay {
                background: rgba(8, 7, 14, 174);
                border: 1px solid rgba(179, 138, 255, 0.22);
                border-radius: 10px;
            }
            #GameLibraryBusyText {
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
        self.busy_label.setObjectName("GameLibraryBusyText")
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
        if visible and self.isVisible():
            self.busy_overlay.show()
            self.busy_overlay.raise_()
            self.busy_spinner.start()
        else:
            self.busy_spinner.stop()
            self.busy_overlay.hide()

    def set_view_mode(self, mode):
        mode = "rows" if mode == "rows" else "grid"
        if self.view_mode == mode:
            self.grid_view_btn.setChecked(mode == "grid")
            self.row_view_btn.setChecked(mode == "rows")
            return

        self.view_mode = mode
        self.grid_view_btn.setChecked(mode == "grid")
        self.row_view_btn.setChecked(mode == "rows")
        self.view_mode_changed.emit(mode)
        self.refresh_grid(self.current_games, self.current_selected_index)

    def refresh_grid(self, games, selected_index):
        self.current_games = list(games or [])
        self.current_selected_index = selected_index
        columns, card_width, poster_width, poster_height = self.grid_metrics()
        if self.view_mode == "rows":
            columns = 1
        self.current_columns = columns
        self.current_card_width = card_width

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        for index, game in enumerate(self.current_games):
            if self.view_mode == "rows":
                row = index
                col = 0
                card = GameRow(
                    index=index,
                    game=game,
                    format_size_func=self.format_size,
                    selected=index == selected_index,
                    action_text=self.card_action_text(game),
                )
            else:
                row = index // columns
                col = index % columns
                card = GameCard(
                    index=index,
                    game=game,
                    format_size_func=self.format_size,
                    selected=index == selected_index,
                    action_text=self.card_action_text(game),
                    card_width=card_width,
                    poster_width=poster_width,
                    poster_height=poster_height,
                )

            card.clicked.connect(self.game_selected.emit)
            card.action_clicked.connect(self.game_action_requested.emit)
            card.poster_context_requested.connect(self.custom_poster_requested.emit)
            self.grid_layout.addWidget(card, row, col, Qt.AlignTop | Qt.AlignLeft)

        for col_index in range(max(1, columns + 1)):
            self.grid_layout.setColumnStretch(col_index, 0)
        self.grid_layout.setColumnStretch(columns, 1)
        self.grid_layout.setRowStretch((len(self.current_games) // columns) + 1, 1)
        self.schedule_grid_reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()
        self.reflow_current_grid()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_show_reflow_done:
            self._initial_show_reflow_done = True
            self.schedule_grid_reflow()

    def log(self, text):
        self.log_box.append(text)

    def set_terminal_visible(self, visible):
        self.log_box.setVisible(bool(visible))

    def set_buttons_enabled(self, enabled):
        self.scan_btn.setEnabled(enabled)
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.size_btn.setEnabled(enabled)
        self.poster_btn.setEnabled(enabled)
