# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based uptime monitoring service that checks the health of HTTP endpoints, TCP ports, and ping targets. It includes a web dashboard for viewing service status and sends email notifications when services go down or come back up.

## Key Components

- **ServiceMonitor** (`src/uptime_monitor/__init__.py`): Core monitoring engine with async service checking
- **WebServiceMonitor** (`src/uptime_monitor/dashboard.py`): Flask-based web dashboard that extends ServiceMonitor
- **Configuration**: YAML-based configuration with service definitions, email settings, and maintenance windows

## Common Development Commands

### Running the application
```bash
# Run the command-line monitor
python -m uptime_monitor

# Or using the entry point
uptime-monitor

# Run the web dashboard
python -m uptime_monitor.dashboard

# Or using the entry point  
uptime-dashboard
```

### Development workflow
```bash
# Install dependencies (uses uv package manager)
uv sync

# Run linting
uv run ruff check

# Run formatting
uv run ruff format

# Build Docker image
docker build -t uptime-monitor .
```

## Architecture Notes

### Service Monitoring
- Async architecture using asyncio for concurrent service checks
- Three check types: HTTP (status 200), TCP port connectivity, and ping
- Configurable retry logic with max_tries per service
- State tracking to prevent duplicate notifications
- Timezone-aware maintenance windows that can span midnight

### Web Dashboard
- Flask application with login authentication
- Runs monitoring in separate thread with dedicated event loop
- Real-time service status display with auto-refresh
- Theme switching (dark/light mode) with cookie persistence
- Password protection using dashboard.password config

### Email Notifications
- SMTP-based notifications for service state changes
- Includes downtime duration in recovery notifications
- Async email sending to prevent blocking the monitoring loop

## Configuration Structure

Services are defined in `config.yaml` with:
- `defaults` section for common settings (timeout, interval, max_tries)
- `services` section with individual service definitions
- Service types: `http`, `port`, `ping`
- Optional maintenance windows and per-service timezones
- Email and healthcheck.io integration

## Key Files

- `config.yaml`: Main configuration file (copy from `config_example.yaml`)
- `src/uptime_monitor/__init__.py`: Core monitoring logic
- `src/uptime_monitor/dashboard.py`: Web interface
- `src/uptime_monitor/templates/`: HTML templates for dashboard
- `pyproject.toml`: Dependencies and project metadata