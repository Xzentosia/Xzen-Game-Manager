from __future__ import annotations


# Change the app palette here. The style helpers below remap the existing QSS
# colors so older widgets follow this one source of truth.
PALETTE = {
    "app_bg": "#0B0A10",  # Main window, dialogs, title areas, deepest app background.
    "page_bg": "#090913",  # Upscaler page background and very dark popup/dropdown backplates.
    "panel": "#0F0E17",  # Left nav, terminal/log boxes, progress tracks, panel surfaces.
    "surface": "#12101C",  # Cards, inputs, combo boxes, modal panels, normal row backgrounds.
    "surface_alt": "#161422",  # Selected cards, hover fills, focused inputs, active row backgrounds.
    "surface_hover": "#231E36",  # Button hover fills and stronger hover card surfaces.
    "surface_soft": "#181525",  # Normal buttons and soft secondary controls.
    "surface_deep": "#08070D",  # Crop editor canvas and darkest scrollbar slots.
    "border": "#221E30",  # Standard card, input, progress, scrollbar, and row borders.
    "border_strong": "#2B2640",  # Stronger button/input/dialog borders and selected outlines.
    "border_soft": "#1A1825",  # Thin dividers, title bar border, disabled/progress track tint.
    "text": "#FFFFFF",  # Primary labels, titles, button text, high-emphasis text.
    "text_soft": "#eeeeee",  # Normal body text, combo text, secondary button text.
    "text_muted": "#888899",  # Hints, metadata, subtitles, row/card small details.
    "text_dim": "#555566",  # Disabled/quiet labels and nav section titles.
    "accent": "#C071FF",  # Main purple: selected nav, highlights, progress chunks, action buttons.
    "accent_soft": "#B38AFF",  # Softer purple: crop tool, scrollbars, secondary highlights.
    "accent_dark": "#7B2CBF",  # Dark purple gradient ends and deep accent shadows.
    "accent_hover": "#D28BFF",  # Bright hover purple for primary buttons and scrollbar hover.
    "accent_button": "#9D4EDD",  # Primary button gradient start.
    "accent_button_hover": "#B060F0",  # Primary button hover gradient start.
    "accent_alt": "#7E61FF",  # Upscaler install/manage buttons and combo focus borders.
    "danger": "#FF6B6B",  # Decompress/destructive buttons, error borders, emergency text.
    "danger_alt": "#FF4D6D",  # Strong danger fills such as close/destructive active states.
    "danger_text": "#FF6B8A",  # Warning status text and paused/game-detected pills.
    "warning": "#FFD166",  # Paused/decompress status and warning checkbox color.
    "success": "#00E676",  # Online/ready/success status, completed progress.
    "info": "#00D4FF",  # File progress, active foreground task status, info accents.
}


PALETTE_DESCRIPTIONS = {
    "app_bg": "Main window, dialogs, title areas, deepest app background.",
    "page_bg": "Upscaler page background and very dark popup/dropdown backplates.",
    "panel": "Left nav, terminal/log boxes, progress tracks, panel surfaces.",
    "surface": "Cards, inputs, combo boxes, modal panels, normal row backgrounds.",
    "surface_alt": "Selected cards, hover fills, focused inputs, active row backgrounds.",
    "surface_hover": "Button hover fills and stronger hover card surfaces.",
    "surface_soft": "Normal buttons and soft secondary controls.",
    "surface_deep": "Crop editor canvas and darkest scrollbar slots.",
    "border": "Standard card, input, progress, scrollbar, and row borders.",
    "border_strong": "Stronger button/input/dialog borders and selected outlines.",
    "border_soft": "Thin dividers, title bar border, disabled/progress track tint.",
    "text": "Primary labels, titles, button text, high-emphasis text.",
    "text_soft": "Normal body text, combo text, secondary button text.",
    "text_muted": "Hints, metadata, subtitles, row/card small details.",
    "text_dim": "Disabled/quiet labels and nav section titles.",
    "accent": "Main purple: selected nav, highlights, progress chunks, action buttons.",
    "accent_soft": "Softer purple: crop tool, scrollbars, secondary highlights.",
    "accent_dark": "Dark purple gradient ends and deep accent shadows.",
    "accent_hover": "Bright hover purple for primary buttons and scrollbar hover.",
    "accent_button": "Primary button gradient start.",
    "accent_button_hover": "Primary button hover gradient start.",
    "accent_alt": "Upscaler install/manage buttons and combo focus borders.",
    "danger": "Decompress/destructive buttons, error borders, emergency text.",
    "danger_alt": "Strong danger fills such as close/destructive active states.",
    "danger_text": "Warning status text and paused/game-detected pills.",
    "warning": "Paused/decompress status and warning checkbox color.",
    "success": "Online/ready/success status, completed progress.",
    "info": "File progress, active foreground task status, info accents.",
}


COLOR_ALIASES = {
    "#08070D": "surface_deep",
    "#080808": "surface_deep",
    "#090913": "page_bg",
    "#0A0A14": "page_bg",
    "#0B0A10": "app_bg",
    "#0F0E17": "panel",
    "#10101D": "panel",
    "#11111F": "surface",
    "#12101C": "surface",
    "#121220": "surface",
    "#141426": "surface",
    "#15131C": "border_soft",
    "#161422": "surface_alt",
    "#171421": "surface_alt",
    "#17172A": "surface_alt",
    "#181525": "surface_soft",
    "#181A30": "surface_soft",
    "#1A1825": "border_soft",
    "#1B1830": "surface_hover",
    "#221E30": "border",
    "#231E36": "surface_hover",
    "#24213B": "surface_hover",
    "#2A181D": "surface",
    "#2A2940": "border_strong",
    "#2B2448": "surface_hover",
    "#2B2640": "border_strong",
    "#292840": "border_strong",
    "#302E4B": "border_strong",
    "#332C55": "surface_hover",
    "#3D3862": "border_strong",
    "#444455": "text_dim",
    "#4A456D": "border_strong",
    "#5C45B8": "accent_dark",
    "#6C5BD1": "accent",
    "#716D8B": "text_muted",
    "#777788": "text_muted",
    "#7B2CBF": "accent_dark",
    "#7D61FF": "accent_alt",
    "#7E61FF": "accent_alt",
    "#9278FF": "accent_hover",
    "#9B96B9": "text_muted",
    "#9C86FF": "accent_hover",
    "#9D4EDD": "accent_button",
    "#A28FFF": "accent_hover",
    "#A6F7C1": "success",
    "#AAAAAA": "text_muted",
    "#B060F0": "accent_button_hover",
    "#B38AFF": "accent_soft",
    "#BBBBCC": "text_muted",
    "#C071FF": "accent",
    "#C8AAFF": "accent_hover",
    "#CBC2FF": "accent_soft",
    "#CCCCCC": "text_soft",
    "#D28BFF": "accent_hover",
    "#DCD6FF": "text_soft",
    "#DCD7F5": "text_soft",
    "#E0E0E0": "text_soft",
    "#EEEEEE": "text_soft",
    "#F5F2FF": "text",
    "#F6F2FF": "text",
    "#FFFFFF": "text",
    "#00D4FF": "info",
    "#00E676": "success",
    "#80D44F": "success",
    "#8E3F46": "danger",
    "#278756": "success",
    "#4778C7": "info",
    "#FF4D6D": "danger_alt",
    "#FF6B6B": "danger",
    "#FF6B8A": "danger_text",
    "#FF7777": "danger",
    "#FF8FA3": "danger_text",
    "#FFB3B3": "danger",
    "#FFB7B7": "danger",
    "#FFD166": "warning",
    "#FFE08A": "warning",
}


RGBA_ALIASES = {
    "rgba(0, 212, 255, 0.12)": ("info", 0.12),
    "rgba(0, 230, 118, 0.1)": ("success", 0.10),
    "rgba(5, 4, 10, 230)": ("app_bg", 0.90),
    "rgba(8, 7, 14, 174)": ("app_bg", 0.68),
    "rgba(9, 8, 14, 0.78)": ("app_bg", 0.78),
    "rgba(16, 13, 24, 0.96)": ("surface", 0.96),
    "rgba(18, 16, 28, 0.72)": ("surface", 0.72),
    "rgba(179, 138, 255, 0.22)": ("accent_soft", 0.22),
    "rgba(192, 113, 255, 0.05)": ("accent", 0.05),
    "rgba(192, 113, 255, 0.1)": ("accent", 0.10),
    "rgba(192, 113, 255, 0.15)": ("accent", 0.15),
    "rgba(192, 113, 255, 0.18)": ("accent", 0.18),
    "rgba(192, 113, 255, 0.2)": ("accent", 0.20),
    "rgba(192, 113, 255, 0.3)": ("accent", 0.30),
    "rgba(192, 113, 255, 0.4)": ("accent", 0.40),
    "rgba(192, 113, 255, 0.5)": ("accent", 0.50),
    "rgba(192, 113, 255, 0.55)": ("accent", 0.55),
    "rgba(192, 113, 255, 0.6)": ("accent", 0.60),
    "rgba(192, 113, 255, 0.65)": ("accent", 0.65),
    "rgba(255, 107, 107, 0.05)": ("danger", 0.05),
    "rgba(255, 107, 107, 0.1)": ("danger", 0.10),
    "rgba(255, 107, 107, 0.2)": ("danger", 0.20),
    "rgba(255, 107, 107, 0.25)": ("danger", 0.25),
    "rgba(255, 107, 107, 0.3)": ("danger", 0.30),
    "rgba(255, 107, 107, 0.45)": ("danger", 0.45),
    "rgba(255, 107, 107, 0.6)": ("danger", 0.60),
    "rgba(255, 107, 138, 0.14)": ("danger_text", 0.14),
    "rgba(255, 209, 102, 0.12)": ("warning", 0.12),
    "rgba(255, 209, 102, 0.6)": ("warning", 0.60),
}


def color(name: str) -> str:
    return PALETTE[name]


def rgba(name: str, alpha: float) -> str:
    value = color(name).lstrip("#")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:g})"


def themed_qss(qss: str) -> str:
    output = qss
    for literal, (name, alpha) in RGBA_ALIASES.items():
        output = output.replace(literal, rgba(name, alpha))
    for literal, name in sorted(COLOR_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        replacement = color(name)
        output = output.replace(literal, replacement)
        output = output.replace(literal.lower(), replacement)
    return output


def status_pill_style(name: str, alpha: float = 0.12) -> str:
    return (
        f"color: {color(name)}; font-size: 13px; font-weight: 800; "
        f"background: {rgba(name, alpha)}; padding: 6px 14px; border-radius: 12px;"
    )
