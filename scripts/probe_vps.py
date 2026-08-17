#!/usr/bin/env python3
"""probe_vps.py — 探测 search MCP 与 intel_hub 可用性"""
import json, sys, urllib.request

def post(url, payload, timeout=10):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

print("=== health ===")
try:
    print(urllib.request.urlopen("http://100.86.60.101:8091/health", timeout=6).read().decode()[:500])
except Exception as e:
    print("health ERR:", e)

print("=== tools/list ===")
try:
    body = post("http://100.86.60.101:8091/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    print(body[:1200])
except Exception as e:
    print("tools ERR:", e)

print("=== intel_hub ===")
import os
hub = os.path.expanduser("~/.hermes/local/intel_hub")
print("exists:", os.path.isdir(hub))
if os.path.isdir(hub):
    print(os.listdir(hub)[:20])
    cf = os.path.join(hub, "common.py")
    if os.path.exists(cf):
        funcs = [l.strip() for l in open(cf, encoding="utf-8").read().splitlines()
                 if l.startswith("def ") or l.startswith("class ")]
        print("funcs:", funcs[:30])
