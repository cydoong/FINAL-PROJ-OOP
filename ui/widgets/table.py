"""
ui.widgets.table
===================
DataTable: a thin convenience wrapper around QTableWidget so every
page builds tables the same way (headers, stretch, row height,
read-only cells, per-row action buttons).
"""
from __future__ import annotations

from typing import Callable, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidget,
    QTableWidgetItem, QWidget,
)

from ui.widgets.common import make_button, _variant_qss


class DataTable(QTableWidget):
    def __init__(self, headers: Sequence[str], parent=None):
        super().__init__(parent)
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(list(headers))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(46)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setStretchLastSection(True)
        self.setShowGrid(False)
        self.setWordWrap(False)

    def set_col_width(self, index: int, mode=QHeaderView.ResizeMode.ResizeToContents):
        self.horizontalHeader().setSectionResizeMode(index, mode)

    def clear_rows(self):
        self.setRowCount(0)

    def add_row(self, values: Sequence, item_flags_editable: bool = False) -> int:
        row = self.rowCount()
        self.insertRow(row)
        for col, val in enumerate(values):
            if isinstance(val, QWidget):
                self.setCellWidget(row, col, val)
            else:
                item = QTableWidgetItem(str(val) if val is not None else "")
                if not item_flags_editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row, col, item)
        return row

    def set_widget(self, row: int, col: int, widget: QWidget):
        self.setCellWidget(row, col, widget)


def icon_button(icon: str, variant: str, parent=None):
    """A small square icon-only button, used in table action bars —
    matches the original PHP system's compact pencil/key/trash icon
    buttons instead of full text labels (which were prone to getting
    clipped in narrow table cells)."""
    from PyQt6.QtWidgets import QPushButton
    from PyQt6.QtCore import Qt as _Qt
    btn = QPushButton(icon, parent)
    variant_qss = _variant_qss()
    if variant in variant_qss:
        btn.setProperty("variant", variant)
        css = variant_qss[variant] + "\nQPushButton { padding: 0px; font-size: 14px; }"
        btn.setStyleSheet(css)
    btn.setCursor(_Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(34, 30)
    return btn


def action_bar(actions: list) -> QWidget:
    """Build a small horizontal bar of icon-only action buttons for a
    table row. `actions` is a list of (icon, variant, callback, tooltip)
    — tooltip is required here since there's no text label to explain
    what the icon does."""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(6)
    for action in actions:
        icon, variant, cb = action[0], action[1], action[2]
        tooltip = action[3] if len(action) > 3 else None
        btn = icon_button(icon, variant)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.clicked.connect(cb)
        lay.addWidget(btn)
    lay.addStretch()
    box.setMinimumWidth(len(actions) * 40 + 8)
    return box
