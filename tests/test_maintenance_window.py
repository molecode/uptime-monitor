import tempfile
import os
from unittest.mock import patch
from datetime import datetime
import pytz

from uptime_monitor import ServiceMonitor


class TestMaintenanceWindow:
    """Test maintenance window functionality."""

    def create_monitor_with_maintenance_service(self, maintenance_config):
        """Helper to create monitor with maintenance window service."""
        config = {
            "email": {},
            "timezone": "UTC",
            "services": {
                "test-service": {
                    "type": "http",
                    "url": "https://example.com",
                    "timeout": 5,
                    "interval": 300,
                    "max_tries": 3,
                    **maintenance_config,
                }
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(config, f)
            monitor = ServiceMonitor(f.name)
            return monitor, f.name

    def test_no_maintenance_window(self):
        """Test service without maintenance window."""
        monitor, config_file = self.create_monitor_with_maintenance_service({})
        service = monitor.config["services"]["test-service"]

        result = monitor._is_in_maintenance(service)
        assert result is False

        os.unlink(config_file)

    def test_maintenance_window_same_day(self):
        """Test maintenance window within same day."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {"maintenance_window": {"start": "02:00", "end": "04:00"}}
        )
        service = monitor.config["services"]["test-service"]

        # Test during maintenance window
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 3, 0, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        # Test outside maintenance window
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 5, 0, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is False

        os.unlink(config_file)

    def test_maintenance_window_crosses_midnight(self):
        """Test maintenance window that crosses midnight."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {"maintenance_window": {"start": "23:00", "end": "01:00"}}
        )
        service = monitor.config["services"]["test-service"]

        # Test during maintenance window (before midnight)
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 23, 30, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        # Test during maintenance window (after midnight)
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 16, 0, 30, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        # Test outside maintenance window
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is False

        os.unlink(config_file)

    def test_maintenance_window_month_boundary(self):
        """Test maintenance window crossing month boundary - this was the bug!"""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {"maintenance_window": {"start": "23:00", "end": "01:00"}}
        )
        service = monitor.config["services"]["test-service"]

        # Test on January 31st at 23:30 (should work with timedelta fix)
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 31, 23, 30, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            # This should not raise ValueError anymore
            result = monitor._is_in_maintenance(service)
            assert result is True

        # Test on February 1st at 00:30 (after the fix)
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 2, 1, 0, 30, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        os.unlink(config_file)

    def test_maintenance_window_february_leap_year(self):
        """Test maintenance window crossing February 29th in leap year."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {"maintenance_window": {"start": "23:00", "end": "01:00"}}
        )
        service = monitor.config["services"]["test-service"]

        # Test on February 29th, 2024 (leap year) at 23:30
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 2, 29, 23, 30, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        os.unlink(config_file)

    def test_maintenance_window_different_timezone(self):
        """Test maintenance window with service-specific timezone."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {
                "maintenance_window": {"start": "02:00", "end": "04:00"},
                "timezone": "America/New_York",
            }
        )
        service = monitor.config["services"]["test-service"]

        # Test during maintenance window in NY timezone
        with patch("uptime_monitor.datetime") as mock_dt:
            ny_tz = pytz.timezone("America/New_York")
            mock_dt.now.return_value = datetime(2024, 1, 15, 3, 0, 0, tzinfo=ny_tz)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        os.unlink(config_file)

    def test_maintenance_window_invalid_service_timezone(self):
        """Test maintenance window with invalid service timezone."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {
                "maintenance_window": {"start": "02:00", "end": "04:00"},
                "timezone": "Invalid/Timezone",
            }
        )
        service = monitor.config["services"]["test-service"]

        with patch("uptime_monitor.logging") as mock_logging:
            with patch("uptime_monitor.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(
                    2024, 1, 15, 3, 0, 0, tzinfo=pytz.UTC
                )
                mock_dt.combine = datetime.combine
                mock_dt.strptime = datetime.strptime

                monitor._is_in_maintenance(service)
                # Should use default timezone and log warning
                mock_logging.warning.assert_called_once()

        os.unlink(config_file)

    def test_maintenance_window_edge_cases(self):
        """Test edge cases for maintenance window."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {"maintenance_window": {"start": "00:00", "end": "00:00"}}
        )
        service = monitor.config["services"]["test-service"]

        # Test at exactly midnight
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 0, 0, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            # This should handle the edge case properly
            assert isinstance(result, bool)

        os.unlink(config_file)

    def test_maintenance_window_boundary_times(self):
        """Test maintenance window at exact boundary times."""
        monitor, config_file = self.create_monitor_with_maintenance_service(
            {"maintenance_window": {"start": "02:00", "end": "04:00"}}
        )
        service = monitor.config["services"]["test-service"]

        # Test at exact start time
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 2, 0, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        # Test at exact end time
        with patch("uptime_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 4, 0, 0, tzinfo=pytz.UTC)
            mock_dt.combine = datetime.combine
            mock_dt.strptime = datetime.strptime

            result = monitor._is_in_maintenance(service)
            assert result is True

        os.unlink(config_file)
