#!/usr/bin/env python3
"""
VLM Server Skill - Run the Hokusai VLM dashboard with camera demo.
This is a thin wrapper around the viewer skill's server.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VIEWER_SERVER = REPO_ROOT / "agents" / "skills" / "viewer" / "server.py"


def main():
    parser = argparse.ArgumentParser(description="Hokusai VLM Dashboard Server")
    parser.add_argument("--port", type=int, default=3002, help="Port to run on (default: 3002)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--check", action="store_true", help="Check VLM endpoint health and exit")
    args = parser.parse_args()

    # Set environment variables for the server
    os.environ.setdefault("VLM_BASE_URL", os.environ.get("VLM_BASE_URL", "http://127.0.0.1:1234/v1"))
    os.environ.setdefault("VLM_MODEL", os.environ.get("VLM_MODEL", "qwen2.5-vl-3b"))
    os.environ.setdefault("VLM_API_KEY", os.environ.get("VLM_API_KEY", ""))
    os.environ["PORT"] = str(args.port)
    os.environ["HOST"] = args.host

    if args.check:
        # Quick health check
        import urllib.request
        import json
        base = os.environ["VLM_BASE_URL"].rstrip("/")
        try:
            req = urllib.request.Request(f"{base}/models", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
            print(f"VLM Server: OK")
            print(f"Base URL: {base}")
            print(f"Configured model: {os.environ['VLM_MODEL']}")
            print(f"Available models: {models}")
            return 0
        except Exception as e:
            print(f"VLM Server: FAILED")
            print(f"Error: {e}")
            return 1

    # Import and run the viewer server
    sys.path.insert(0, str(VIEWER_SERVER.parent))
    sys.argv = [
        "server.py",
        "--port", str(args.port),
        "--host", args.host,
    ]
    import uvicorn
    from server import app

    print(f"Starting Hokusai VLM Dashboard on http://{args.host}:{args.port}")
    print(f"  Dashboard: http://{args.host}:{args.port}/")
    print(f"  VLM Demo:  http://{args.host}:{args.port}/vlm")
    print(f"  VLM Model: {os.environ['VLM_MODEL']}")
    print(f"  VLM Base:  {os.environ['VLM_BASE_URL']}")

    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    sys.exit(main())