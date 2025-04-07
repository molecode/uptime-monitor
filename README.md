# Uptime Monitor

Uptime Monitor is a Python-based service monitoring tool that checks the status of various services and provides a web dashboard to display their statuses. It also sends email notifications when a service goes down or comes back up.

## Features

- Monitor HTTP, port, and ping services
- Configurable maintenance windows
- Email notifications for service status changes
- Web dashboard with auto-refresh to display service statuses
- Healthcheck pings to an external endpoint
- Password-protected dashboard
- Beautiful terminal output with rich formatting

## Requirements

- Python 3.12 or higher
- Required packages: aiohttp, ping3, pytz, pyyaml, flask, flask-login, rich

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/uptime-monitor.git
    cd uptime-monitor
    ```

2. Install the dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Configuration

Edit the config.yaml file to configure the services you want to monitor and email settings.

Example config.yaml:
```yaml
email:
  smtp_server: mail.example.com
  smtp_port: 587
  username: your-email@example.com
  password: your-email-password
  notification_email: notify@example.com

healthcheck:
  url: https://hc-ping.com/your-healthcheck-url
  interval: 3600  # in seconds (1 hour)

dashboard:
  password: your-dashboard-password  # Password for the web dashboard (defaults to "admin")

defaults: &default_service
  timeout: 5
  interval: 300 # in seconds (5 minutes)
  max_tries: 3

services:
  example-http-service:
    <<: *default_service
    type: http
    url: https://example.com

  example-ssh-service:
    <<: *default_service
    type: port
    host: example.com
    port: 22

  example-ping-service:
    <<: *default_service
    type: ping
    host: example.com
    maintenance_window:
      start: "23:00"
      end: "01:00"
```

## Usage

### Command Line

To start the uptime monitor from the command line, run:
```sh
python -m uptime_monitor
```

### Web Dashboard

To start the web dashboard, run:
```sh
python -m uptime_monitor.dashboard
```

The dashboard will be available at http://0.0.0.0:8080.

To log in, use the password configured in the `dashboard.password` setting in your config.yaml (defaults to "admin").

## License

This project is licensed under the MIT License.

