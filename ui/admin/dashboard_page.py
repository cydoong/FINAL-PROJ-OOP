"""
ui.admin.dashboard_page
===========================
Admin landing page: KPI stat cards, a payroll trend chart, department
headcount breakdown, and recent activity tables. Exact data source:
core.dashboard_service.get_admin_dashboard().
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from core.dashboard_service import get_admin_dashboard
from core.utils import format_currency, format_datetime
from database.db_manager import get_db
from ui import theme
from ui.widgets.common import Badge, SectionHeader, StatCard
from ui.widgets.table import DataTable


def _style_axes(ax, fig):
    fig.patch.set_facecolor(theme.BG_CARD)
    ax.set_facecolor(theme.BG_CARD)
    ax.tick_params(colors=theme.TEXT_MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(theme.BORDER)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=theme.BORDER, linewidth=0.6, alpha=0.5)
    ax.set_axisbelow(True)


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(20)
        self.refresh()

    def refresh(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        db = get_db()
        with db.session() as s:
            d = get_admin_dashboard(s)

        header = SectionHeader("Dashboard", "Overview of your workforce and payroll activity")
        self.lay.addWidget(header)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)
        kpi_row.addWidget(StatCard("Active Employees", str(d.total_employees), "\U0001F465", theme.PINK))
        kpi_row.addWidget(StatCard("Departments", str(d.total_departments), "\U0001F3E2", theme.PURPLE))
        kpi_row.addWidget(StatCard("Open Pay Periods", str(d.open_periods), "\U0001F4C5", theme.CYAN))
        kpi_row.addWidget(StatCard("Draft Payrolls", str(d.draft_payroll), "\u23F3", theme.WARNING))
        self.lay.addLayout(kpi_row)

        if d.latest_paid:
            lp = d.latest_paid
            banner = Card()
            bl = QHBoxLayout(banner)
            bl.setContentsMargins(20, 16, 20, 16)
            icon = QLabel("\u2705")
            icon.setStyleSheet("font-size: 22px;")
            bl.addWidget(icon)
            txt = QLabel(f"Latest completed payroll: <b>{lp['period_name']}</b> \u2014 "
                         f"{lp['emp_count']} employee(s) paid, totaling "
                         f"<b style='color:{theme.SUCCESS}'>{format_currency(lp['total_net'])}</b> net.")
            txt.setStyleSheet(f"color: {theme.TEXT_DIM};")
            bl.addWidget(txt, 1)
            self.lay.addWidget(banner)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        trend_card = Card()
        tl = QVBoxLayout(trend_card)
        tl.setContentsMargins(20, 16, 20, 16)
        tl.addWidget(self._section_title("Payroll Trend (Net Pay, last 6 periods)"))
        if d.trend:
            fig = Figure(figsize=(5.5, 3), dpi=100)
            ax = fig.add_subplot(111)
            names = [t["period_name"][:12] for t in d.trend]
            values = [t["net"] for t in d.trend]
            ax.plot(names, values, color=theme.PINK, marker="o", linewidth=2.4, markersize=5)
            ax.fill_between(range(len(values)), values, color=theme.PINK, alpha=0.12)
            _style_axes(ax, fig)
            fig.tight_layout()
            tl.addWidget(FigureCanvas(fig))
        else:
            tl.addWidget(self._empty_label("No payroll history yet."))
        charts_row.addWidget(trend_card, 3)

        dept_card = Card()
        dl = QVBoxLayout(dept_card)
        dl.setContentsMargins(20, 16, 20, 16)
        dl.addWidget(self._section_title("Headcount by Department"))
        if d.dept_breakdown and sum(x["emp_count"] for x in d.dept_breakdown) > 0:
            fig2 = Figure(figsize=(3.6, 3), dpi=100)
            ax2 = fig2.add_subplot(111)
            labels = [x["department_name"][:14] for x in d.dept_breakdown]
            sizes = [x["emp_count"] for x in d.dept_breakdown]
            colors = [theme.PINK, theme.PURPLE, theme.CYAN, theme.SUCCESS, theme.WARNING, theme.INFO]
            wedges, _ = ax2.pie(sizes, colors=colors[:len(sizes)], startangle=90,
                                 wedgeprops={"width": 0.42, "edgecolor": theme.BG_CARD})
            ax2.legend(wedges, [f"{l} ({s})" for l, s in zip(labels, sizes)],
                       loc="center left", bbox_to_anchor=(1, 0.5), fontsize=7,
                       labelcolor=theme.TEXT_DIM, frameon=False)
            fig2.patch.set_facecolor(theme.BG_CARD)
            fig2.tight_layout()
            dl.addWidget(FigureCanvas(fig2))
        else:
            dl.addWidget(self._empty_label("No department data yet."))
        charts_row.addWidget(dept_card, 2)

        self.lay.addLayout(charts_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        payroll_card = Card()
        pl = QVBoxLayout(payroll_card)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.addWidget(self._section_title("Recent Payroll Activity"))
        table = DataTable(["Employee", "Department", "Period", "Net Pay", "Status"])
        table.setMinimumHeight(260)
        for row in d.recent_payroll:
            r = table.add_row([row["emp_name"], row["department_name"], row["period_name"],
                                format_currency(row["net_pay"]), ""])
            table.set_widget(r, 4, Badge(row["status"]))
        pl.addWidget(table)
        bottom_row.addWidget(payroll_card, 3)

        audit_card = Card()
        al = QVBoxLayout(audit_card)
        al.setContentsMargins(20, 16, 20, 16)
        al.addWidget(self._section_title("Recent Activity"))
        for a in d.recent_audit[:8]:
            row = QHBoxLayout()
            dot = QLabel("\u2022")
            dot.setStyleSheet(f"color: {theme.PINK}; font-size: 16px;")
            row.addWidget(dot)
            text = QLabel(f"<b>{(a['username'] or 'System')}</b> \u2014 {a['action'].replace('_',' ').title()}")
            text.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12px;")
            text.setWordWrap(True)
            row.addWidget(text, 1)
            al.addLayout(row)
            ts = QLabel(format_datetime(a["logged_at"]))
            ts.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; margin-left: 16px;")
            al.addWidget(ts)
        al.addStretch()
        bottom_row.addWidget(audit_card, 2)

        self.lay.addLayout(bottom_row)
        self.lay.addStretch()

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {theme.TEXT_STRONG}; margin-bottom: 8px;")
        return lbl

    @staticmethod
    def _empty_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; padding: 40px;")
        return lbl
