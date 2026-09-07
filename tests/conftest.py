"""Shared fixtures for the phased test suite."""

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_server_import(monkeypatch, tmp_path):
    """Import server modules after moving database side effects into ``tmp_path``."""
    monkeypatch.chdir(tmp_path)

    for module_name in tuple(sys.modules):
        if module_name == "Server" or module_name.startswith("Server."):
            del sys.modules[module_name]

    try:
        yield importlib.import_module
    finally:
        state_module = sys.modules.get("Server.state")
        if state_module is not None:
            state_module.auth.db.close()

        for module_name in tuple(sys.modules):
            if module_name == "Server" or module_name.startswith("Server."):
                del sys.modules[module_name]


@pytest.fixture
def auth_manager_factory(monkeypatch, tmp_path):
    """Create AuthManager instances backed by one temporary SQLite database."""
    monkeypatch.chdir(tmp_path)
    from auth import AuthManager

    managers = []

    def create():
        manager = AuthManager()
        managers.append(manager)
        return manager

    yield create

    for manager in managers:
        try:
            manager.db.close()
        except sqlite3.Error:
            pass
