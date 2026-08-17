#!/usr/bin/env python3
"""probe2.py — 带 MCP 协议头探 search MCP"""
import json, urllib.request

def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "MCP-Protocol-Version": "2025-06-18"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.read().decode("utf-8", "replace")

for url in ["http://100.86.60.101:8091/mcp", "http://100.86.60.101:8091/"]:
    print("URL:", url)
    try:
        st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        print("status", st, "body[:700]", body[:700])
    except Exception as e:
        print("ERR:", e)
