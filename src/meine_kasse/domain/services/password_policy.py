from meine_kasse.domain.errors import ValidationError

MIN_PASSWORD_LENGTH = 8


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein."
        )
    if not password.strip():
        raise ValidationError("Das Passwort darf nicht nur aus Leerzeichen bestehen.")
