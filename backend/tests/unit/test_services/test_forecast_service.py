from typing import List

import pytest

from app.services.forecast_service import _trend


def test_trend_increasing():
    assert _trend([0.10, 0.20, 0.35]) == "increasing"


def test_trend_declining():
    assert _trend([0.50, 0.30, 0.10]) == "declining"


def test_trend_stable():
    assert _trend([0.30, 0.31, 0.29]) == "stable"


def test_trend_empty_returns_stable():
    assert _trend([]) == "stable"


def test_trend_single_value_returns_stable():
    assert _trend([0.42]) == "stable"


def test_trend_two_values_increasing():
    assert _trend([0.10, 0.50]) == "increasing"


def test_trend_two_values_declining():
    assert _trend([0.50, 0.10]) == "declining"
