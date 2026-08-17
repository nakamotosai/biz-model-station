#!/usr/bin/env python3
"""probe3.py — MCP initialize 握手后 tools/list"""
import json, urllib.request, http.client

HOST = "100.86.60.101"
PORT = 8091
PATH = "/mcp"

def call(payload, session_id=None):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-06-18"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    conn = http.client.HTTPConnection(HOST, PORT, timeout=15)
    conn.request("POST", PATH, body=json.dumps(payload), headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    sid = resp.getheader("Mcp-Session-Id")
    conn.close()
    return resp.status, body, sid

try:
    st, body, sid = call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18",
                                     "capabilities": {},
                                     "clientInfo": {"name": "probe", "version": "0.1"}}})
    print("initialize:", st, body[:500], "session:", sid)
    if sid:
        st2, body2, _ = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
        print("tools/list:", st2, body2[:800])
except Exception as e:
    print("ERR:", e)
