"""
ui.theme
==========
Five selectable themes. Existing code across the app reads colors as
plain module attributes — `theme.PINK`, `theme.TEXT_MUTED`, and so on —
via `from ui import theme` + `theme.XXX` (never `from ui.theme import
XXX`), so those lookups happen live against this module's current
state. Switching themes just reassigns those attributes and rebuilds
the stylesheet; anything reconstructed afterwards (main_window.py
rebuilds the sidebar + current page on every theme change) picks up
the new palette automatically with no per-page code changes.

Themes:
  classic  - the original dark neon pink/purple look (default)
  emerald  - dark, green / teal / cyan
  sky      - light, blue / sky-blue
  blossom  - light, pink / rose / mauve
  special  - pure-black base whose accent changes *by section* —
             gold for Employees/Payroll-ish pages, red for
             Attendance/Reports-ish pages, purple for Departments/
             HR-ish pages, and a quiet monochrome silver for the
             Dashboard — so switching to it turns the whole app into
             one rich, multi-tone "premium" experience instead of a
             single flat accent color. See SPECIAL_SECTION_ACCENTS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace as _dc_replace
from pathlib import Path
from typing import Optional

_ICONS_DIR = (Path(__file__).resolve().parent.parent / "assets" / "icons")
_GENERATED_DIR = _ICONS_DIR / "_generated"


def _icon(name: str) -> str:
    return (_ICONS_DIR / name).as_posix()


def _generated_icon(name: str) -> str:
    return (_GENERATED_DIR / name).as_posix()


# ── Color math ──────────────────────────────────────────────────────────
def _to_rgb(hex_color: str) -> tuple:
    h = (hex_color or "#7c6f9e").lstrip("#")
    if len(h) != 6:
        return (124, 111, 158)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgba(hex_color: str, alpha: float) -> str:
    """'#E040FB', 0.14 -> 'rgba(224,64,251,0.14)' — for QSS overlays
    that need to track the live accent color instead of a frozen
    literal (that was the root cause of themes not being switchable
    at all before this module existed)."""
    r, g, b = _to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha})"


def mix(hex1: str, hex2: str, t: float) -> str:
    """Blend two hex colors; t=0 -> hex1, t=1 -> hex2."""
    r1, g1, b1 = _to_rgb(hex1)
    r2, g2, b2 = _to_rgb(hex2)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Theme spec ──────────────────────────────────────────────────────────
@dataclass
class ThemeSpec:
    key: str
    label: str
    tagline: str
    is_light: bool
    BG_DARKEST: str
    BG_DARK: str
    BG_CARD: str
    BG_CARD_HOVER: str
    BG_ELEVATED: str
    BORDER: str
    BORDER_LIGHT: str
    PINK: str                  # primary accent (buttons, active nav, focus)
    PINK_HOVER: str
    PINK_PRESSED: str
    PINK_DIM: str
    PURPLE: str                # secondary accent (variety in stat cards/badges)
    CYAN: str                  # tertiary accent (links, misc highlights)
    SUCCESS: str
    WARNING: str
    DANGER: str
    INFO: str
    TEXT: str
    TEXT_DIM: str
    TEXT_MUTED: str
    TEXT_STRONG: str           # headings/titles (previously hardcoded #fff)
    TEXT_ON_ACCENT: str        # text drawn on top of a PINK-colored surface
    SOFT_OVERLAY: str          # icon-chip backgrounds etc — light-on-dark or dark-on-light
    SUCCESS_TEXT: str = "#06280f"
    SUCCESS_HOVER: str = "#6ee89a"
    SUCCESS_PRESSED: str = "#35c56a"
    swatch: tuple = ()         # 3 colors for the theme-picker preview chip


THEMES = {
    "classic": ThemeSpec(
        key="classic", label="Classic Neon", tagline="The original dark pink & purple look",
        is_light=False,
        BG_DARKEST="#0e0b1a", BG_DARK="#120e21", BG_CARD="#181329", BG_CARD_HOVER="#1e1836",
        BG_ELEVATED="#221c3d", BORDER="#2c2547", BORDER_LIGHT="#3a3163",
        PINK="#E040FB", PINK_HOVER="#ea6bfc", PINK_PRESSED="#c930e0", PINK_DIM="#a855c9",
        PURPLE="#a855f7", CYAN="#22d3ee",
        SUCCESS="#4ade80", WARNING="#fbbf24", DANGER="#f87171", INFO="#60a5fa",
        TEXT="#e8e0f7", TEXT_DIM="#a89fc4", TEXT_MUTED="#7c6f9e", TEXT_STRONG="#ffffff",
        TEXT_ON_ACCENT="#1a0a22", SOFT_OVERLAY="rgba(255,255,255,0.04)",
        swatch=("#E040FB", "#a855f7", "#22d3ee"),
    ),
    "emerald": ThemeSpec(
        key="emerald", label="Emerald", tagline="Dark, green / cyan / teal",
        is_light=False,
        BG_DARKEST="#07120f", BG_DARK="#0a1815", BG_CARD="#0f211c", BG_CARD_HOVER="#152e27",
        BG_ELEVATED="#122720", BORDER="#1e3931", BORDER_LIGHT="#2b4d42",
        PINK="#10b981", PINK_HOVER="#34d399", PINK_PRESSED="#0c8b64", PINK_DIM="#0d9668",
        PURPLE="#0d9488", CYAN="#22d3ee",
        SUCCESS="#4ade80", WARNING="#fbbf24", DANGER="#f87171", INFO="#22d3ee",
        TEXT="#e3f7ee", TEXT_DIM="#9fcbb8", TEXT_MUTED="#5f8a79", TEXT_STRONG="#ffffff",
        TEXT_ON_ACCENT="#052016", SOFT_OVERLAY="rgba(255,255,255,0.04)",
        swatch=("#10b981", "#0d9488", "#22d3ee"),
    ),
    "sky": ThemeSpec(
        key="sky", label="Sky", tagline="Light, sky-blue & white",
        is_light=True,
        BG_DARKEST="#e3ebfa", BG_DARK="#eef2fb", BG_CARD="#ffffff", BG_CARD_HOVER="#f4f8fe",
        BG_ELEVATED="#ffffff", BORDER="#dbe4f3", BORDER_LIGHT="#c2d3ec",
        PINK="#2f6fed", PINK_HOVER="#4c85f5", PINK_PRESSED="#2158c4", PINK_DIM="#5f95f5",
        PURPLE="#0ea5e9", CYAN="#38bdf8",
        SUCCESS="#16a34a", WARNING="#d97706", DANGER="#dc2626", INFO="#2f6fed",
        TEXT="#1e293b", TEXT_DIM="#475569", TEXT_MUTED="#94a3b8", TEXT_STRONG="#0f172a",
        TEXT_ON_ACCENT="#ffffff", SOFT_OVERLAY="rgba(15,23,42,0.05)",
        SUCCESS_TEXT="#ffffff", SUCCESS_HOVER="#22c55e", SUCCESS_PRESSED="#15803d",
        swatch=("#2f6fed", "#0ea5e9", "#38bdf8"),
    ),
    "blossom": ThemeSpec(
        key="blossom", label="Blossom", tagline="Light, pink & rose",
        is_light=True,
        BG_DARKEST="#f5dced", BG_DARK="#fdf3f8", BG_CARD="#ffffff", BG_CARD_HOVER="#fdf0f6",
        BG_ELEVATED="#ffffff", BORDER="#f5d9e8", BORDER_LIGHT="#eec2dc",
        PINK="#e0559b", PINK_HOVER="#e874ac", PINK_PRESSED="#c23f82", PINK_DIM="#ea8dbe",
        PURPLE="#a855c9", CYAN="#f2a6cf",
        SUCCESS="#16a34a", WARNING="#d97706", DANGER="#dc2626", INFO="#a855c9",
        TEXT="#3d2438", TEXT_DIM="#6b4a63", TEXT_MUTED="#a5809d", TEXT_STRONG="#241320",
        TEXT_ON_ACCENT="#ffffff", SOFT_OVERLAY="rgba(61,36,56,0.05)",
        SUCCESS_TEXT="#ffffff", SUCCESS_HOVER="#22c55e", SUCCESS_PRESSED="#15803d",
        swatch=("#e0559b", "#a855c9", "#f2a6cf"),
    ),
    "special": ThemeSpec(
        key="special", label="Special \u2014 Black & Gold", tagline="Pure black, with gold / red / purple by section",
        is_light=False,
        BG_DARKEST="#000000", BG_DARK="#070707", BG_CARD="#121212", BG_CARD_HOVER="#1c1c1c",
        BG_ELEVATED="#0c0c0c", BORDER="#272727", BORDER_LIGHT="#3a3a3a",
        # Base/default accent (used wherever there's no active-section
        # context yet, e.g. the login screen or a modal dialog) is gold —
        # see SPECIAL_SECTION_ACCENTS for the per-page variants.
        PINK="#d9a635", PINK_HOVER="#e6b94f", PINK_PRESSED="#b3862a", PINK_DIM="#9c7a2e",
        PURPLE="#8a6a1f", CYAN="#f0d488",
        SUCCESS="#2fd66b", WARNING="#f2b632", DANGER="#e5484d", INFO="#8b5cf6",
        TEXT="#f2f2f2", TEXT_DIM="#c9c9c9", TEXT_MUTED="#8f8f8f", TEXT_STRONG="#ffffff",
        TEXT_ON_ACCENT="#1a1200", SOFT_OVERLAY="rgba(255,255,255,0.05)",
        swatch=("#d9a635", "#e5484d", "#8b5cf6"),
    ),
}

# Special theme's per-section accent bundles. Keys match the nav keys
# used in ui/main_window.py's ADMIN_NAV/EMPLOYEE_NAV. Sections not
# listed here (dialogs, settings, login) keep the base "special" spec's
# gold default.
_MONO = dict(PINK="#e6e6e6", PINK_HOVER="#ffffff", PINK_PRESSED="#c7c7c7", PINK_DIM="#a0a0a0",
             PURPLE="#9ca3af", CYAN="#d4d4d4", TEXT_ON_ACCENT="#0a0a0a")
_GOLD = dict(PINK="#d9a635", PINK_HOVER="#e6b94f", PINK_PRESSED="#b3862a", PINK_DIM="#9c7a2e",
             PURPLE="#8a6a1f", CYAN="#f0d488", TEXT_ON_ACCENT="#1a1200")
_RED = dict(PINK="#e0433c", PINK_HOVER="#ea5c55", PINK_PRESSED="#b8342e", PINK_DIM="#a13a34",
            PURPLE="#7a1f1a", CYAN="#f0928c", TEXT_ON_ACCENT="#ffffff")
_VIOLET = dict(PINK="#8659f0", PINK_HOVER="#9a75f3", PINK_PRESSED="#6d3fc9", PINK_DIM="#5b3fa8",
               PURPLE="#4c2a8f", CYAN="#c4b0f5", TEXT_ON_ACCENT="#ffffff")

SPECIAL_SECTION_ACCENTS = {
    "dashboard": _MONO, "emp_dashboard": _MONO,
    "employees": _GOLD, "positions": _GOLD, "payroll": _GOLD, "notifications": _GOLD, "emp_payslips": _GOLD,
    "attendance": _RED, "reports": _RED, "audit_log": _RED, "emp_attendance": _RED,
    "departments": _VIOLET, "pay_periods": _VIOLET, "allowances": _VIOLET, "archive": _VIOLET, "emp_profile": _VIOLET,
}

THEME_ORDER = ["classic", "emerald", "sky", "blossom", "special"]

# ── Live module state ────────────────────────────────────────────────────
_current_theme_key = "classic"
_current_section = "dashboard"


def list_themes():
    return [THEMES[k] for k in THEME_ORDER]


def get_current_theme_key() -> str:
    return _current_theme_key


def get_current_section() -> str:
    return _current_section


def normalize_theme_key(key):
    """Old settings.json files may still say 'dark_neon' (the theme's
    old, unnamed, only-option identity) — treat that as classic."""
    if key in THEMES:
        return key
    return "classic"


def set_active_section(section_key) -> None:
    """Called by main_window.py right before building each page, so the
    Special theme's per-section accent is correct for whatever's about
    to be constructed. Harmless (and cheap) to call for every theme,
    not just Special."""
    global _current_section
    _current_section = section_key or "dashboard"
    _apply_current()


def set_theme(key) -> None:
    global _current_theme_key
    _current_theme_key = normalize_theme_key(key)
    _apply_current()


def _effective_spec():
    base = THEMES[_current_theme_key]
    if base.key != "special":
        return base
    override = SPECIAL_SECTION_ACCENTS.get(_current_section)
    if not override:
        return base
    return _dc_replace(base, **override)


def _write_icon_svgs(spec) -> None:
    """Regenerate the 4 small UI icons (dropdown chevron, calendar,
    checkbox check, radio dot) tinted to the current theme/section
    colors. These are tiny static SVGs on disk (Qt's QSS `url()` needs
    a real file, not an inline data URI reliably), so 'theming' them
    means writing fresh files whenever the palette changes rather than
    baking one fixed color in forever."""
    try:
        _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        chevron = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                   f'<path d="M3.5 6l4.5 4.5L12.5 6" fill="none" stroke="{spec.TEXT_DIM}" '
                   f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        calendar = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                    f'<rect x="2" y="3" width="12" height="11" rx="1.5" fill="none" stroke="{spec.TEXT_DIM}" stroke-width="1.4"/>'
                    f'<line x1="2" y1="6.3" x2="14" y2="6.3" stroke="{spec.TEXT_DIM}" stroke-width="1.4"/>'
                    f'<line x1="5" y1="1.6" x2="5" y2="4" stroke="{spec.TEXT_DIM}" stroke-width="1.4" stroke-linecap="round"/>'
                    f'<line x1="11" y1="1.6" x2="11" y2="4" stroke="{spec.TEXT_DIM}" stroke-width="1.4" stroke-linecap="round"/></svg>')
        check = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                 f'<path d="M3.2 8.5l3.1 3.1 6.3-6.8" fill="none" stroke="{spec.TEXT_ON_ACCENT}" '
                 f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
        radio = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                 f'<circle cx="8" cy="8" r="4" fill="{spec.TEXT_ON_ACCENT}"/></svg>')
        for name, svg in [("chevron_down.svg", chevron), ("calendar.svg", calendar),
                          ("check.svg", check), ("radio_dot.svg", radio)]:
            with open(_GENERATED_DIR / name, "w", encoding="utf-8") as f:
                f.write(svg)
    except Exception:
        # Icon recoloring is a nice-to-have; if the filesystem is
        # read-only or something else goes wrong, fall back to the
        # original static icons rather than crash theme switching.
        pass


def _generated_icons_ready() -> bool:
    return all((_GENERATED_DIR / n).exists() for n in
               ["chevron_down.svg", "calendar.svg", "check.svg", "radio_dot.svg"])


def _apply_current() -> None:
    """The heart of theme switching: reassigns every module-level color
    'constant' from the effective spec, so all existing `theme.XXX`
    references across the app resolve to the new palette the next time
    whatever reads them is (re)constructed."""
    spec = _effective_spec()
    g = globals()
    for fld in spec.__dataclass_fields__:
        if fld in ("key", "label", "tagline", "is_light", "swatch"):
            continue
        g[fld] = getattr(spec, fld)
    g["IS_LIGHT"] = spec.is_light
    g["THEME_LABEL"] = spec.label

    g["GRADIENT_PRIMARY"] = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {spec.PINK}, stop:1 {spec.PURPLE})"
    # Login screen's decorative side panel is always a dark, accent-tinted
    # gradient regardless of the overall theme's light/dark-ness (a
    # deliberately fixed design choice — see BrandPanel in login_window.py).
    brand_base = "#0a0912"
    g["BRAND_GRADIENT"] = (
        f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {brand_base}, "
        f"stop:0.55 {mix(brand_base, spec.PINK, 0.30)}, stop:1 {mix(brand_base, spec.PINK, 0.55)})"
    )

    g["STATUS_COLORS"] = {
        "draft": spec.TEXT_MUTED, "approved": spec.INFO, "paid": spec.SUCCESS, "cancelled": spec.DANGER,
        "active": spec.SUCCESS, "inactive": spec.WARNING, "terminated": spec.DANGER, "on_leave": spec.INFO,
        "open": spec.SUCCESS, "processing": spec.WARNING, "closed": spec.TEXT_MUTED,
        "sent": spec.SUCCESS, "failed": spec.DANGER,
        "present": spec.SUCCESS, "late": spec.WARNING, "absent": spec.DANGER,
        "holiday": spec.PURPLE, "rest_day": spec.TEXT_MUTED, "half_day": spec.WARNING,
    }
    _write_icon_svgs(spec)


def status_color(status: str) -> str:
    return STATUS_COLORS.get((status or "").lower(), TEXT_MUTED)


# Apply the default theme immediately at import time so every module-level
# color name below (BG_DARK, PINK, ...) exists the moment anything does
# `from ui import theme; theme.PINK`.
_apply_current()


def build_stylesheet() -> str:
    chevron = _generated_icon("chevron_down.svg") if _generated_icons_ready() else _icon("chevron_down.svg")
    calendar_icon = _generated_icon("calendar.svg") if _generated_icons_ready() else _icon("calendar.svg")
    check_icon = _generated_icon("check.svg") if _generated_icons_ready() else _icon("check.svg")
    radio_icon = _generated_icon("radio_dot.svg") if _generated_icons_ready() else _icon("radio_dot.svg")
    return f"""
    * {{
        font-family: 'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Inter', Arial, sans-serif;
        outline: none;
    }}

    QWidget {{
        background-color: {BG_DARK};
        color: {TEXT};
        font-size: 13px;
    }}

    QMainWindow, QDialog {{
        background-color: {BG_DARK};
    }}

    /* ── Scrollbars ── */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_LIGHT};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {PINK_DIM}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: {BORDER_LIGHT}; border-radius: 5px; min-width: 30px; }}

    /* ── Labels ── */
    QLabel {{ background: transparent; color: {TEXT}; }}
    QLabel[role="title"] {{ font-size: 20px; font-weight: 800; color: {TEXT_STRONG}; }}
    QLabel[role="subtitle"] {{ font-size: 13px; color: {TEXT_MUTED}; }}
    QLabel[role="section"] {{ font-size: 15px; font-weight: 700; color: {TEXT_STRONG}; }}
    QLabel[role="muted"] {{ color: {TEXT_MUTED}; font-size: 12px; }}
    QLabel[role="error"] {{ color: {DANGER}; font-size: 12px; font-weight: 600; }}
    QLabel[role="stat-value"] {{ font-size: 26px; font-weight: 800; color: {TEXT_STRONG}; }}
    QLabel[role="stat-label"] {{ font-size: 11px; font-weight: 600; color: {TEXT_MUTED}; text-transform: uppercase; }}
    QLabel[role="code"] {{ font-family: 'Consolas', 'Courier New', monospace; letter-spacing: 2px; font-weight: 800; color: {PINK}; }}

    /* ── Buttons ── */
    QPushButton {{
        background-color: {BG_ELEVATED};
        color: {TEXT};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background-color: {BG_CARD_HOVER}; border-color: {PINK_DIM}; }}
    QPushButton:pressed {{ background-color: {BG_DARKEST}; }}
    QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {BORDER}; }}

    QPushButton[variant="primary"] {{
        background-color: {PINK};
        border: 1px solid {PINK};
        color: {TEXT_ON_ACCENT};
        font-weight: 700;
    }}
    QPushButton[variant="primary"]:hover {{ background-color: {PINK_HOVER}; }}
    QPushButton[variant="primary"]:pressed {{ background-color: {PINK_PRESSED}; }}
    QPushButton[variant="primary"]:disabled {{ background-color: {BORDER_LIGHT}; color: {TEXT_MUTED}; border-color: {BORDER_LIGHT}; }}

    QPushButton[variant="success"] {{ background-color: {SUCCESS}; border: 1px solid {SUCCESS}; color: {SUCCESS_TEXT}; }}
    QPushButton[variant="success"]:hover {{ background-color: {SUCCESS_HOVER}; }}

    QPushButton[variant="danger"] {{ background-color: transparent; border: 1px solid {DANGER}; color: {DANGER}; }}
    QPushButton[variant="danger"]:hover {{ background-color: {rgba(DANGER, 0.15)}; }}

    QPushButton[variant="ghost"] {{ background-color: transparent; border: 1px solid {BORDER_LIGHT}; color: {TEXT_DIM}; }}
    QPushButton[variant="ghost"]:hover {{ background-color: {BG_CARD_HOVER}; color: {TEXT}; }}

    QPushButton[variant="link"] {{ background: transparent; border: none; color: {PINK}; font-weight: 600; padding: 2px; }}
    QPushButton[variant="link"]:hover {{ color: {CYAN}; text-decoration: underline; }}

    /* ── Inputs ── */
    QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 8px;
        padding: 8px 10px;
        color: {TEXT};
        selection-background-color: {PINK};
        selection-color: {TEXT_ON_ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {PINK};
    }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {TEXT_MUTED}; background-color: {BG_DARK}; }}
    QLineEdit[error="true"] {{ border: 1px solid {DANGER}; }}
    QLineEdit[success="true"] {{ border: 1px solid {SUCCESS}; }}

    QComboBox::drop-down {{
        border: none; border-left: 1px solid {BORDER_LIGHT};
        width: 28px; background: transparent;
    }}
    QComboBox::down-arrow {{
        image: url({chevron});
        width: 11px; height: 11px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER_LIGHT};
        selection-background-color: {PINK};
        selection-color: {TEXT_ON_ACCENT};
        outline: none;
        padding: 4px;
    }}
    QDateEdit::drop-down {{
        border: none; border-left: 1px solid {BORDER_LIGHT};
        width: 28px; background: transparent;
    }}
    QDateEdit::down-arrow {{
        image: url({calendar_icon});
        width: 14px; height: 14px;
    }}
    QCheckBox {{ color: {TEXT}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border-radius: 5px;
        border: 1px solid {BORDER_LIGHT}; background: {BG_CARD};
    }}
    QCheckBox::indicator:checked {{
        background: {PINK}; border-color: {PINK};
        image: url({check_icon});
    }}
    QCheckBox::indicator:hover {{ border-color: {PINK_DIM}; }}
    QRadioButton {{ color: {TEXT}; spacing: 8px; }}
    QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 8px; border: 1px solid {BORDER_LIGHT}; background: {BG_CARD}; }}
    QRadioButton::indicator:checked {{
        background: {PINK}; border-color: {PINK};
        image: url({radio_icon});
    }}

    /* ── Calendar popup (QDateEdit's dropdown) ── */
    QCalendarWidget {{ background-color: {BG_ELEVATED}; }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{ background-color: {BG_ELEVATED}; }}
    QCalendarWidget QToolButton {{
        color: {TEXT}; background-color: transparent; border: none;
        border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 12px;
        icon-size: 16px;
    }}
    QCalendarWidget QToolButton:hover {{ background-color: {BG_CARD_HOVER}; }}
    QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
    QCalendarWidget QMenu {{ background-color: {BG_ELEVATED}; color: {TEXT}; border: 1px solid {BORDER_LIGHT}; }}
    QCalendarWidget QSpinBox {{
        background-color: {BG_CARD}; color: {TEXT}; border: 1px solid {BORDER_LIGHT};
        border-radius: 4px; padding: 2px 4px;
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: {BG_CARD}; color: {TEXT}; selection-background-color: {PINK};
        selection-color: {TEXT_ON_ACCENT}; border: none; outline: none; gridline-color: {BORDER};
    }}
    QCalendarWidget QAbstractItemView:disabled {{ color: {TEXT_MUTED}; }}
    QCalendarWidget QHeaderView {{ background-color: {BG_ELEVATED}; }}
    QCalendarWidget QHeaderView::section {{
        background-color: {BG_ELEVATED}; color: {TEXT_DIM}; border: none;
        padding: 4px 0px; font-size: 11px; font-weight: 700; text-transform: none;
    }}

    /* ── Cards / Frames ── */
    QFrame[card="true"] {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 14px;
    }}
    QFrame[card="stat"] {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 14px;
    }}
    QFrame[card="stat"]:hover {{ border: 1px solid {PINK_DIM}; }}
    QFrame[divider="true"] {{ background-color: {BORDER}; max-height: 1px; min-height: 1px; }}

    /* ── Sidebar ── */
    QFrame#sidebar {{ background-color: {BG_DARKEST}; border-right: 1px solid {BORDER}; }}
    QPushButton[nav="true"] {{
        background: transparent;
        border: none;
        border-radius: 10px;
        text-align: left;
        padding: 10px 14px;
        color: {TEXT_DIM};
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton[nav="true"]:hover {{ background-color: {BG_CARD}; color: {TEXT}; }}
    QPushButton[nav="true"][active="true"] {{
        background-color: {rgba(PINK, 0.14)};
        color: {PINK};
        border: 1px solid {rgba(PINK, 0.35)};
    }}

    /* ── Top bar ── */
    QFrame#topbar {{ background-color: {BG_DARK}; border-bottom: 1px solid {BORDER}; }}

    /* ── Tables ── */
    QTableWidget, QTableView {{
        background-color: {BG_CARD};
        alternate-background-color: {BG_DARK};
        border: 1px solid {BORDER};
        border-radius: 10px;
        gridline-color: {BORDER};
        selection-background-color: {rgba(PINK, 0.18)};
        selection-color: {TEXT};
    }}
    QHeaderView::section {{
        background-color: {BG_ELEVATED};
        color: {TEXT_MUTED};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {BORDER_LIGHT};
        font-weight: 700;
        font-size: 11px;
        text-transform: uppercase;
    }}
    QTableWidget::item, QTableView::item {{ padding: 6px; border-bottom: 1px solid {BORDER}; }}
    QTableCornerButton::section {{ background-color: {BG_ELEVATED}; border: none; }}

    /* ── Tabs ── */
    QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; top: -1px; }}
    QTabBar::tab {{
        background: transparent;
        color: {TEXT_MUTED};
        padding: 8px 18px;
        margin-right: 4px;
        border-bottom: 2px solid transparent;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{ color: {PINK}; border-bottom: 2px solid {PINK}; }}
    QTabBar::tab:hover {{ color: {TEXT}; }}

    /* ── ToolTips ── */
    QToolTip {{
        background-color: {BG_ELEVATED};
        color: {TEXT};
        border: 1px solid {BORDER_LIGHT};
        padding: 6px 8px;
        border-radius: 6px;
    }}

    /* ── ProgressBar ── */
    QProgressBar {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 8px;
        text-align: center;
        color: {TEXT};
    }}
    QProgressBar::chunk {{ background-color: {PINK}; border-radius: 7px; }}

    /* ── Menu ── */
    QMenu {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 8px 24px 8px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background-color: {rgba(PINK, 0.18)}; color: {PINK}; }}
    QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

    QSplitter::handle {{ background-color: {BORDER}; }}

    QListWidget {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 4px;
    }}
    QListWidget::item {{ padding: 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ background-color: {rgba(PINK, 0.18)}; color: {PINK}; }}

    QMessageBox {{ background-color: {BG_CARD}; }}
    """
