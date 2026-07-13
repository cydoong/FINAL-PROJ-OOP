"""
ui.widgets.dialogs
=====================
BaseFormDialog: a consistent modal shell (title, scrollable form body,
footer Cancel/Save buttons) used by every Add/Edit dialog in the app.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget, QFrame,
)

from ui import theme
from ui.widgets.common import make_button


class BaseFormDialog(QDialog):
    def __init__(self, title: str, subtitle: str = "", parent=None, width: int = 620, height: int = 680):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setModal(True)
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(f"background-color: {theme.BG_ELEVATED}; border-top-left-radius: 12px; "
                              f"border-top-right-radius: 12px;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 20, 24, 20)
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {theme.TEXT_STRONG};")
        hl.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
            hl.addWidget(s)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.form_layout = QFormLayout(self.body)
        self.form_layout.setContentsMargins(24, 20, 24, 12)
        self.form_layout.setSpacing(14)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(self.body)
        outer.addWidget(scroll, 1)

        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.error_label.setContentsMargins(24, 0, 24, 8)
        outer.addWidget(self.error_label)

        footer = QFrame()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 12, 24, 20)
        fl.addStretch()
        self.cancel_btn = make_button("Cancel", "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn = make_button("Save", "primary")
        fl.addWidget(self.cancel_btn)
        fl.addWidget(self.save_btn)
        outer.addWidget(footer)

        # NOTE: this used to call self.resize(width, self.sizeHint().height())
        # right here — but at this point no subclass has added any rows yet
        # (add_row() is always called AFTER super().__init__() returns), so
        # the form was still empty and sizeHint() came back tiny. That's why
        # dialogs were opening with only one field visible, needing a scroll
        # to find the rest. A generous fixed default fixes it for every
        # dialog without needing each one to be measured individually.
        self.resize(width, height)

    def add_row(self, label: str, widget: QWidget):
        self.form_layout.addRow(label, widget)

    def add_full_row(self, widget: QWidget):
        self.form_layout.addRow(widget)

    def set_row_visible(self, widget: QWidget, visible: bool):
        """Show/hide a previously-added row (both its label and field)."""
        lbl = self.form_layout.labelForField(widget)
        if lbl is not None:
            lbl.setVisible(visible)
        widget.setVisible(visible)

    def show_error(self, message: str):
        self.error_label.setText("\u26A0  " + message)
        self.error_label.setVisible(True)

    def clear_error(self):
        self.error_label.setVisible(False)
