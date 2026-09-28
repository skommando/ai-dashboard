#!/usr/bin/env bash
set -euo pipefail
systemctl stop ai-dashboard.service
if systemctl is-active --quiet ai-dashboard.service; then
    printf 'service is still active\n' >&2
    exit 1
fi
printf 'ai-dashboard.service is stopped\n'
