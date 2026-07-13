"""
ui.admin.notifications_page
===============================
Notification history + test send diagnostics, exact port of
admin/notifications.php.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import core.notification_service as ns
from core.utils import format_datetime
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import Badge, SectionHeader, StatCard, error as show_err, info as show_info, make_button
from ui.widgets.table import DataTable


class NotificationsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        header = SectionHeader("Notifications & Diagnostics", "Email/SMS delivery history and testing tools")
        lay.addWidget(header)

        self.kpi_row = QHBoxLayout()
        lay.addLayout(self.kpi_row)

        test_row = QHBoxLayout()
        self.test_target = QLineEdit()
        self.test_target.setPlaceholderText("Email or phone number to test...")
        test_row.addWidget(self.test_target)
        test_email_btn = make_button("Send Test Email", "ghost")
        test_email_btn.clicked.connect(self.send_test_email)
        test_row.addWidget(test_email_btn)
        test_sms_btn = make_button("Send Test SMS", "ghost")
        test_sms_btn.clicked.connect(self.send_test_sms)
        test_row.addWidget(test_sms_btn)
        lay.addLayout(test_row)

        filters = QHBoxLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("All Channels", "")
        self.channel_combo.addItem("Email", "email")
        self.channel_combo.addItem("SMS", "sms")
        self.channel_combo.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.channel_combo)
        self.status_combo = QComboBox()
        self.status_combo.addItem("All Statuses", "")
        self.status_combo.addItem("Sent", "sent")
        self.status_combo.addItem("Failed", "failed")
        self.status_combo.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.status_combo)
        filters.addStretch()
        lay.addLayout(filters)

        self.table = DataTable(["Channel", "Type", "Recipient", "Subject", "Status", "Error", "Sent At"])
        lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        while self.kpi_row.count():
            item = self.kpi_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        db = get_db()
        with db.session() as s:
            stats = ns.notification_stats(s)
            rows, total = ns.list_notifications(s, self.channel_combo.currentData(), self.status_combo.currentData(),
                                                 1, 50)

        self.kpi_row.addWidget(StatCard("Total Sent", str(stats["total"]), "\U0001F4EC", theme.PINK))
        self.kpi_row.addWidget(StatCard("Successful", str(stats["sent"]), "\u2705", theme.SUCCESS))
        self.kpi_row.addWidget(StatCard("Failed", str(stats["failed"]), "\u274C", theme.DANGER))
        self.kpi_row.addWidget(StatCard("Today", str(stats["today"]), "\U0001F4C5", theme.CYAN))

        self.table.clear_rows()
        for n in rows:
            r = self.table.add_row([n.channel.upper(), n.notif_type.replace("_", " ").title(), n.recipient,
                                     n.subject or "\u2014", "", n.error_message or "\u2014",
                                     format_datetime(n.created_at)])
            self.table.set_widget(r, 4, Badge(n.status))

    def send_test_email(self):
        target = self.test_target.text().strip()
        if not target:
            show_err(self, "Missing Target", "Enter an email address to test.")
            return
        from core.notifications import send_email, email_template
        result = send_email(target, "Test Recipient", "PayrollPro \u2014 Test Email",
                             email_template("Test", "<p>This is a test email from PayrollPro Settings.</p>"))
        if result.success:
            show_info(self, "Sent", "Test email sent successfully!")
        else:
            show_err(self, "Failed", result.error or "Could not send test email. Check Settings \u2192 Mail.")
        self.refresh()

    def send_test_sms(self):
        target = self.test_target.text().strip()
        if not target:
            show_err(self, "Missing Target", "Enter a phone number to test.")
            return
        from core.notifications import send_sms
        result = send_sms(target, "This is a test SMS from PayrollPro.")
        if result.success:
            show_info(self, "Sent", "Test SMS sent successfully!")
        else:
            show_err(self, "Failed", result.error or "Could not send test SMS. Check Settings \u2192 SMS.")
        self.refresh()
