import asyncio
import logging
import smtplib
import socket
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Dict

import aiohttp
import ping3
import pytz
import yaml
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# Initialize rich console with custom theme
custom_theme = Theme(
    {
        "info": "green",
        "warning": "yellow",
        "error": "red",
        "maintenance": "yellow",
        "up": "green",
        "down": "red",
    }
)
console = Console(theme=custom_theme)

# Default timezone
DEFAULT_TIMEZONE = "Europe/Berlin"


class ServiceMonitor:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.service_states = {}  # Tracks current state of services
        self.down_since = {}  # Tracks when services went down
        self._setup_logging()
        self._setup_email()
        self.healthcheck_config = self.config.get("healthcheck", {})
        # Get timezone from config or use default
        self.timezone = self.config.get("timezone", DEFAULT_TIMEZONE)
        try:
            self.tz = pytz.timezone(self.timezone)
            logging.info(f"Using timezone: {self.timezone}")
        except pytz.exceptions.UnknownTimeZoneError:
            logging.warning(
                f"Unknown timezone: {self.timezone}, falling back to {DEFAULT_TIMEZONE}"
            )
            self.timezone = DEFAULT_TIMEZONE
            self.tz = pytz.timezone(DEFAULT_TIMEZONE)

    def _load_config(self, config_path: str) -> dict:
        with open(config_path, "r") as file:
            return yaml.safe_load(file)

    def _setup_logging(self):
        # Configure rich handler for console output
        rich_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_path=False,
            enable_link_path=False,
            log_time_format="[%m/%d/%y %H:%M:%S]",
            omit_repeated_times=False,
        )

        # Configure file handler for log file
        file_handler = logging.FileHandler("service_monitor.log")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )

        # Set up the root logger
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            handlers=[rich_handler, file_handler],
            force=True,
        )

    def _setup_email(self):
        self.email_config = self.config.get("email", {})
        self.smtp_server = self.email_config.get("smtp_server")
        self.smtp_port = self.email_config.get("smtp_port")
        self.smtp_user = self.email_config.get("username")
        self.smtp_password = self.email_config.get("password")
        self.notification_email = self.email_config.get("notification_email")

    async def _send_email_notification(
        self, service_name: str, status: str, reason: str = None
    ):
        if not all(
            [
                self.smtp_server,
                self.smtp_port,
                self.smtp_user,
                self.smtp_password,
                self.notification_email,
            ]
        ):
            logging.warning("Email configuration incomplete. Skipping notification.")
            return

        # Use timezone-aware datetime for timestamp
        timestamp = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S %Z")

        # Build email content
        content = [
            f"Service: {service_name}",
            f"Status: {status}",
            f"Timestamp: {timestamp}",
        ]

        # Add downtime duration for UP notifications
        if status == "UP" and service_name in self.down_since:
            down_start = self.down_since[service_name]
            downtime = self._format_duration(
                (datetime.now() - down_start).total_seconds()
            )
            content.append(f"Total downtime: {downtime}")
            del self.down_since[service_name]  # Clear the downtime tracker

        if reason:
            content.append(f"Reason: {reason}")

        msg = EmailMessage()
        msg.set_content("\n".join(content))

        # Add emoji to subject based on status
        status_emoji = "🔴" if status == "DOWN" else "✅"
        msg["Subject"] = (
            f"{status_emoji} Service Monitor Alert - {service_name} is {status}"
        )
        msg["From"] = self.smtp_user
        msg["To"] = self.notification_email

        # Run SMTP operations in a thread to not block the event loop
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._send_email_sync, msg)
            logging.info(
                f"Email notification sent for service {service_name} - Status: {status}"
            )
        except Exception as e:
            logging.error(f"Failed to send email notification: {e}")

    def _send_email_sync(self, msg):
        """Synchronous method to send email, to be run in an executor."""
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

    def _format_duration(self, seconds):
        """Convert seconds into human readable duration."""
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        parts = []
        if days > 0:
            parts.append(f"{days} days")
        if hours > 0:
            parts.append(f"{hours} hours")
        if minutes > 0:
            parts.append(f"{minutes} minutes")
        if seconds > 0 or not parts:  # Include seconds if it's the only non-zero value
            parts.append(f"{seconds} seconds")

        return ", ".join(parts)

    def _is_in_maintenance(self, service: Dict) -> bool:
        if "maintenance_window" not in service:
            return False

        # Get service-specific timezone or use default
        service_tz = service.get("timezone", self.timezone)
        try:
            tz = pytz.timezone(service_tz)
        except pytz.exceptions.UnknownTimeZoneError:
            logging.warning(
                f"Unknown timezone for service: {service_tz}, using {self.timezone}"
            )
            tz = self.tz

        # Use timezone-aware datetime for current time
        now = datetime.now(tz).time()

        # Get hour and minute values for start and end
        start_time = service["maintenance_window"]["start"]
        end_time = service["maintenance_window"]["end"]

        # Create datetime objects for today with the maintenance window times
        today = datetime.now(tz).date()

        # Create timezone-aware datetime objects for start and end times
        start_dt = tz.localize(
            datetime.combine(today, datetime.strptime(start_time, "%H:%M").time())
        )
        end_dt = tz.localize(
            datetime.combine(today, datetime.strptime(end_time, "%H:%M").time())
        )

        # If end time is earlier than start time, it means the window crosses midnight
        # So we need to add one day to the end time
        if end_dt < start_dt:
            end_dt = end_dt + timedelta(days=1)

        # Get the time components for comparison
        start = start_dt.time()
        end = end_dt.time()

        # If the window crosses midnight and we need to compare with naive time objects
        # we need special handling
        if start_dt.date() != end_dt.date():  # Window crosses midnight
            return now >= start or now <= end
        else:  # Window is within the same day
            return start <= now <= end

    async def _check_http(self, service: Dict) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    service["url"], timeout=service["timeout"]
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _check_port(self, service: Dict) -> bool:
        loop = asyncio.get_running_loop()
        try:
            # Run socket operations in executor to prevent blocking the event loop
            return await loop.run_in_executor(None, self._check_port_sync, service)
        except Exception:
            return False

    def _check_port_sync(self, service: Dict) -> bool:
        """Synchronous implementation of port checking to run in executor."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(service["timeout"])
            result = sock.connect_ex((service["host"], service["port"]))
            sock.close()
            return result == 0
        except socket.error:
            return False

    async def _check_ping(self, service: Dict) -> bool:
        loop = asyncio.get_running_loop()
        try:
            # Run ping operation in executor as it's blocking
            return await loop.run_in_executor(None, self._check_ping_sync, service)
        except Exception:
            return False

    def _check_ping_sync(self, service: Dict) -> bool:
        """Synchronous implementation of ping checking to run in executor."""
        try:
            result = ping3.ping(service["host"], timeout=service["timeout"])
            return result is not None
        except Exception:
            return False

    async def _check_service(self, service_name: str, service: Dict):
        check_functions = {
            "http": self._check_http,
            "port": self._check_port,
            "ping": self._check_ping,
        }

        was_in_maintenance = False
        check_func = check_functions[service["type"]]

        while True:
            if self._is_in_maintenance(service):
                if not was_in_maintenance:
                    logging.info(
                        f"Service {service_name} ({service['type']}) entering maintenance window"
                    )
                    was_in_maintenance = True
                logging.info(
                    f"Service {service_name} ({service['type']}) status: [maintenance]MAINTENANCE[/maintenance]"
                )
                await asyncio.sleep(60)  # Check maintenance status every minute
                continue
            elif was_in_maintenance:
                logging.info(
                    f"Service {service_name} ({service['type']}) exiting maintenance window"
                )
                was_in_maintenance = False

            # Count failures over all retry attempts
            failures = 0
            error_reason = None

            # Try service check up to max_tries times
            for attempt in range(service["max_tries"]):
                try:
                    logging.debug(
                        f"Service {service_name} ({service['type']}) - Attempt {attempt + 1}/{service['max_tries']}"
                    )
                    if await check_func(service):
                        logging.debug(
                            f"Service {service_name} ({service['type']}) - Attempt {attempt + 1} successful"
                        )
                        break
                    failures += 1
                    if service["type"] == "http":
                        error_reason = "HTTP status not 200"
                    elif service["type"] == "port":
                        error_reason = f"Could not connect to port {service['port']}"
                    else:  # ping
                        error_reason = "No ping response"
                    logging.debug(
                        f"Service {service_name} ({service['type']}) - Attempt {attempt + 1} failed: {error_reason}"
                    )
                except Exception as e:
                    failures += 1
                    error_reason = str(e)
                    logging.debug(
                        f"Service {service_name} ({service['type']}) - Attempt {attempt + 1} failed with error: {e}"
                    )

                if failures < service["max_tries"]:
                    await asyncio.sleep(1)  # Wait between retries

            # After all retries, update state and send notification if needed
            if failures == service["max_tries"]:  # Service is DOWN
                if (
                    service_name not in self.service_states
                    or self.service_states[service_name]
                ):
                    await self._send_email_notification(
                        service_name, "DOWN", error_reason
                    )
                    self.down_since[service_name] = (
                        datetime.now()
                    )  # Record when service went down
                self.service_states[service_name] = False
                logging.info(
                    f"Service {service_name} ({service['type']}) status: [down]DOWN[/down]"
                )
            else:  # Service is UP
                if (
                    service_name in self.service_states
                    and not self.service_states[service_name]
                ):
                    await self._send_email_notification(
                        service_name, "UP"
                    )  # Downtime will be included if available
                self.service_states[service_name] = True
                logging.info(
                    f"Service {service_name} ({service['type']}) status: [up]UP[/up]"
                )

            await asyncio.sleep(service["interval"])

    async def _ping_healthcheck(self):
        """Ping healthcheck.io endpoint."""
        if not self.healthcheck_config.get("url"):
            return

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.healthcheck_config["url"], timeout=5
                    ) as response:
                        if response.status == 200:
                            logging.info("Healthcheck ping successful")
                        else:
                            logging.warning(
                                f"Healthcheck ping failed with status code: {response.status}"
                            )
            except Exception as e:
                logging.error(f"Failed to ping healthcheck: {e}")

            # Sleep for the configured interval (default 1 hour)
            await asyncio.sleep(self.healthcheck_config.get("interval", 3600))

    async def start_monitoring(self):
        tasks = []
        # Add healthcheck task if configured
        if self.healthcheck_config.get("url"):
            tasks.append(asyncio.create_task(self._ping_healthcheck()))

        # Create tasks for each service
        for service_name, service in self.config["services"].items():
            tasks.append(
                asyncio.create_task(self._check_service(service_name, service))
            )

        # Wait for all tasks to complete (they run indefinitely unless there's an exception)
        # TODO: Without try except to debug the we had before:
        # [03/30/25 22:00:04] ERROR    Error in monitoring: day is out of range for month
        await asyncio.gather(*tasks)
        # try:
        #     await asyncio.gather(*tasks)
        # except asyncio.CancelledError:
        #     logging.info("Monitoring tasks cancelled")
        # except Exception as e:
        #     logging.error(f"Error in monitoring: {e}")


async def main():
    monitor = ServiceMonitor("config.yaml")
    await monitor.start_monitoring()


def run():
    """Entry point for the application."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Monitoring stopped by user")
