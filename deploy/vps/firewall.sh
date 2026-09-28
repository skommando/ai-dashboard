#!/usr/bin/env bash
set -euo pipefail

# This project owns only the 8083 rule. Do not alter global frps bindings.
action="${1:-apply}"
for tool in /usr/sbin/iptables /usr/sbin/ip6tables; do
    rule=(INPUT '!' -i lo -p tcp --dport 8083 -m comment --comment ai-dashboard-view -j REJECT)
    case "$action" in
        apply)
            if ! "$tool" -C "${rule[@]}" 2>/dev/null; then
                "$tool" -I INPUT 1 '!' -i lo -p tcp --dport 8083 -m comment --comment ai-dashboard-view -j REJECT
            fi
            ;;
        remove)
            if "$tool" -C "${rule[@]}" 2>/dev/null; then
                "$tool" -D "${rule[@]}"
            fi
            ;;
        *) echo 'Usage: firewall.sh apply|remove' >&2; exit 2 ;;
    esac
done
