import re

from meine_kasse.domain.errors import ValidationError

_IBAN_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def normalize_iban(value: str) -> str:
    """Prüft eine IBAN (Format und Prüfziffer) und gibt sie ohne Leerzeichen zurück."""
    iban = value.replace(" ", "").upper()
    if not _IBAN_PATTERN.match(iban):
        raise ValidationError("Die IBAN hat ein ungültiges Format.")
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    if int(digits) % 97 != 1:
        raise ValidationError("Die IBAN ist ungültig (Prüfziffer stimmt nicht).")
    return iban
