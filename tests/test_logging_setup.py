import logging

import pytest

from app.logging_setup import NOISY_HTTP_LOGGERS, quiet_http_logs


@pytest.fixture(autouse=True)
def reset_levels():
    """Put the loggers back afterwards, so other tests are not affected."""
    before = {name: logging.getLogger(name).level for name in NOISY_HTTP_LOGGERS}
    yield
    for name, level in before.items():
        logging.getLogger(name).setLevel(level)


def test_http_request_lines_are_not_logged():
    for name in NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
    quiet_http_logs()
    for name in NOISY_HTTP_LOGGERS:
        logger = logging.getLogger(name)
        assert not logger.isEnabledFor(logging.INFO)
        assert logger.isEnabledFor(logging.WARNING)


def test_importing_the_mcp_server_quiets_http_logs():
    for name in NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
    import importlib

    import app.mcp_server

    importlib.reload(app.mcp_server)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert not logging.getLogger("httpx2").isEnabledFor(logging.INFO)


def test_importing_the_bot_quiets_http_logs():
    for name in NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
    import importlib

    import app.bot

    importlib.reload(app.bot)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)


def test_a_real_request_leaves_no_url_in_the_log(caplog):
    import httpx

    for name in NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))

    with caplog.at_level(logging.INFO):
        client.get("https://example.invalid/secret-token-123")
    assert "secret-token-123" in caplog.text  # without our setting, the URL IS logged

    caplog.clear()
    quiet_http_logs()
    with caplog.at_level(logging.INFO):
        client.get("https://example.invalid/secret-token-123")
    assert "secret-token-123" not in caplog.text
