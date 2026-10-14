from datetime import datetime
from types import SimpleNamespace

import pytest

from meine_kasse import build_info


def test_without_build_file_the_label_names_the_development_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_info, "_build_info", None)

    assert build_info.build_time() is None
    assert "Entwicklungsstand" in build_info.build_label()


def test_build_time_is_shown_in_german_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        build_info, "_build_info", SimpleNamespace(BUILD_TIMESTAMP="2026-10-14T13:20:05")
    )

    assert build_info.build_time() == datetime(2026, 10, 14, 13, 20, 5)
    assert build_info.build_label() == "Build vom 14.10.2026 13:20:05"


@pytest.mark.parametrize("raw", ["kein Datum", "", 42, None])
def test_invalid_build_value_is_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch, raw: object
) -> None:
    monkeypatch.setattr(build_info, "_build_info", SimpleNamespace(BUILD_TIMESTAMP=raw))

    assert build_info.build_time() is None
    assert "Entwicklungsstand" in build_info.build_label()
