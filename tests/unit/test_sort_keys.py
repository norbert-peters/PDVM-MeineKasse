from datetime import date

import pytest

from meine_kasse.presentation.widgets.sorting import (
    explicit_key,
    natural_key,
    sort_key_for_text,
)


def _sorted(texts: list[str]) -> list[str]:
    return sorted(texts, key=sort_key_for_text)


def test_euro_amounts_sort_by_value_not_text() -> None:
    texts = ["10,00 €", "9,00 €", "-2,50 €", "1.234,56 €", "0,99 €"]

    assert _sorted(texts) == ["-2,50 €", "0,99 €", "9,00 €", "10,00 €", "1.234,56 €"]


def test_dates_sort_chronologically_across_years() -> None:
    texts = ["02.01.2027", "15.12.2026", "01.02.2026"]

    assert _sorted(texts) == ["01.02.2026", "15.12.2026", "02.01.2027"]


def test_numbers_and_text_sort_naturally() -> None:
    assert _sorted(["300", "1000", "20"]) == ["20", "300", "1000"]
    assert _sorted(["Konto 10", "Konto 2", "konto 1"]) == ["konto 1", "Konto 2", "Konto 10"]


def test_empty_cells_come_first() -> None:
    assert _sorted(["5,00 €", "", "1,00 €"]) == ["", "1,00 €", "5,00 €"]


def test_invalid_date_is_treated_as_text() -> None:
    assert sort_key_for_text("31.02.2026")[0] == sort_key_for_text("abc")[0]


def test_percent_and_mixed_text_never_raise() -> None:
    values = ["5,000 %", "abc", "", "12", "01.01.2026", "-3,00 €"]

    assert len(_sorted(values)) == len(values)


def test_explicit_keys_sort_raw_values_with_none_first() -> None:
    keys = [explicit_key(1000), explicit_key(None), explicit_key(150)]

    assert [key for key in sorted(keys)] == [
        explicit_key(None),
        explicit_key(150),
        explicit_key(1000),
    ]


def test_explicit_date_ordinals_order_correctly() -> None:
    later = explicit_key(date(2026, 5, 2).toordinal())
    earlier = explicit_key(date(2026, 4, 20).toordinal())

    assert earlier < later


@pytest.mark.parametrize("text", ["a1b22", "007", "x"])
def test_natural_key_is_comparable(text: str) -> None:
    assert natural_key(text) <= natural_key(text)
