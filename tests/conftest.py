"""Shared fixtures."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


@pytest.fixture(autouse=True)
def no_delay():
    """Do not wait between page loads in tests."""
    with (
        patch("custom_components.matpriskollen.api.REQUEST_DELAY", 0),
        patch("custom_components.matpriskollen.coordinator.REQUEST_DELAY", 0),
    ):
        yield
