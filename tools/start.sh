#!/usr/bin/env bash
set -euo pipefail
systemctl start ai-dashboard.service
systemctl is-active --quiet ai-dashboard.service
printf 'ai-dashboard.service is active\n'
