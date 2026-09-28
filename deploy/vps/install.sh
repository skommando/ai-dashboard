#!/usr/bin/env bash
set -euo pipefail

# Run from this uploaded directory, as the site's administrator.
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
site=/www/server/panel/vhost/nginx/dashboard.example.com.conf
include_file=/www/server/panel/vhost/nginx/view-dashboard.locations.inc
nginx=/www/server/nginx/sbin/nginx
backup_dir="/root/ai-dashboard-backups/$(date -u +%Y%m%dT%H%M%SZ)-$$"
test -f "$site"
test -x "$nginx"
install -d -m 700 "$backup_dir"
cp -p -- "$site" "$backup_dir/site.conf"
if test -f "$include_file"; then cp -p -- "$include_file" "$backup_dir/locations.inc"; fi
if test -f /www/wwwroot/dashboard.example.com/dashboard-offline.html; then
    cp -p -- /www/wwwroot/dashboard.example.com/dashboard-offline.html "$backup_dir/offline.html"
fi

rollback_site() {
    cp -p -- "$backup_dir/site.conf" "$site"
    if test -f "$backup_dir/locations.inc"; then
        cp -p -- "$backup_dir/locations.inc" "$include_file"
    fi
}
trap rollback_site ERR

# Store only project-owned files. Basic Auth and certificates stay in the site.
install -d -m 755 /usr/local/lib/ai-dashboard
install -m 755 "$source_dir/firewall.sh" /usr/local/lib/ai-dashboard/firewall.sh
install -m 644 "$source_dir/ai-dashboard-firewall.service" /etc/systemd/system/ai-dashboard-firewall.service
systemctl daemon-reload
systemctl enable --now ai-dashboard-firewall.service
install -m 644 "$source_dir/offline.html" /www/wwwroot/dashboard.example.com/dashboard-offline.html
install -m 644 "$source_dir/view-dashboard.locations.conf" "$include_file"

python3 - "$site" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
include = '    include /www/server/panel/vhost/nginx/view-dashboard.locations.inc;'
if include not in text:
    marker = '    #REWRITE-END'
    if marker not in text:
        raise SystemExit('Expected site insertion marker is missing; refusing to rewrite the site.')
    text = text.replace(marker, marker + '\n\n' + include, 1)
    path.write_text(text, encoding='utf-8')
PY

"$nginx" -t
"$nginx" -s reload
trap - ERR
printf 'Installed dashboard.example.com proxy; configuration backup: %s\n' "$backup_dir"
