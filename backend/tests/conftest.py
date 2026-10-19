"""Shared test setup: a throwaway database and the Flask test client.

Run from the project root:   python -m pytest backend/tests -q
(needs: pip install -r requirements-dev.txt)
"""
import os
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import database  # noqa: E402

database.DB_PATH = os.path.join(tempfile.mkdtemp(), "test.db")   # never touch data/fandom_chars.db

import app as app_module  # noqa: E402
import text_module  # noqa: E402

HEADERS = {"Host": "localhost:5000"}   # the local-only guard rejects other hosts


@pytest.fixture(scope="session")
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(scope="session")
def H():
    return HEADERS
