#!/usr/bin/env bash
# URDF HTTP 서버 — Lichtblick 3D 패널이 spot_isaac.urdf 를 fetch 할 수 있도록
# CORS 헤더 포함 (Lichtblick origin=http://192.168.10.105:8080 → cross-origin fetch)
# 기본 포트: 8780 (8766 은 isaac-sim-mcp 확장이 점유 — layout.json 과 일치시킬 것)
set -e
cd "$(dirname "$0")"
PORT="${URDF_SERVER_PORT:-8780}"
echo "[urdf-server] serving $(pwd) on :${PORT}"
exec python3 - <<'EOF'
import os, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("URDF_SERVER_PORT", "8780"))

class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, fmt, *args):
        pass  # quiet

os.chdir(os.path.dirname(os.path.abspath(__file__)))
HTTPServer(("0.0.0.0", PORT), CORSHandler).serve_forever()
EOF
