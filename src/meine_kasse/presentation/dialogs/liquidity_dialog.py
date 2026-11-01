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

from meine_kasse.application.services.booking_control_service import (
    MAX_YEAR,
    MIN_YEAR,
    BookingControlService,
)
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.domain.errors import DomainError
from meine_kasse.domain.services.planning_rules import MONTHS
from meine_kasse.domain.value_objects.money import format_euro
from meine_kasse.presentation.labels import MONTH_NAMES

_HEADERS = [
    "Monat",
    "Einnahmen (erwartet)",
    "Zuführung Rückstellung",
    "Zahlung ohne Rückstellung",
    "Bedarf",
    "Einnahmen − Bedarf",
    "Fortlaufend",
    "Status",
]
_BALANCE_COLUMN, _CUMULATIVE_COLUMN = 5, 6
_CLOSED_BACKGROUND = QBrush(QColor("#e6e6e6"))
_SHORT_FOREGROUND = QBrush(QColor("#b00020"))
_BAD = "color: #b00020;"
_GOOD = "color: #1b6e2d;"


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
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Liquiditätsplanung")
        self.resize(1000, 560)
        self._planning = planning

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

        close_button = QPushButton("S&chließen")
        close_button.clicked.connect(lambda _checked=False: self.accept())

        selection_row = QHBoxLayout()
        selection_row.addWidget(QLabel("Jahr:"))
        selection_row.addWidget(self.year_spin)
        selection_row.addStretch()
        buttons = QHBoxLayout()
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

    def _reload(self) -> None:
        year = self.year_spin.value()
        try:
            view = self._planning.get_liquidity_view(year)
        except DomainError as error:
            self.message_label.setText(str(error))
            self.message_label.setStyleSheet(_BAD)
            return
        cumulative = view.cumulative_cents
        for index, month in enumerate(view.months):
            short = month.balance_cents < 0
            values = [
                MONTH_NAMES[month.month - 1],
                format_euro(month.income_cents),
                format_euro(month.reserve_cents),
                format_euro(month.payment_cents),
                format_euro(month.need_cents),
                format_euro(month.balance_cents),
                format_euro(cumulative[month.month]),
                "abgeschlossen" if month.is_closed else ("Fehlbetrag" if short else "gedeckt"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if 0 < column < len(values) - 1:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
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
