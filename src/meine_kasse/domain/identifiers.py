import uuid


def new_id() -> str:
    """Neue GUID im kanonischen Textformat. Primärschlüssel werden in der Anwendung erzeugt."""
    return str(uuid.uuid4())
