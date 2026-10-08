"""Shared fixtures for the backend test suite.

Tests run fully offline: LLM calls go to the scripted "mock" provider and all
on-disk state (quality DB, PageIndex storage) goes to a temp directory.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="dealforge-tests-")
os.environ.setdefault("DATA_DIR", _TMP)
os.environ.setdefault("PAGEINDEX_STORAGE_DIR", os.path.join(_TMP, "pageindex"))

import pytest  # noqa: E402

from app.core.harness.mock_llm import (  # noqa: E402
    MOCK_PROVIDER,
    MockLLMClient,
    install_mock_provider,
    route_all_agents_to,
)


@pytest.fixture
def mock_llm():
    """A fresh scripted LLM installed as provider "mock" for every agent."""
    client = install_mock_provider(MockLLMClient())
    route_all_agents_to(MOCK_PROVIDER)
    return client


@pytest.fixture
def gateway():
    """A fresh LLMGateway (no shared cache / rate-limit state between tests)."""
    from app.core.llm.llm_gateway import LLMGateway

    return LLMGateway()
