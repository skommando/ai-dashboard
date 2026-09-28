#!/usr/bin/env python3
"""Validate headerless `ss -H -ltn` output for the two project ports."""

import sys


CONTROL_ADDRESSES = {"*:8072", "0.0.0.0:8072", "[::]:8072", ":::8072"}
PROXY_ADDRESSES = {"127.0.0.1:8083"}


def valid(kind, output):
    addresses = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "LISTEN":
            return False
        addresses.append(fields[3])
    if kind == "control":
        return bool(addresses) and all(address in CONTROL_ADDRESSES for address in addresses)
    if kind == "proxy":
        return all(address in PROXY_ADDRESSES for address in addresses)
    return False


if __name__ == "__main__":
    if len(sys.argv) != 2 or not valid(sys.argv[1], sys.stdin.read()):
        raise SystemExit(1)
