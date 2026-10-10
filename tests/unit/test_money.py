from decimal import Decimal

import pytest

from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.value_objects.iban import normalize_iban
from meine_kasse.domain.value_objects.money import (
    allocate_by_percent,
    format_euro,
    format_percent,
    from_cents,
    parse_euro,
    to_cents,
)


def test_to_cents_is_exact_and_keeps_sign() -> None:
    assert to_cents(Decimal("12.34")) == 1234
    assert to_cents(Decimal("-0.05")) == -5
    assert to_cents("1000") == 100000


def test_to_cents_rejects_more_than_two_decimals() -> None:
    with pytest.raises(ValidationError):
        to_cents(Decimal("1.001"))


def test_to_cents_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        to_cents("abc")


def test_from_cents_roundtrip() -> None:
    assert from_cents(-1234) == Decimal("-12.34")


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (123456, "1.234,56 €"),
        (-123456, "-1.234,56 €"),
        (5, "0,05 €"),
        (-5, "-0,05 €"),
        (0, "0,00 €"),
    ],
)
def test_format_euro(cents: int, expected: str) -> None:
    assert format_euro(cents) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1.234,56", 123456), ("-5,5", -550), ("12 €", 1200), ("0,05", 5), ("+7", 700)],
)
def test_parse_euro(text: str, expected: int) -> None:
    assert parse_euro(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "1234.56", "1,234,56", "12,345"])
def test_parse_euro_rejects_invalid_input(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_euro(text)


def test_format_percent_has_at_least_three_decimals() -> None:
    assert format_percent(Decimal("33.3")) == "33,300 %"
    assert format_percent(Decimal("12.34567")) == "12,34567 %"


def test_allocation_sums_to_total_and_assigns_remainder_to_largest_share() -> None:
    shares = [Decimal("33.333"), Decimal("33.333"), Decimal("33.334")]
    parts = allocate_by_percent(1000, shares)
    assert sum(parts) == 1000
    assert parts == [333, 333, 334]


def test_allocation_keeps_negative_sign() -> None:
    parts = allocate_by_percent(-1000, [Decimal(50), Decimal(30), Decimal(20)])
    assert parts == [-500, -300, -200]


def test_allocation_remainder_goes_to_first_of_equal_shares() -> None:
    parts = allocate_by_percent(100, [Decimal(50), Decimal(50)])
    assert parts == [50, 50]
    parts = allocate_by_percent(1, [Decimal(50), Decimal(50)])
    assert sum(parts) == 1


def test_allocation_requires_one_hundred_percent() -> None:
    with pytest.raises(ValidationError):
        allocate_by_percent(100, [Decimal(60), Decimal(30)])


def test_iban_valid_and_normalized() -> None:
    assert normalize_iban("de89 3704 0044 0532 0130 00") == "DE89370400440532013000"


@pytest.mark.parametrize(
    "value", ["DE00370400440532013000", "12345", "DE89 3704 0044 0532 0130 01"]
)
def test_iban_invalid(value: str) -> None:
    with pytest.raises(ValidationError):
        normalize_iban(value)
