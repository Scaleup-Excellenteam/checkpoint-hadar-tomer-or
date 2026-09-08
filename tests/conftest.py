"""Shared fixtures for the phased test suite."""

import importlib
import sqlite3
import ssl
import sys
import aiohttp
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


@pytest.fixture
def isolated_server_module(monkeypatch, tmp_path):
    """Import the server handler with its database and TLS setup isolated."""
    monkeypatch.chdir(tmp_path)

    import logger

    class InertSSLContext:
        def __init__(self, protocol):
            self.protocol = protocol

        def load_cert_chain(self, *args, **kwargs):
            pass

    monkeypatch.setattr(ssl, "SSLContext", InertSSLContext)
    monkeypatch.setattr(logger, "setup_logger", lambda role: None)

    for module_name in tuple(sys.modules):
        if module_name == "Server" or module_name.startswith("Server."):
            del sys.modules[module_name]

    module = importlib.import_module("Server.Server")
    module.state.CLIENTS.clear()
    module.state.ROOMS.clear()

    try:
        yield module
    finally:
        module.state.CLIENTS.clear()
        module.state.ROOMS.clear()
        module.state.auth.db.close()

        for module_name in tuple(sys.modules):
            if module_name == "Server" or module_name.startswith("Server."):
                del sys.modules[module_name]
