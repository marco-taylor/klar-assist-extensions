#!/bin/bash
# Execute a separate Python process; no installation/files/services in HA.
set -euo pipefail
cd "$(dirname "$0")/.."
tar -czf - custom_components tests hacs.json |
  docker exec -i -e PYTHONDONTWRITEBYTECODE=1 homeassistant python -c "$(cat tools/isolated_runner.py)"
