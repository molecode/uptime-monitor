import asyncio
import os
import secrets
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    login_required,
    login_user,
    logout_user,
)

from uptime_monitor import ServiceMonitor


class User(UserMixin):
    def __init__(self, id, password):
        self.id = id
        self.password = password
        self.theme = "dark"  # Default theme is dark


class WebServiceMonitor(ServiceMonitor):
    def __init__(self, config_path: str, host: str = "0.0.0.0", port: int = 8080):
        super().__init__(config_path)
        self.host = host
        self.port = port
        self.app = Flask(__name__)

        # Configure Flask and login
        self.app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
        self.login_manager = LoginManager()
        self.login_manager.init_app(self.app)
        self.login_manager.login_view = "login"

        # Set up user with just a password
        # Note: In a production environment, you should use a proper user management system
        # with secure password storage
        admin_password = self.config.get("dashboard", {}).get("password", "admin")
        self.user = User(1, admin_password)

        self.setup_routes()

        # Initialize asyncio task for monitoring
        self.monitoring_task: Optional[asyncio.Task] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def dashboard_config(self):
        return self.config.get("dashboard", {})

    def setup_routes(self):
        @self.login_manager.user_loader
        def load_user(user_id):
            if int(user_id) == self.user.id:
                return self.user
            return None

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            # Get theme preference from cookie, default to dark
            theme = request.cookies.get("theme", "dark")

            if request.method == "POST":
                password = request.form.get("password")

                if password == self.user.password:
                    login_user(self.user)
                    next_page = request.args.get("next", "")
                    if not next_page or url_for("login") in next_page:
                        next_page = url_for("home")
                    return redirect(next_page)
                else:
                    return render_template(
                        "login.html", error="Invalid password", theme=theme
                    )

            return render_template("login.html", theme=theme)

        @self.app.route("/logout")
        @login_required
        def logout():
            logout_user()
            return redirect(url_for("login"))

        @self.app.route("/toggle-theme")
        def toggle_theme():
            # Toggle between light and dark mode
            current_theme = request.cookies.get("theme", "dark")
            new_theme = "dark" if current_theme == "light" else "light"

            # Get the previous page or default to home
            next_page = request.referrer or url_for("home")

            # Create response with redirect
            response = redirect(next_page)

            # Set cookie with the new theme
            response.set_cookie(
                "theme", new_theme, max_age=60 * 60 * 24 * 365
            )  # 1 year

            return response

        @self.app.route("/")
        @login_required
        def home():
            # Get theme preference from cookie, default to dark
            theme = request.cookies.get("theme", "dark")

            return render_template(
                "index.html",
                services=self._get_services_status(),
                theme=theme,
            )

    def _get_services_status(self):
        services_status = {}
        current_time = datetime.now(self.tz)

        for name, service in self.config["services"].items():
            # Check if service is in maintenance window
            is_in_maintenance = self._is_in_maintenance(service)
            
            # Get the state of the service
            state = self.service_states.get(name, None)

            # Convert state to string
            if is_in_maintenance:
                state = "MAINTENANCE"
            elif state is True:
                state = "UP"
            elif state is False:
                state = "DOWN"
            else:
                state = "UNKNOWN"

            # Additional information for display
            display_info = {
                "status": state,
                "type": service["type"],
                "last_check": current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            }

            # Add specific service details
            if "host" in service:
                display_info["host"] = service["host"]
            if "url" in service:
                display_info["url"] = service["url"]
            if "port" in service:
                display_info["port"] = service["port"]

            # Add downtime information if the service is down
            if state == "DOWN" and name in self.down_since:
                display_info["down_since"] = self.down_since[name].strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            services_status[name] = display_info

        return services_status

    def _run_async_monitoring(self):
        """Run the async monitoring in a separate thread with its own event loop."""
        # Create a new event loop for this thread
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.loop = asyncio.get_event_loop()

        # Create and run the monitoring task
        self.monitoring_task = self.loop.create_task(self.start_monitoring())

        # Run the event loop until complete
        self.loop.run_until_complete(self.monitoring_task)

    def start(self):
        # Start the monitoring in a separate thread with its own event loop
        monitoring_thread = threading.Thread(target=self._run_async_monitoring)
        monitoring_thread.daemon = True
        monitoring_thread.start()

        # Start the web server
        self.app.run(host=self.host, port=self.port, debug=False)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Web Service Monitor")
    parser.add_argument(
        "--config", "-c", default="config.yaml", help="Path to the configuration file"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port to bind to")

    args = parser.parse_args()

    monitor = WebServiceMonitor(args.config, args.host, args.port)
    monitor.start()


if __name__ == "__main__":
    main()
