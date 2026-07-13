"""
ui.settings_dialog
=====================
Admin-only Settings dialog: choose SQLite vs XAMPP/MySQL backend
(with connection test), configure SMTP mail, and configure SMS
(Semaphore/Twilio). Mirrors includes/config.php constants, exposed
through a GUI instead of hand-editing a PHP file.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget, QDialog, QStackedWidget,
)

from config.settings import get_settings, save_settings, DatabaseConfig
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import error as show_err, info as show_info, make_button


class DatabaseTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        cfg = get_settings().database

        lay.addWidget(QLabel("Database Backend"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("SQLite (local file, zero-config)", "sqlite")
        self.backend_combo.addItem("MySQL / MariaDB (XAMPP)", "mysql")
        self.backend_combo.setCurrentIndex(0 if cfg.backend == "sqlite" else 1)
        self.backend_combo.currentIndexChanged.connect(self._switch_backend)
        lay.addWidget(self.backend_combo)

        self.stack = QStackedWidget()

        sqlite_page = QWidget()
        sp = QVBoxLayout(sqlite_page)
        sp.addWidget(QLabel("Database File Path"))
        path_row = QHBoxLayout()
        self.sqlite_path = QLineEdit(cfg.sqlite_path)
        path_row.addWidget(self.sqlite_path)
        browse_btn = make_button("Browse...", "ghost")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        sp.addLayout(path_row)
        sp.addStretch()
        self.stack.addWidget(sqlite_page)

        mysql_page = QWidget()
        mp = QVBoxLayout(mysql_page)
        note = QLabel("This connects to your existing XAMPP MySQL/MariaDB server. "
                       "If a payroll_db database already exists there (from the original "
                       "PHP system), your existing employees/payroll/audit data will be used as-is.")
        note.setWordWrap(True)
        mp.addWidget(note)
        self.mysql_host = QLineEdit(cfg.mysql_host)
        self.mysql_port = QSpinBox()
        self.mysql_port.setRange(1, 65535)
        self.mysql_port.setValue(cfg.mysql_port)
        self.mysql_db = QLineEdit(cfg.mysql_db)
        self.mysql_user = QLineEdit(cfg.mysql_user)
        self.mysql_password = QLineEdit(cfg.mysql_password)
        self.mysql_password.setEchoMode(QLineEdit.EchoMode.Password)
        for label, widget in [("Host", self.mysql_host), ("Port", self.mysql_port),
                               ("Database Name", self.mysql_db), ("Username", self.mysql_user),
                               ("Password", self.mysql_password)]:
            mp.addWidget(QLabel(label))
            mp.addWidget(widget)
        mp.addStretch()
        self.stack.addWidget(mysql_page)

        self.stack.setCurrentIndex(0 if cfg.backend == "sqlite" else 1)
        lay.addWidget(self.stack)

        test_row = QHBoxLayout()
        test_btn = make_button("Test Connection", "ghost")
        test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(test_btn)
        test_row.addStretch()
        lay.addLayout(test_row)
        lay.addStretch()

    def _switch_backend(self):
        self.stack.setCurrentIndex(self.backend_combo.currentIndex())

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "Choose SQLite Database File", self.sqlite_path.text(),
                                               "SQLite Database (*.db)")
        if path:
            self.sqlite_path.setText(path)

    def build_config(self) -> DatabaseConfig:
        cfg = DatabaseConfig()
        cfg.backend = self.backend_combo.currentData()
        cfg.sqlite_path = self.sqlite_path.text().strip()
        cfg.mysql_host = self.mysql_host.text().strip()
        cfg.mysql_port = self.mysql_port.value()
        cfg.mysql_db = self.mysql_db.text().strip()
        cfg.mysql_user = self.mysql_user.text().strip()
        cfg.mysql_password = self.mysql_password.text()
        return cfg

    def _test_connection(self):
        cfg = self.build_config()
        db = get_db()
        ok, msg = db.test_connection(cfg)
        if ok:
            show_info(self, "Connection Successful", msg)
        else:
            show_err(self, "Connection Failed", msg)


class MailTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        cfg = get_settings().mail

        self.enabled = QCheckBox("Enable Email Notifications")
        self.enabled.setChecked(cfg.enabled)
        lay.addWidget(self.enabled)

        self.host = QLineEdit(cfg.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(cfg.port)
        self.encryption = QComboBox()
        self.encryption.addItems(["tls", "ssl"])
        self.encryption.setCurrentText(cfg.encryption)
        self.encryption.currentTextChanged.connect(self._sync_port_to_encryption)
        self.username = QLineEdit(cfg.username)
        self.password = QLineEdit(cfg.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.from_email = QLineEdit(cfg.from_email)
        self.from_name = QLineEdit(cfg.from_name)
        self.company_name = QLineEdit(cfg.company_name)

        for label, widget in [
            ("SMTP Host", self.host), ("SMTP Port", self.port), ("Encryption", self.encryption),
            ("SMTP Username", self.username), ("SMTP Password / App Password", self.password),
            ("From Email", self.from_email), ("From Name", self.from_name), ("Company Name", self.company_name),
        ]:
            lay.addWidget(QLabel(label))
            lay.addWidget(widget)
            if label == "Encryption":
                port_hint = QLabel("TLS normally uses port 587, SSL normally uses port 465 — "
                                    "the port above updates automatically when you switch this.")
                port_hint.setWordWrap(True)
                port_hint.setProperty("role", "muted")
                lay.addWidget(port_hint)

        hint = QLabel("For Gmail: enable 2FA, then create an App Password at "
                       "myaccount.google.com/apppasswords and use it here.")
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        lay.addWidget(hint)
        lay.addStretch()

    def _sync_port_to_encryption(self, encryption: str):
        # Only auto-adjust if the port is currently one of the two
        # well-known Gmail values — if someone already customized it for
        # a different provider, leave it alone.
        current = self.port.value()
        if encryption == "ssl" and current in (587, 25, 2525):
            self.port.setValue(465)
        elif encryption == "tls" and current in (465,):
            self.port.setValue(587)

    def apply_to(self, cfg):
        cfg.enabled = self.enabled.isChecked()
        cfg.host = self.host.text().strip()
        cfg.port = self.port.value()
        cfg.encryption = self.encryption.currentText()
        cfg.username = self.username.text().strip()
        cfg.password = self.password.text()
        cfg.from_email = self.from_email.text().strip()
        cfg.from_name = self.from_name.text().strip()
        cfg.company_name = self.company_name.text().strip()


class SmsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        cfg = get_settings().sms

        self.enabled = QCheckBox("Enable SMS Notifications")
        self.enabled.setChecked(cfg.enabled)
        lay.addWidget(self.enabled)

        self.provider = QComboBox()
        self.provider.addItems(["semaphore", "twilio"])
        self.provider.setCurrentText(cfg.provider)
        lay.addWidget(QLabel("Provider"))
        lay.addWidget(self.provider)

        self.api_key = QLineEdit(cfg.api_key)
        self.sender_name = QLineEdit(cfg.sender_name)
        lay.addWidget(QLabel("Semaphore API Key"))
        lay.addWidget(self.api_key)
        lay.addWidget(QLabel("Sender Name"))
        lay.addWidget(self.sender_name)

        self.twilio_sid = QLineEdit(cfg.twilio_sid)
        self.twilio_token = QLineEdit(cfg.twilio_token)
        self.twilio_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.twilio_from = QLineEdit(cfg.twilio_from)
        lay.addWidget(QLabel("Twilio Account SID"))
        lay.addWidget(self.twilio_sid)
        lay.addWidget(QLabel("Twilio Auth Token"))
        lay.addWidget(self.twilio_token)
        lay.addWidget(QLabel("Twilio From Number"))
        lay.addWidget(self.twilio_from)
        lay.addStretch()

    def apply_to(self, cfg):
        cfg.enabled = self.enabled.isChecked()
        cfg.provider = self.provider.currentText()
        cfg.api_key = self.api_key.text().strip()
        cfg.sender_name = self.sender_name.text().strip()
        cfg.twilio_sid = self.twilio_sid.text().strip()
        cfg.twilio_token = self.twilio_token.text()
        cfg.twilio_from = self.twilio_from.text().strip()


class GovRatesTab(QWidget):
    """SSS / PhilHealth / Pag-IBIG rates, editable here instead of in
    code — see database.models.ContributionRateConfig. BIR withholding
    tax brackets are also DB-backed (TaxBracket table) but aren't
    exposed here since there are ~24 rows across 4 pay-period types;
    updating those (rare — BIR revises them far less often than
    SSS/PhilHealth/Pag-IBIG) is a direct database edit for now."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        hint = QLabel("These feed core.gov_rates and are applied automatically on every payroll run — "
                      "no code change needed when SSS/PhilHealth/Pag-IBIG revise their schedules.")
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        lay.addWidget(hint)

        self.rows = {}
        from database.db_manager import get_db
        db = get_db()
        try:
            with db.session() as s:
                from database.models import ContributionRateConfig
                from sqlalchemy import select
                configs = {c.scheme: c for c in s.execute(select(ContributionRateConfig)).scalars().all()}
        except Exception:
            configs = {}

        for scheme, title in [("sss", "SSS"), ("philhealth", "PhilHealth"), ("pagibig", "Pag-IBIG")]:
            cfg = configs.get(scheme)
            box = QWidget()
            form = QVBoxLayout(box)
            form.addWidget(QLabel(f"<b>{title}</b>"))
            row = QHBoxLayout()
            ee = QDoubleSpinBox(); ee.setSuffix(" % (employee)"); ee.setRange(0, 100); ee.setDecimals(2)
            er = QDoubleSpinBox(); er.setSuffix(" % (employer)"); er.setRange(0, 100); er.setDecimals(2)
            floor = QDoubleSpinBox(); floor.setPrefix("Floor \u20b1 "); floor.setRange(0, 1_000_000)
            ceil = QDoubleSpinBox(); ceil.setPrefix("Ceiling \u20b1 "); ceil.setRange(0, 1_000_000)
            if cfg:
                ee.setValue(float(cfg.employee_rate) * 100)
                er.setValue(float(cfg.employer_rate) * 100)
                floor.setValue(float(cfg.salary_floor))
                ceil.setValue(float(cfg.salary_ceiling))
            for w in (ee, er, floor, ceil):
                row.addWidget(w)
            form.addLayout(row)
            low_ceil = low_ee = None
            if scheme == "pagibig":
                row2 = QHBoxLayout()
                low_ceil = QDoubleSpinBox(); low_ceil.setPrefix("Lower-tier up to \u20b1 "); low_ceil.setRange(0, 1_000_000)
                low_ee = QDoubleSpinBox(); low_ee.setSuffix(" % (employee, at/below that salary)"); low_ee.setRange(0, 100); low_ee.setDecimals(2)
                if cfg and cfg.low_tier_ceiling is not None:
                    low_ceil.setValue(float(cfg.low_tier_ceiling))
                    low_ee.setValue(float(cfg.low_tier_employee_rate or 0) * 100)
                row2.addWidget(low_ceil)
                row2.addWidget(low_ee)
                form.addLayout(row2)
            lay.addWidget(box)
            self.rows[scheme] = (ee, er, floor, ceil, low_ceil, low_ee)

        save_btn = make_button("Save Government Rates", "primary")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)
        lay.addStretch()

    def _save(self):
        from database.db_manager import get_db
        from database.models import ContributionRateConfig
        from sqlalchemy import select
        db = get_db()
        with db.session() as s:
            for scheme, (ee, er, floor, ceil, low_ceil, low_ee) in self.rows.items():
                cfg = s.execute(select(ContributionRateConfig).where(
                    ContributionRateConfig.scheme == scheme)).scalar_one_or_none()
                if not cfg:
                    cfg = ContributionRateConfig(scheme=scheme)
                    s.add(cfg)
                cfg.employee_rate = ee.value() / 100
                cfg.employer_rate = er.value() / 100
                cfg.salary_floor = floor.value()
                cfg.salary_ceiling = ceil.value()
                if low_ceil is not None:
                    cfg.low_tier_ceiling = low_ceil.value()
                    cfg.low_tier_employee_rate = low_ee.value() / 100
        show_info(self, "Saved", "Government contribution rates updated.")


class ThemeCard(QFrame):
    """One clickable theme option: label, tagline, and a 3-color swatch
    strip previewing its actual accent colors."""
    def __init__(self, spec, is_selected: bool, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._key = spec.key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(72)
        self._render(spec, is_selected)

    def _render(self, spec, is_selected: bool):
        border_color = theme.PINK if is_selected else theme.BORDER_LIGHT
        bg = theme.rgba(theme.PINK, 0.10) if is_selected else theme.BG_CARD
        self.setStyleSheet(f"""
            QFrame {{ background-color: {bg}; border: 1.5px solid {border_color}; border-radius: 10px; }}
        """)
        # Clear any previous layout/children (re-render on selection change)
        old_layout = self.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            QWidget().setLayout(old_layout)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(14)

        swatch = QWidget()
        swatch.setFixedSize(48, 48)
        swatch_lay = QHBoxLayout(swatch)
        swatch_lay.setContentsMargins(0, 0, 0, 0)
        swatch_lay.setSpacing(0)
        for i, c in enumerate(spec.swatch or (spec.PINK, spec.PURPLE, spec.CYAN)):
            chip = QLabel()
            chip.setFixedSize(16, 48)
            radius_css = ""
            if i == 0:
                radius_css = "border-top-left-radius: 8px; border-bottom-left-radius: 8px;"
            elif i == len(spec.swatch) - 1:
                radius_css = "border-top-right-radius: 8px; border-bottom-right-radius: 8px;"
            chip.setStyleSheet(f"background-color: {c}; {radius_css}")
            swatch_lay.addWidget(chip)
        lay.addWidget(swatch)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        name = QLabel(spec.label)
        name.setStyleSheet(f"font-weight: 700; font-size: 13.5px; color: {theme.TEXT_STRONG};")
        title_row.addWidget(name)
        if is_selected:
            check = QLabel("\u2713 Active")
            check.setStyleSheet(f"color: {theme.PINK}; font-weight: 700; font-size: 11px;")
            title_row.addWidget(check)
        title_row.addStretch()
        text_col.addLayout(title_row)
        tagline = QLabel(spec.tagline)
        tagline.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11.5px;")
        text_col.addWidget(tagline)
        lay.addLayout(text_col, 1)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._on_click(self._key)


class AppearanceTab(QWidget):
    """Lets anyone pick one of 5 themes — including the Special theme,
    whose accent color changes per page/section (see ui/theme.py's
    SPECIAL_SECTION_ACCENTS) — with an instant live preview. This isn't
    just for people who dislike the current look: it's the only way to
    actually try Special without committing to it first."""
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self._cards: list[ThemeCard] = []
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        hint = QLabel("Changes apply immediately across the whole app.")
        hint.setProperty("role", "muted")
        lay.addWidget(hint)
        self._card_container = QVBoxLayout()
        self._card_container.setSpacing(10)
        lay.addLayout(self._card_container)
        lay.addStretch()
        self._render_cards()

    def _render_cards(self):
        while self._card_container.count():
            item = self._card_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards = []
        current = theme.get_current_theme_key()
        for spec in theme.list_themes():
            card = ThemeCard(spec, spec.key == current, self._select_theme)
            self._card_container.addWidget(card)
            self._cards.append(card)

    def _select_theme(self, key: str):
        theme.set_theme(key)
        settings = get_settings()
        settings.theme = key
        save_settings(settings)
        if self._main_window is not None and hasattr(self._main_window, "rebuild_theme"):
            self._main_window.rebuild_theme()
        self._render_cards()


class AppearanceDialog(QDialog):
    """The role-agnostic theme picker — reachable by every user (admin
    or employee) from the topbar dropdown, unlike the full Settings
    dialog which stays admin-only."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Appearance")
        self.resize(480, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(AppearanceTab(main_window=parent))
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = make_button("Close", "primary")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(560, 560)
        lay = QVBoxLayout(self)

        tabs = QTabWidget()
        self.db_tab = DatabaseTab()
        self.mail_tab = MailTab()
        self.sms_tab = SmsTab()
        self.gov_tab = GovRatesTab()
        self.appearance_tab = AppearanceTab(main_window=parent)
        tabs.addTab(self.appearance_tab, "\U0001F3A8 Appearance")
        tabs.addTab(self.db_tab, "\U0001F5C4\uFE0F Database")
        tabs.addTab(self.mail_tab, "\U0001F4E7 Mail")
        tabs.addTab(self.sms_tab, "\U0001F4F1 SMS")
        tabs.addTab(self.gov_tab, "\U0001F3DB\uFE0F Gov't Rates")
        lay.addWidget(tabs, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = make_button("Cancel", "ghost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = make_button("Save Settings", "primary")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)

    def save(self):
        settings = get_settings()
        old_backend = settings.database.backend
        old_url_key = (settings.database.sqlite_path, settings.database.mysql_host,
                       settings.database.mysql_db, settings.database.mysql_user)

        settings.database = self.db_tab.build_config()
        self.mail_tab.apply_to(settings.mail)
        self.sms_tab.apply_to(settings.sms)
        save_settings(settings)

        new_url_key = (settings.database.sqlite_path, settings.database.mysql_host,
                       settings.database.mysql_db, settings.database.mysql_user)
        backend_changed = (old_backend != settings.database.backend) or (old_url_key != new_url_key)

        if backend_changed:
            from ui.widgets.common import confirm
            if confirm(self, "Switch Database Now?",
                       "Database settings changed. Reconnect now? (Choosing No just saves the "
                       "settings \u2014 restart PayrollPro later to apply them.)"):
                db = get_db()
                try:
                    db.connect(settings.database)
                    from database.seed_data import seed_if_empty
                    with db.session() as s:
                        seed_if_empty(s)
                    show_info(self, "Connected", "Successfully switched database backend.")
                except Exception as e:  # noqa: BLE001
                    show_err(self, "Connection Failed", f"Could not connect: {e}")
            else:
                show_info(self, "Settings Saved",
                           "Settings saved. Restart PayrollPro for the new database connection to take effect.")
        else:
            show_info(self, "Settings Saved", "Your settings have been saved.")
        self.accept()
