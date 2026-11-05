from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.reporting.pdf_model import PdfColumn, PdfRow, PdfTable, RowStyle
from meine_kasse.application.services.booking_control_service import (
    MAX_YEAR,
    MIN_YEAR,
    BookingControlService,
)
from meine_kasse.application.services.liquidity_planning import LiquidityView
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.domain.errors import DomainError
from meine_kasse.domain.services.liquidity_rules import LiquidityMonth
from meine_kasse.domain.services.planning_rules import MONTHS
from meine_kasse.domain.value_objects.money import format_euro
from meine_kasse.presentation.labels import MONTH_NAMES
from meine_kasse.presentation.widgets.pdf_export import PdfExporter

_HEADERS = [
    "Monat",
    "Geldfluss Bank\n(nur Info)",
    "Bewegung Rücklagen\n(nur Info)",
    "Einnahmen\n(erwartet)",
    "Zuführung\nRückstellung",
    "Zahlung ohne\nRückstellung",
    "Bedarf",
    "Einnahmen −\nBedarf",
    "Fortlaufend",
    "Status",
]
_INFO_COLUMNS = (1, 2)
_BALANCE_COLUMN, _CUMULATIVE_COLUMN = 7, 8
_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_SHORT_FOREGROUND = QBrush(QColor("#b00020"))
_INFO_FOREGROUND = QBrush(QColor("#666666"))
_BAD = "color: #b00020;"
_GOOD = "color: #1b6e2d;"


def _status(month: LiquidityMonth) -> str:
    if month.is_closed:
        return "abgeschlossen"
    return "Fehlbetrag" if month.balance_cents < 0 else "gedeckt"


class LiquidityDialog(QDialog):
    """Liquiditätsplanung: Einnahmen gegen Rückstellungszuführung und Zahlungen je Monat.

    Der Dialog ist lesend. Einnahmen kommen aus der Einnahmenplanung (auch Entnahmen aus
    Anlagevermögen oder Betriebsmitteln, wenn sie dort als Einnahme geplant sind), der Bedarf aus
    der Kostenstellenplanung.
    """

    def __init__(
        self,
        planning: PlanningService,
        control: BookingControlService,
        parent: QWidget | None = None,
        exporter: PdfExporter | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Liquiditätsplanung")
        self.resize(1100, 560)
        self._planning = planning
        self._exporter = exporter
        self._view: LiquidityView | None = None

        self.year_spin = QSpinBox()
        self.year_spin.setRange(MIN_YEAR, MAX_YEAR)
        self.year_spin.setValue(control.get().current_year)
        self.summary_label = QLabel()
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.table = QTableWidget(len(MONTHS), len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setTextElideMode(Qt.TextElideMode.ElideNone)

        close_button = QPushButton("S&chließen")
        close_button.clicked.connect(lambda _checked=False: self.accept())
        self.pdf_button = QPushButton("&PDF…")
        self.pdf_button.clicked.connect(lambda _checked=False: self._export_pdf())
        self.pdf_button.setVisible(exporter is not None)

        selection_row = QHBoxLayout()
        selection_row.addWidget(QLabel("Jahr:"))
        selection_row.addWidget(self.year_spin)
        selection_row.addStretch()
        buttons = QHBoxLayout()
        buttons.addWidget(self.pdf_button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_row)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)

        self.year_spin.valueChanged.connect(lambda _value: self._reload())
        self._reload()

    def pdf_table(self) -> PdfTable | None:
        """Die Liquiditätsplanung des gewählten Jahres als PDF-Tabelle (`None` ohne Daten)."""
        view = self._view
        if view is None:
            return None
        cumulative = view.cumulative_cents
        rows = tuple(
            PdfRow(
                (
                    MONTH_NAMES[month.month - 1],
                    format_euro(month.bank_outflow_cents),
                    format_euro(month.reserve_movement_cents),
                    format_euro(month.income_cents),
                    format_euro(month.reserve_cents),
                    format_euro(month.payment_cents),
                    format_euro(month.need_cents),
                    format_euro(month.balance_cents),
                    format_euro(cumulative[month.month]),
                    _status(month),
                )
            )
            for month in view.months
        )
        total = PdfRow(
            (
                "Gesamt",
                format_euro(sum(month.bank_outflow_cents for month in view.months)),
                format_euro(sum(month.reserve_movement_cents for month in view.months)),
                format_euro(view.income_cents),
                format_euro(sum(month.reserve_cents for month in view.months)),
                format_euro(sum(month.payment_cents for month in view.months)),
                format_euro(view.need_cents),
                format_euro(view.balance_cents),
                "",
                "",
            ),
            RowStyle.TOTAL,
        )
        return PdfTable(
            title=f"Liquiditätsplanung {view.year}",
            columns=tuple(
                PdfColumn(header.replace("\n", " "), align_right=0 < index < len(_HEADERS) - 1)
                for index, header in enumerate(_HEADERS)
            ),
            rows=rows,
            subtitle_lines=(self.message_label.text(),),
            total_row=total,
        )

    def _export_pdf(self) -> None:
        table = self.pdf_table()
        if self._exporter is not None and table is not None:
            self._exporter.export(self, table)

    def _reload(self) -> None:
        year = self.year_spin.value()
        try:
            view = self._planning.get_liquidity_view(year)
        except DomainError as error:
            self._view = None
            self.message_label.setText(str(error))
            self.message_label.setStyleSheet(_BAD)
            return
        self._view = view
        cumulative = view.cumulative_cents
        for index, month in enumerate(view.months):
            short = month.balance_cents < 0
            values = [
                MONTH_NAMES[month.month - 1],
                format_euro(month.bank_outflow_cents),
                format_euro(month.reserve_movement_cents),
                format_euro(month.income_cents),
                format_euro(month.reserve_cents),
                format_euro(month.payment_cents),
                format_euro(month.need_cents),
                format_euro(month.balance_cents),
                format_euro(cumulative[month.month]),
                _status(month),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if 0 < column < len(values) - 1:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column in _INFO_COLUMNS:
                    item.setForeground(_INFO_FOREGROUND)
                if month.is_closed:
                    item.setBackground(_CLOSED_BACKGROUND)
                if (column == _BALANCE_COLUMN and short) or (
                    column == _CUMULATIVE_COLUMN and cumulative[month.month] < 0
                ):
                    item.setForeground(_SHORT_FOREGROUND)
                self.table.setItem(index, column, item)

        self.summary_label.setText(
            f"Einnahmen {format_euro(view.income_cents)} − Bedarf {format_euro(view.need_cents)} "
            f"= {format_euro(view.balance_cents)}"
        )
        short_months = view.shortfall_months
        if short_months:
            names = ", ".join(MONTH_NAMES[month - 1] for month in short_months)
            self.message_label.setText(
                f"Die Einnahmen decken den Bedarf nicht in: {names}. "
                "Liquidität z. B. durch eine geplante Entnahme aus Anlagevermögen oder "
                "Betriebsmitteln als Einnahme in der Einnahmenplanung sichern."
            )
            self.message_label.setStyleSheet(_BAD)
        else:
            self.message_label.setText("Die Einnahmen decken den Bedarf in jedem Monat.")
            self.message_label.setStyleSheet(_GOOD)
