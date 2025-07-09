import tempfile
import os
from unittest.mock import patch
from datetime import datetime, timedelta
import pytz

from uptime_monitor.dashboard import WebServiceMonitor, User


class TestUser:
    """Test User class."""

    def test_user_init(self):
        """Test User initialization."""
        user = User(1, "password123")
        assert user.id == 1
        assert user.password == "password123"
        assert user.theme == "dark"


class TestWebServiceMonitor:
    """Test WebServiceMonitor class."""

    def create_web_monitor(self, config_override=None):
        """Helper to create WebServiceMonitor with test config."""
        config = {
            "email": {},
            "timezone": "UTC",
            "dashboard": {"password": "testpass"},
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
            },
        }

        if config_override:
            config.update(config_override)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(config, f)
            monitor = WebServiceMonitor(f.name)
            return monitor, f.name

    def test_web_monitor_init(self):
        """Test WebServiceMonitor initialization."""
        monitor, config_file = self.create_web_monitor()

        assert monitor.host == "0.0.0.0"
        assert monitor.port == 8080
        assert monitor.user.password == "testpass"
        assert monitor.app is not None
        assert monitor.login_manager is not None

        os.unlink(config_file)

    def test_web_monitor_custom_host_port(self):
        """Test WebServiceMonitor with custom host and port."""
        monitor, config_file = self.create_web_monitor()
        monitor.host = "127.0.0.1"
        monitor.port = 9090

        assert monitor.host == "127.0.0.1"
        assert monitor.port == 9090

        os.unlink(config_file)

    def test_dashboard_config_property(self):
        """Test dashboard_config property."""
        monitor, config_file = self.create_web_monitor()

        dashboard_config = monitor.dashboard_config
        assert dashboard_config == {"password": "testpass"}

        os.unlink(config_file)

    def test_get_services_status(self):
        """Test _get_services_status method."""
        monitor, config_file = self.create_web_monitor()

        # Set up some service states
        monitor.service_states = {"test-http": True, "test-port": False}
        monitor.down_since = {"test-port": datetime.now() - timedelta(minutes=30)}

        with patch("uptime_monitor.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=pytz.UTC)

            services_status = monitor._get_services_status()

            # Check test-http service (UP)
            assert services_status["test-http"]["status"] == "UP"
            assert services_status["test-http"]["type"] == "http"
            assert services_status["test-http"]["url"] == "https://example.com"

            # Check test-port service (DOWN)
            assert services_status["test-port"]["status"] == "DOWN"
            assert services_status["test-port"]["type"] == "port"
            assert services_status["test-port"]["host"] == "example.com"
            assert services_status["test-port"]["port"] == 80
            assert "down_since" in services_status["test-port"]

        os.unlink(config_file)

    def test_get_services_status_maintenance(self):
        """Test _get_services_status with maintenance window."""
        monitor, config_file = self.create_web_monitor(
            {
                "services": {
                    "test-maintenance": {
                        "type": "http",
                        "url": "https://example.com",
                        "timeout": 5,
                        "interval": 300,
                        "max_tries": 3,
                        "maintenance_window": {"start": "02:00", "end": "04:00"},
                    }
                }
            }
        )

        # Mock maintenance window check
        with patch.object(monitor, "_is_in_maintenance", return_value=True):
            services_status = monitor._get_services_status()

            assert services_status["test-maintenance"]["status"] == "MAINTENANCE"

        os.unlink(config_file)

    def test_get_services_status_unknown(self):
        """Test _get_services_status with unknown service state."""
        monitor, config_file = self.create_web_monitor()

        # No service states set (should be UNKNOWN)
        services_status = monitor._get_services_status()

        assert services_status["test-http"]["status"] == "UNKNOWN"
        assert services_status["test-port"]["status"] == "UNKNOWN"

        os.unlink(config_file)


class TestWebServiceMonitorRoutes:
    """Test WebServiceMonitor Flask routes."""

    def create_test_client(self):
        """Create test client for Flask app."""
        config = {
            "email": {},
            "timezone": "UTC",
            "dashboard": {"password": "testpass"},
            "services": {
                "test-http": {
                    "type": "http",
                    "url": "https://example.com",
                    "timeout": 5,
                    "interval": 300,
                    "max_tries": 3,
                }
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(config, f)
            monitor = WebServiceMonitor(f.name)
            monitor.app.config["TESTING"] = True
            return monitor.app.test_client(), f.name

    def test_login_get(self):
        """Test GET request to login page."""
        client, config_file = self.create_test_client()

        response = client.get("/login")
        assert response.status_code == 200
        assert b"login" in response.data.lower()

        os.unlink(config_file)

    def test_login_post_success(self):
        """Test successful login."""
        client, config_file = self.create_test_client()

        response = client.post(
            "/login", data={"password": "testpass"}, follow_redirects=True
        )

        assert response.status_code == 200

        os.unlink(config_file)

    def test_login_post_failure(self):
        """Test failed login."""
        client, config_file = self.create_test_client()

        response = client.post("/login", data={"password": "wrongpass"})

        assert response.status_code == 200
        assert b"Invalid password" in response.data

        os.unlink(config_file)

    def test_home_requires_login(self):
        """Test home page requires login."""
        client, config_file = self.create_test_client()

        response = client.get("/")
        assert response.status_code == 302  # Redirect to login

        os.unlink(config_file)

    def test_logout(self):
        """Test logout functionality."""
        client, config_file = self.create_test_client()

        # Login first
        with client.session_transaction() as session:
            session["_user_id"] = "1"
            session["_fresh"] = True

        response = client.get("/logout")
        assert response.status_code == 302  # Redirect to login

        os.unlink(config_file)

    def test_toggle_theme(self):
        """Test theme toggle functionality."""
        client, config_file = self.create_test_client()

        # Test toggling from default (dark) to light
        response = client.get("/toggle-theme")
        assert response.status_code == 302

        # Check if cookie is set (would need to check Set-Cookie header)
        assert "Set-Cookie" in response.headers

        os.unlink(config_file)

    def test_home_with_login(self):
        """Test home page with valid login."""
        client, config_file = self.create_test_client()

        # Login first
        with client.session_transaction() as session:
            session["_user_id"] = "1"
            session["_fresh"] = True

        with patch(
            "uptime_monitor.dashboard.WebServiceMonitor._get_services_status"
        ) as mock_status:
            mock_status.return_value = {
                "test-http": {
                    "status": "UP",
                    "type": "http",
                    "url": "https://example.com",
                    "last_check": "2024-01-15 12:00:00 UTC",
                }
            }

            response = client.get("/")
            assert response.status_code == 200
            assert b"test-http" in response.data

        os.unlink(config_file)
