"""Fixtures for the LIBI tests."""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/libi in every test."""
    yield


@pytest.fixture
def config_dir(hass, tmp_path):
    """Point the configuration directory at an empty folder of this test's own, so a test reads
    and writes its own automations.yaml and never the shared testing config."""
    hass.config.config_dir = str(tmp_path)
    return tmp_path
