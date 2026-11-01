from datetime import datetime

import pytest

from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.services.document_rules import (
    build_file_name,
    clean_suffix,
    sanitize_name_part,
)

MOMENT = datetime(2026, 5, 15, 14, 30, 5)


def test_file_name_has_machine_part_and_suffix() -> None:
    assert build_file_name(MOMENT, "Buchungen", "Mai Abrechnung") == (
        "2026-05-15_143005_Buchungen_Mai_Abrechnung.pdf"
    )


def test_file_name_without_suffix() -> None:
    assert build_file_name(MOMENT, "Buchungen") == "2026-05-15_143005_Buchungen.pdf"


def test_forbidden_characters_are_removed() -> None:
    assert sanitize_name_part('a<b>c:d"e/f\\g|h?i*j') == "abcdefghij"
    assert build_file_name(MOMENT, "Plan/Ist: 2026", "..\\..\\x") == (
        "2026-05-15_143005_PlanIst_2026_x.pdf"
    )


def test_path_traversal_cannot_leave_the_directory() -> None:
    name = build_file_name(MOMENT, "../../Windows", "../evil")

    assert "/" not in name
    assert "\\" not in name
    assert ".." not in name


def test_empty_table_name_gets_a_fallback() -> None:
    assert build_file_name(MOMENT, "///") == "2026-05-15_143005_Tabelle.pdf"


def test_suffix_of_40_characters_is_allowed_and_41_is_rejected() -> None:
    assert clean_suffix("x" * 40) == "x" * 40
    with pytest.raises(ValidationError, match="höchstens 40 Zeichen"):
        clean_suffix("x" * 41)
