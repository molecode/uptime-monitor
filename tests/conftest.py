import pytest
import tempfile
import yaml
from unittest.mock import patch
from datetime import datetime
import pytz


@pytest.fixture
def mock_config():
    """Basic test configuration."""
    return {
        "email": {
            "smtp_server": "smtp.test.com",
            "smtp_port": 587,
            "username": "test@test.com",
            "password": "testpass",
            "notification_email": "notify@test.com",
        },
        "healthcheck": {"url": "https://hc-ping.com/test", "interval": 3600},
        "dashboard": {"password": "testpass"},
        "timezone": "UTC",
        "defaults": {"timeout": 5, "interval": 300, "max_tries": 3},
        "services": {
            "test-http": {
                "type": "http",
                "url": "https://example.com",
                "timeout": 5,
                "interval": 300,
                "max_tries": 3,
            },
            "test-port": {
                "type": "port",
                "host": "example.com",
                "port": 80,
                "timeout": 5,
                "interval": 300,
                "max_tries": 3,
            },
            "test-ping": {
                "type": "ping",
                "host": "example.com",
                "timeout": 5,
                "interval": 300,
                "max_tries": 3,
            },
        },
    }


@pytest.fixture
def config_file(mock_config):
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(mock_config, f)
        return f.name


@pytest.fixture
def mock_datetime():
    """Mock datetime for consistent testing."""
    with patch("uptime_monitor.datetime") as mock_dt:
        # Set a fixed datetime for testing
        mock_dt.now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=pytz.UTC)
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        yield mock_dt


@pytest.fixture
def mock_timezone():
    """Mock timezone for testing."""
    return pytz.UTC
