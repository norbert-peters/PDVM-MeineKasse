"""Fachliche Fehler. Die Meldungen sind für Anwender bestimmt und deshalb deutsch."""


class DomainError(Exception):
    """Basisklasse für alle fachlichen Fehler."""


class ValidationError(DomainError):
    """Eingabe oder Daten verletzen eine fachliche Regel."""


class AuthenticationError(DomainError):
    """Anmeldung fehlgeschlagen. Die Meldung verrät nie, ob der Anwender existiert."""


class DuplicateError(DomainError):
    """Ein eindeutiger Wert (z. B. eine Nummer) ist bereits vergeben."""


class NotFoundError(DomainError):
    """Ein Datensatz wurde nicht gefunden."""


class PeriodError(DomainError):
    """Der Buchungszeitraum ist nicht zulässig oder bereits abgeschlossen."""


class PlanPeriodError(PeriodError):
    """Das Planjahr des Entstehungsdatums ist nicht vorhanden oder abgeschlossen."""


class BudgetExceededError(DomainError):
    """Der Ansatz würde überschritten bzw. unterschritten."""

    def __init__(self, message: str, shortfall_cents: int) -> None:
        super().__init__(message)
        self.shortfall_cents = shortfall_cents
