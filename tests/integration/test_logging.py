import io
import logging
import sys

import pytest

from logger import setup_logger


def _clear_root_handlers():
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    for handler in original_handlers:
        root_logger.removeHandler(handler)
    return root_logger, original_handlers


def _restore_root_handlers(root_logger, original_handlers):
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    for handler in original_handlers:
        root_logger.addHandler(handler)


@pytest.mark.integration
def test_setup_logger_writes_role_and_message_to_console_and_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    console = io.StringIO()
    monkeypatch.setattr(sys, "stderr", console)
    root_logger, original_handlers = _clear_root_handlers()

    try:
        setup_logger("PHASE_ONE")
        logging.getLogger("tests.phase_one").info("model logging is ready")

        for handler in root_logger.handlers:
            handler.flush()

        log_text = (tmp_path / "Log" / "app_phase_one.log").read_text(encoding="utf-8")
        assert "PHASE_ONE" in console.getvalue()
        assert "model logging is ready" in console.getvalue()
        assert "PHASE_ONE" in log_text
        assert "model logging is ready" in log_text
    finally:
        _restore_root_handlers(root_logger, original_handlers)


@pytest.mark.integration
def test_first_logging_configuration_remains_active(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    first_console = io.StringIO()
    second_console = io.StringIO()
    root_logger, original_handlers = _clear_root_handlers()

    try:
        monkeypatch.setattr(sys, "stderr", first_console)
        setup_logger("FIRST")
        monkeypatch.setattr(sys, "stderr", second_console)
        setup_logger("SECOND")
        logging.getLogger("tests.phase_one").info("only the first setup applies")

        for handler in root_logger.handlers:
            handler.flush()

        first_log = (tmp_path / "Log" / "app_first.log").read_text(encoding="utf-8")
        assert "FIRST" in first_log
        assert "only the first setup applies" in first_log
        if (tmp_path / "Log" / "app_second.log").exists():
            assert "only the first setup applies" not in (
                tmp_path / "Log" / "app_second.log"
            ).read_text(encoding="utf-8")
        assert "SECOND" not in first_console.getvalue()
        assert second_console.getvalue() == ""
    finally:
        _restore_root_handlers(root_logger, original_handlers)


@pytest.mark.integration
def test_controlled_server_import_creates_state_database_only_in_temp_directory(
    isolated_server_import, tmp_path
):
    state = isolated_server_import("Server.state")

    assert state.CLIENTS == {}
    assert state.ROOMS == {}
    assert (tmp_path / "DB" / "users.db").is_file()
