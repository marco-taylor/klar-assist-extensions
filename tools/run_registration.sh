#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
tar -czf - custom_components tests hacs.json |
  docker exec -i -e PYTHONDONTWRITEBYTECODE=1 homeassistant python -c "$(cat tools/registration_runner.py)"
