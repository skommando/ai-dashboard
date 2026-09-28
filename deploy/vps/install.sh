#!/usr/bin/env bash
set -euo pipefail

# Run on the VPS as root, passing an already uploaded private frps.toml.
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
site=/www/server/panel/vhost/nginx/dashboard.example.com.conf
include_file=/www/server/panel/vhost/nginx/view-dashboard.locations.inc
offline_file=/www/wwwroot/dashboard.example.com/dashboard-offline.html
frps_config=/etc/ai-dashboard/frps.toml
frps_binary=/usr/local/lib/ai-dashboard/frps
unit_file=/etc/systemd/system/ai-dashboard-frps.service
nginx=/www/server/nginx/sbin/nginx
source_frps=/root/frp/frps
service=ai-dashboard-frps.service

die() { printf '错误：%s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die '必须以 root 运行。'
[[ $# -eq 1 ]] || die '用法：bash install.sh /root/私有目录/frps.toml'
private_config=$1
[[ -f $private_config && ! -L $private_config ]] || die '私有 frps.toml 不存在或是符号链接。'
[[ -f $site && ! -L $site && -x $nginx && -x $source_frps ]] || die '站点、Nginx 或 frps 前提不满足。'
for file in "$source_dir/ai-dashboard-frps.service" "$source_dir/view-dashboard.locations.conf" "$source_dir/offline.html" "$source_dir/check-listeners.py"; do
    [[ -f $file ]] || die "缺少部署文件：$file"
done
for file in "$include_file" "$offline_file" "$frps_config" "$frps_binary" "$unit_file"; do
    [[ ! -L $file && ! -d $file ]] || die "目标是符号链接或目录，拒绝覆盖：$file"
done
[[ ! -L /etc/ai-dashboard && ! -L /usr/local/lib/ai-dashboard ]] || die '项目目录是符号链接，拒绝安装。'
mode=$(stat -c %a -- "$private_config")
(( (8#$mode & 077) == 0 )) || die '私有配置必须仅所有者可读写（例如 chmod 600）。'

# Verify the six expected settings, with a random token as the only variable.
# frps itself verifies TOML syntax below. Python 3.9 is sufficient here.
python3 - "$private_config" <<'PY' || die '私有 frps.toml 不符合项目模板或 token 格式。'
from pathlib import Path
import re
import sys

lines = [line.strip() for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines()
         if line.strip() and not line.lstrip().startswith('#')]
patterns = {
    'bindAddr': r'bindAddr\s*=\s*"0\.0\.0\.0"',
    'bindPort': r'bindPort\s*=\s*8072',
    'proxyBindAddr': r'proxyBindAddr\s*=\s*"127\.0\.0\.1"',
    'allowPorts': r'allowPorts\s*=\s*\[\s*\{\s*single\s*=\s*8083\s*\}\s*\]',
    'auth.method': r'auth\.method\s*=\s*"token"',
    'auth.token': r'auth\.token\s*=\s*"[A-Za-z0-9_-]{32,}"',
}
if len(lines) != len(patterns) or not all(
    sum(bool(re.fullmatch(pattern, line)) for line in lines) == 1
    for pattern in patterns.values()
):
    raise SystemExit(1)
if any('REPLACE_WITH_RANDOM_TOKEN' in line for line in lines):
    raise SystemExit(1)
PY
"$source_frps" verify -c "$private_config" >/dev/null 2>&1 || die 'frps 配置验证失败。'
"$nginx" -t >/dev/null 2>&1 || die '现有 Nginx 配置未通过预检。'

# This lock prevents two installers from interleaving snapshots.
exec 9>/run/lock/ai-dashboard-vps-install.lock
flock -n 9 || die '另一个 ai-dashboard VPS 安装正在运行。'
backup_dir="/root/ai-dashboard-backups/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -m 700 "$backup_dir"
targets=("$site" "$include_file" "$offline_file" "$frps_config" "$frps_binary" "$unit_file")
for i in "${!targets[@]}"; do
    if [[ -e ${targets[$i]} ]]; then cp -a -- "${targets[$i]}" "$backup_dir/$i"; fi
done
was_enabled=0
was_active=0
systemctl is-enabled --quiet "$service" && was_enabled=1 || true
systemctl is-active --quiet "$service" && was_active=1 || true
created_user=0
created_config_dir=0
created_binary_dir=0
[[ -d /etc/ai-dashboard ]] || created_config_dir=1
[[ -d /usr/local/lib/ai-dashboard ]] || created_binary_dir=1
attempted_enable=0
committed=0

rollback() {
    local failure=$? rollback_failed=0 i
    trap - EXIT INT TERM
    if (( committed )); then return 0; fi
    set +e
    printf '安装失败（状态 %s），恢复项目文件和服务；备份：%s\n' "$failure" "$backup_dir" >&2
    if (( attempted_enable || was_active )); then
        systemctl stop "$service" >/dev/null 2>&1 || rollback_failed=1
    else
        systemctl stop "$service" >/dev/null 2>&1 || true
    fi
    if (( !was_enabled && attempted_enable )); then
        systemctl disable "$service" >/dev/null || rollback_failed=1
    fi
    for i in "${!targets[@]}"; do
        if [[ -e $backup_dir/$i ]]; then
            cp -a -- "$backup_dir/$i" "${targets[$i]}" || rollback_failed=1
        else
            rm -f -- "${targets[$i]}" || rollback_failed=1
        fi
    done
    systemctl daemon-reload || rollback_failed=1
    if (( was_enabled )); then
        systemctl enable "$service" >/dev/null || rollback_failed=1
    fi
    if (( was_active )); then
        systemctl start "$service" || rollback_failed=1
        systemctl is-active --quiet "$service" || rollback_failed=1
    else
        systemctl stop "$service" >/dev/null 2>&1 || true
    fi
    "$nginx" -t && "$nginx" -s reload || rollback_failed=1
    if (( created_config_dir )); then rmdir /etc/ai-dashboard 2>/dev/null || rollback_failed=1; fi
    if (( created_binary_dir )); then rmdir /usr/local/lib/ai-dashboard 2>/dev/null || rollback_failed=1; fi
    if (( created_user )); then userdel ai-dashboard || rollback_failed=1; fi
    if (( rollback_failed )); then
        printf '回滚未完全成功；请依据备份和上述错误人工恢复。\n' >&2
    fi
    (( failure != 0 )) || failure=1
    exit "$failure"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! id -u ai-dashboard >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin ai-dashboard
    created_user=1
fi
if (( created_config_dir )); then install -d -m 750 -o root -g ai-dashboard /etc/ai-dashboard; fi
if (( created_binary_dir )); then install -d -m 755 -o root -g root /usr/local/lib/ai-dashboard; fi

# Keep the old project service stopped while replacing its executable/config.
if (( was_active )); then
    systemctl stop "$service"
else
    systemctl stop "$service" >/dev/null 2>&1 || true
fi
install -m 755 -o root -g root "$source_frps" "$frps_binary"
install -m 640 -o root -g ai-dashboard "$private_config" "$frps_config"
install -m 644 -o root -g root "$source_dir/ai-dashboard-frps.service" "$unit_file"
install -m 644 -o root -g root "$source_dir/offline.html" "$offline_file"
install -m 644 -o root -g root "$source_dir/view-dashboard.locations.conf" "$include_file"

runuser -u ai-dashboard -- "$frps_binary" verify -c "$frps_config" >/dev/null 2>&1 || die '服务用户无法读取或验证 frps 配置。'
systemctl daemon-reload
attempted_enable=1
systemctl enable --now "$service"
sleep 1
systemctl is-active --quiet "$service" || die 'ai-dashboard-frps 未保持运行。'
ss -H -ltn '( sport = :8072 )' | python3 "$source_dir/check-listeners.py" control || die '控制端口 8072 未以预期地址监听。'
ss -H -ltn '( sport = :8083 )' | python3 "$source_dir/check-listeners.py" proxy || die '代理端口 8083 存在非回环监听。'

# The dedicated frps is running safely before switching the site to it.
# No frpc connection is required at install time.
python3 - "$site" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
include = '    include /www/server/panel/vhost/nginx/view-dashboard.locations.inc;'
if include not in text:
    marker = '    #REWRITE-END'
    if marker not in text:
        raise SystemExit('找不到站点插入标记，拒绝修改。')
    text = text.replace(marker, marker + '\n\n' + include, 1)
    path.write_text(text, encoding='utf-8')
PY
"$nginx" -t
"$nginx" -s reload
committed=1
trap - EXIT INT TERM
printf 'VPS 配置安装成功；备份：%s\n' "$backup_dir"
