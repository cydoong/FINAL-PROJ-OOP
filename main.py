"""ITO ANG NEED I-RUN. ITO ANG INITIAL/MAIN FILE NG SYSTEM"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_API", "PyQt6")

from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from config.settings import get_settings
from database.db_manager import get_db
from database.seed_data import seed_if_empty
from ui import theme
from ui.login_window import LoginWindow


class AppWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PayrollPro — Payroll & Workforce Management")
        self.resize(1360, 860)
        self.setMinimumSize(1024, 680)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self._show_main_window)
        self.stack.addWidget(self.login_window)
        self.stack.setCurrentWidget(self.login_window)

        self.main_window = None

    def _show_main_window(self):
        from ui.main_window import MainWindow
        if self.main_window is not None:
            self.stack.removeWidget(self.main_window)
            self.main_window.deleteLater()
        self.main_window = MainWindow()
        self.main_window.logout_requested.connect(self._show_login_window)
        self.stack.addWidget(self.main_window)
        self.stack.setCurrentWidget(self.main_window)

    def _show_login_window(self):
        new_login = LoginWindow()
        new_login.login_success.connect(self._show_main_window)
        self.stack.removeWidget(self.login_window)
        self.login_window.deleteLater()
        self.login_window = new_login
        self.stack.addWidget(self.login_window)
        self.stack.setCurrentWidget(self.login_window)
        if self.main_window is not None:
            self.stack.removeWidget(self.main_window)
            self.main_window.deleteLater()
            self.main_window = None


def bootstrap_database() -> tuple[bool, str]:
    """Connect to the configured database and seed reference data if empty.
    Returns (ok, error_message)."""
    settings = get_settings()
    db = get_db()
    try:
        db.connect(settings.database)
        with db.session() as s:
            seed_if_empty(s, settings.admin_default_password)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PayrollPro")
    app.setStyle("Fusion")
    theme.set_theme(get_settings().theme)
    app.setStyleSheet(theme.build_stylesheet())

    ok, err = bootstrap_database()
    if not ok:
        settings = get_settings()
        backend = settings.database.backend
        QMessageBox.critical(
            None, "Database Connection Failed",
            f"Could not connect to the {backend.upper()} database.\n\n{err}\n\n"
            f"The app will fall back to a local SQLite database. You can change this "
            f"later from Settings after logging in as admin.",
        )
        from config.settings import DatabaseConfig
        db = get_db()
        db.connect(DatabaseConfig(backend="sqlite"))
        with db.session() as s:
            seed_if_empty(s, get_settings().admin_default_password)

    window = AppWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
