import pytest

from app.config import parse_user_ids


def test_parses_comma_separated_ids():
    assert parse_user_ids("123, 456,789") == {123, 456, 789}


def test_empty_means_nobody():
    assert parse_user_ids("") == frozenset()
    assert parse_user_ids(" , ") == frozenset()


def test_rejects_non_numeric():
    with pytest.raises(ValueError):
        parse_user_ids("123,@kaamesh")
