import pytest
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import pytz

from uptime_monitor import ServiceMonitor


class TestServiceMonitor:
    """Test ServiceMonitor class initialization and basic functionality."""

    def test_init_with_config(self, config_file, mock_config):
        """Test ServiceMonitor initialization with config file."""
        monitor = ServiceMonitor(config_file)

        assert monitor.config == mock_config
        assert monitor.service_states == {}
        assert monitor.down_since == {}
        assert monitor.timezone == "UTC"
        assert monitor.tz == pytz.UTC

        # Clean up
        os.unlink(config_file)

    def test_init_with_invalid_timezone(self, mock_config):
        """Test ServiceMonitor handles invalid timezone gracefully."""
        mock_config["timezone"] = "Invalid/Timezone"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(mock_config, f)
            config_file = f.name

        with patch("uptime_monitor.logging") as mock_logging:
            monitor = ServiceMonitor(config_file)

            # Should fall back to default timezone
            assert monitor.timezone == "Europe/Berlin"
            mock_logging.warning.assert_called_once()

        os.unlink(config_file)

    def test_load_config_file_not_found(self):
        """Test error handling when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            ServiceMonitor("nonexistent_config.yaml")

    def test_email_setup(self, config_file, mock_config):
        """Test email configuration setup."""
        monitor = ServiceMonitor(config_file)

        assert monitor.smtp_server == mock_config["email"]["smtp_server"]
        assert monitor.smtp_port == mock_config["email"]["smtp_port"]
        assert monitor.smtp_user == mock_config["email"]["username"]
        assert monitor.smtp_password == mock_config["email"]["password"]
        assert monitor.notification_email == mock_config["email"]["notification_email"]

        os.unlink(config_file)

    def test_format_duration(self, config_file):
        """Test duration formatting."""
        monitor = ServiceMonitor(config_file)

        # Test various durations
        assert monitor._format_duration(30) == "30 seconds"
        assert monitor._format_duration(90) == "1 minutes, 30 seconds"
        assert monitor._format_duration(3661) == "1 hours, 1 minutes, 1 seconds"
        assert (
            monitor._format_duration(90061) == "1 days, 1 hours, 1 minutes, 1 seconds"
        )
        assert monitor._format_duration(0) == "0 seconds"

        os.unlink(config_file)


class TestServiceChecks:
    """Test individual service check methods."""

    @pytest.mark.asyncio
    async def test_check_http_success(self, config_file):
        """Test successful HTTP check."""
        monitor = ServiceMonitor(config_file)
        service = {"url": "https://example.com", "timeout": 5}

        # Create mock response context manager
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # Create mock session context manager
        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor._check_http(service)
            assert result is True

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_check_http_failure(self, config_file):
        """Test failed HTTP check."""
        monitor = ServiceMonitor(config_file)
        service = {"url": "https://example.com", "timeout": 5}

        # Create mock response context manager with 404 status
        mock_response = Mock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # Create mock session context manager
        mock_session = Mock()
        mock_session.get = Mock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await monitor._check_http(service)
            assert result is False

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_check_http_exception(self, config_file):
        """Test HTTP check with exception."""
        monitor = ServiceMonitor(config_file)
        service = {"url": "https://example.com", "timeout": 5}

        with patch("aiohttp.ClientSession", side_effect=Exception("Connection error")):
            result = await monitor._check_http(service)
            assert result is False

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_check_port_success(self, config_file):
        """Test successful port check."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "port": 80, "timeout": 5}

        with patch.object(monitor, "_check_port_sync", return_value=True):
            result = await monitor._check_port(service)
            assert result is True

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_check_port_failure(self, config_file):
        """Test failed port check."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "port": 80, "timeout": 5}

        with patch.object(monitor, "_check_port_sync", return_value=False):
            result = await monitor._check_port(service)
            assert result is False

        os.unlink(config_file)

    def test_check_port_sync_success(self, config_file):
        """Test synchronous port check success."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "port": 80, "timeout": 5}

        with patch("socket.socket") as mock_socket:
            mock_sock = Mock()
            mock_sock.connect_ex.return_value = 0
            mock_socket.return_value = mock_sock

            result = monitor._check_port_sync(service)
            assert result is True
            mock_sock.close.assert_called_once()

        os.unlink(config_file)

    def test_check_port_sync_failure(self, config_file):
        """Test synchronous port check failure."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "port": 80, "timeout": 5}

        with patch("socket.socket") as mock_socket:
            mock_sock = Mock()
            mock_sock.connect_ex.return_value = 1
            mock_socket.return_value = mock_sock

            result = monitor._check_port_sync(service)
            assert result is False
            mock_sock.close.assert_called_once()

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_check_ping_success(self, config_file):
        """Test successful ping check."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "timeout": 5}

        with patch.object(monitor, "_check_ping_sync", return_value=True):
            result = await monitor._check_ping(service)
            assert result is True

        os.unlink(config_file)

    def test_check_ping_sync_success(self, config_file):
        """Test synchronous ping check success."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "timeout": 5}

        with patch("ping3.ping", return_value=0.1):
            result = monitor._check_ping_sync(service)
            assert result is True

        os.unlink(config_file)

    def test_check_ping_sync_failure(self, config_file):
        """Test synchronous ping check failure."""
        monitor = ServiceMonitor(config_file)
        service = {"host": "example.com", "timeout": 5}

        with patch("ping3.ping", return_value=None):
            result = monitor._check_ping_sync(service)
            assert result is False

        os.unlink(config_file)


class TestEmailNotifications:
    """Test email notification functionality."""

    @pytest.mark.asyncio
    async def test_send_email_notification_down(self, config_file):
        """Test sending email notification for service down."""
        monitor = ServiceMonitor(config_file)

        with patch.object(monitor, "_send_email_sync") as mock_send:
            await monitor._send_email_notification(
                "test-service", "DOWN", "Connection timeout"
            )

            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            msg = args[0]
            assert "test-service" in msg.get_content()
            assert "DOWN" in msg.get_content()
            assert "Connection timeout" in msg.get_content()

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_send_email_notification_up_with_downtime(self, config_file):
        """Test sending email notification for service up with downtime tracking."""
        monitor = ServiceMonitor(config_file)
        monitor.down_since["test-service"] = datetime.now() - timedelta(hours=1)

        with patch.object(monitor, "_send_email_sync") as mock_send:
            await monitor._send_email_notification("test-service", "UP")

            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            msg = args[0]
            assert "test-service" in msg.get_content()
            assert "UP" in msg.get_content()
            assert "Total downtime" in msg.get_content()
            assert "test-service" not in monitor.down_since

        os.unlink(config_file)

    @pytest.mark.asyncio
    async def test_send_email_notification_incomplete_config(self, config_file):
        """Test email notification with incomplete configuration."""
        monitor = ServiceMonitor(config_file)
        monitor.smtp_server = None

        with patch("uptime_monitor.logging") as mock_logging:
            await monitor._send_email_notification("test-service", "DOWN")
            mock_logging.warning.assert_called_once()

        os.unlink(config_file)

    def test_send_email_sync(self, config_file):
        """Test synchronous email sending."""
        monitor = ServiceMonitor(config_file)

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = Mock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            msg = Mock()
            monitor._send_email_sync(msg)

            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once()
            mock_server.send_message.assert_called_once_with(msg)

        os.unlink(config_file)
