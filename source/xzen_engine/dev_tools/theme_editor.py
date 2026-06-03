from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


THEME_FILE = Path(__file__).resolve().parents[1] / "theme.py"
PALETTE_LINE_RE = re.compile(
    r'^(?P<prefix>\s*"(?P<key>[^"]+)":\s*")(?P<value>#[0-9A-Fa-f]{6})'
    r'(?P<suffix>",\s*#\s*(?P<note>.*))$'
)
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def load_theme_module():
    spec = importlib.util.spec_from_file_location("xzen_theme_live", THEME_FILE)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Could not load theme.py")
    spec.loader.exec_module(module)
    return module


def load_palette_rows():
    module = load_theme_module()
    comments = {}
    for line in THEME_FILE.read_text(encoding="utf-8").splitlines():
        match = PALETTE_LINE_RE.match(line)
        if match:
            comments[match.group("key")] = match.group("note").strip()

    rows = []
    for key, value in module.PALETTE.items():
        rows.append(
            {
                "key": key,
                "value": value.upper(),
                "note": getattr(module, "PALETTE_DESCRIPTIONS", {}).get(key, comments.get(key, "")),
            }
        )
    return rows


def write_palette(values):
    lines = THEME_FILE.read_text(encoding="utf-8").splitlines()
    output = []
    for line in lines:
        match = PALETTE_LINE_RE.match(line)
        if match and match.group("key") in values:
            value = values[match.group("key")].upper()
            output.append(f"{match.group('prefix')}{value}{match.group('suffix')}")
        else:
            output.append(line)
    THEME_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")


def readable_name(key):
    return key.replace("_", " ").title()


class ColorRow(QFrame):
    def __init__(self, row, changed_callback):
        super().__init__()
        self.key = row["key"]
        self.note = row["note"]
        self.changed_callback = changed_callback
        self.setObjectName("ColorRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(4)

        self.swatch = QPushButton()
        self.swatch.setObjectName("Swatch")
        self.swatch.setFixedSize(42, 42)
        self.swatch.clicked.connect(self.pick_color)

        title = QLabel(readable_name(self.key))
        title.setObjectName("ColorName")
        title.setMinimumWidth(170)

        key_label = QLabel(self.key)
        key_label.setObjectName("ColorKey")

        note = QLabel(self.note)
        note.setObjectName("ColorNote")
        note.setWordWrap(True)

        self.input = QLineEdit(row["value"])
        self.input.setObjectName("ColorInput")
        self.input.setMaxLength(7)
        self.input.textChanged.connect(self.on_text_changed)

        layout.addWidget(self.swatch, 0, 0, 2, 1)
        layout.addWidget(title, 0, 1)
        layout.addWidget(key_label, 1, 1)
        layout.addWidget(note, 0, 2, 2, 1)
        layout.addWidget(self.input, 0, 3, 2, 1)
        layout.setColumnStretch(2, 1)

        self.update_swatch(row["value"])

    def value(self):
        return self.input.text().strip().upper()

    def is_valid(self):
        return bool(HEX_RE.match(self.value()))

    def update_swatch(self, value):
        self.swatch.setStyleSheet(
            f"QPushButton#Swatch {{ background: {value}; border: 1px solid #3B3754; border-radius: 8px; }}"
        )

    def on_text_changed(self, text):
        value = text.strip()
        valid = bool(HEX_RE.match(value))
        self.input.setProperty("invalid", not valid)
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)
        if valid:
            self.update_swatch(value)
            self.changed_callback()

    def pick_color(self):
        initial = QColor(self.value()) if self.is_valid() else QColor("#ffffff")
        color = QColorDialog.getColor(initial, self, f"Choose {readable_name(self.key)}")
        if color.isValid():
            self.input.setText(color.name().upper())


class ThemePreview(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Preview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.title = QLabel("Xzen Theme Preview")
        self.title.setObjectName("PreviewTitle")

        self.meta = QLabel("Cards, buttons, inputs, status pills")
        self.meta.setObjectName("PreviewMeta")

        self.card = QFrame()
        self.card.setObjectName("PreviewCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        self.card_title = QLabel("Game Card")
        self.card_title.setObjectName("PreviewCardTitle")
        self.input = QLineEdit("Hex values update live")
        self.input.setObjectName("PreviewInput")

        buttons = QHBoxLayout()
        self.primary = QPushButton("Primary")
        self.primary.setObjectName("PreviewPrimary")
        self.secondary = QPushButton("Secondary")
        self.secondary.setObjectName("PreviewSecondary")
        buttons.addWidget(self.primary)
        buttons.addWidget(self.secondary)
        buttons.addStretch()

        self.status = QLabel("System Online")
        self.status.setObjectName("PreviewStatus")

        card_layout.addWidget(self.card_title)
        card_layout.addWidget(self.input)
        card_layout.addLayout(buttons)
        card_layout.addWidget(self.status)

        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addWidget(self.card)
        layout.addStretch()

    def apply_palette(self, values):
        def c(name):
            return values.get(name, "#ffffff")

        self.setStyleSheet(
            f"""
            QFrame#Preview {{
                background: {c("app_bg")};
                border: 1px solid {c("border")};
                border-radius: 12px;
            }}
            QLabel#PreviewTitle {{
                color: {c("text")};
                font-size: 22px;
                font-weight: 900;
            }}
            QLabel#PreviewMeta {{
                color: {c("text_muted")};
                font-size: 12px;
                font-weight: 700;
            }}
            QFrame#PreviewCard {{
                background: {c("surface")};
                border: 1px solid {c("border")};
                border-radius: 10px;
            }}
            QLabel#PreviewCardTitle {{
                color: {c("text")};
                font-size: 15px;
                font-weight: 900;
            }}
            QLineEdit#PreviewInput {{
                background: {c("panel")};
                color: {c("text_soft")};
                border: 1px solid {c("border_strong")};
                border-radius: 8px;
                padding: 10px 12px;
                font-weight: 700;
            }}
            QPushButton#PreviewPrimary {{
                background: {c("accent")};
                color: {c("text")};
                border: 1px solid {c("accent")};
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: 900;
            }}
            QPushButton#PreviewSecondary {{
                background: {c("surface_soft")};
                color: {c("text_soft")};
                border: 1px solid {c("border_strong")};
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: 900;
            }}
            QLabel#PreviewStatus {{
                color: {c("success")};
                background: {c("surface_alt")};
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 900;
            }}
            """
        )


class ThemeEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xzen Theme Editor")
        self.resize(1040, 720)
        self.rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Xzen Theme Editor")
        title.setObjectName("AppTitle")
        subtitle = QLabel(str(THEME_FILE))
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self.reload)
        self.save_btn = QPushButton("Save Theme")
        self.save_btn.setObjectName("SaveButton")
        self.save_btn.clicked.connect(self.save)

        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.reload_btn)
        header.addWidget(self.save_btn)

        body = QHBoxLayout()
        body.setSpacing(14)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("ColorScroll")
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.list_host)

        self.preview = ThemePreview()
        self.preview.setMinimumWidth(340)

        body.addWidget(self.scroll, 2)
        body.addWidget(self.preview, 1)

        root.addLayout(header)
        root.addLayout(body, 1)

        self.setStyleSheet(self.app_style())
        self.load_rows()

    def app_style(self):
        return """
        QWidget {
            background: #0B0A10;
            color: #eeeeee;
            font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
            font-size: 13px;
        }
        QLabel {
            background: transparent;
        }
        QLabel#AppTitle {
            color: #FFFFFF;
            font-size: 24px;
            font-weight: 900;
        }
        QLabel#AppSubtitle {
            color: #888899;
            font-size: 12px;
            font-weight: 700;
        }
        QFrame#ColorRow {
            background: #12101C;
            border: 1px solid #221E30;
            border-radius: 10px;
        }
        QLabel#ColorName {
            color: #FFFFFF;
            font-size: 14px;
            font-weight: 900;
        }
        QLabel#ColorKey {
            color: #888899;
            font-size: 11px;
            font-weight: 800;
        }
        QLabel#ColorNote {
            color: #DCD7F5;
            font-size: 12px;
            font-weight: 650;
        }
        QLineEdit#ColorInput {
            background: #0F0E17;
            color: #FFFFFF;
            border: 1px solid #2B2640;
            border-radius: 8px;
            padding: 9px 10px;
            font-weight: 900;
            min-width: 92px;
            max-width: 92px;
        }
        QLineEdit#ColorInput[invalid="true"] {
            border-color: #FF6B6B;
            color: #FFB3B3;
        }
        QPushButton {
            background: #181525;
            color: #FFFFFF;
            border: 1px solid #2B2640;
            border-radius: 8px;
            padding: 10px 16px;
            font-weight: 900;
        }
        QPushButton:hover {
            background: #231E36;
            border-color: #C071FF;
            color: #C071FF;
        }
        QPushButton#SaveButton {
            background: #7E61FF;
            border-color: #9C86FF;
        }
        QScrollArea {
            background: transparent;
            border: none;
        }
        QScrollBar:vertical {
            background: #0F0E17;
            width: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: #B38AFF;
            min-height: 36px;
            border-radius: 6px;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0;
        }
        """

    def load_rows(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.rows = []

        for row_data in load_palette_rows():
            row = ColorRow(row_data, self.update_preview)
            self.rows.append(row)
            self.list_layout.addWidget(row)

        self.list_layout.addStretch()
        self.update_preview()

    def values(self):
        return {row.key: row.value() for row in self.rows}

    def invalid_rows(self):
        return [row.key for row in self.rows if not row.is_valid()]

    def update_preview(self):
        self.preview.apply_palette(self.values())

    def reload(self):
        self.load_rows()

    def save(self):
        invalid = self.invalid_rows()
        if invalid:
            QMessageBox.warning(
                self,
                "Invalid Colors",
                "Fix these values first:\n" + "\n".join(invalid),
            )
            return
        write_palette(self.values())
        QMessageBox.information(self, "Saved", "theme.py has been updated.")


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI Variable", 10))
    window = ThemeEditor()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
