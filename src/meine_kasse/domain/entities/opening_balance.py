from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountOpeningBalance:
    """Manuell erfasster Vortrag eines Kontos zum 01.01. des Jahres (vorzeichenbehaftet).

    Je Konto gibt es höchstens einen. Spätere Jahre leiten ihren Vortrag aus Vortrag und
    Buchungen ab.
    """

    id: str
    account_id: str
    year: int
    amount_cents: int
