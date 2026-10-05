"""
Interactive Dashboard Local Server.
Serves the daily intelligence report and provides REST API endpoints to:
1. Update application status (e.g. mark as 'applied', 'interviewing', etc.) directly in jobs.db.
2. Query live application statuses and market intelligence data.

Run via:
    python scripts/serve_dashboard.py [--port 8080]
"""

import argparse
import json
import mimetypes
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.application_repository import ApplicationRepository
from reports.daily_report_generator import generate_daily_reports

REPORTS_DIR = PROJECT_ROOT / "reports"



class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url_path = self.path.split("?")[0]

        # 1. API: List Applications
        if url_path == "/api/applications":
            app_repo = ApplicationRepository()
            apps = app_repo.get_all()
            app_repo.close()
            self._send_json({"applications": apps})
            return

        # 2. Serve Latest Daily Report
        if url_path in ("/", "/index.html", "/report"):
            report_file = REPORTS_DIR / "latest_report.html"
            if not report_file.exists():
                generate_daily_reports()

            self._serve_file(report_file, "text/html")
            return

        # 3. Serve Other Files in Reports Directory
        safe_rel_path = url_path.lstrip("/")
        candidate_file = (REPORTS_DIR / safe_rel_path).resolve()
        if candidate_file.is_file() and candidate_file.is_relative_to(REPORTS_DIR):
            mime, _ = mimetypes.guess_type(str(candidate_file))
            self._serve_file(candidate_file, mime or "text/plain")
            return

        self.send_error(404, f"File or endpoint not found: {url_path}")

    def do_POST(self):
        url_path = self.path.split("?")[0]

        # 1. API: Update Application Status
        match = re.match(r"^/api/applications/(\d+)/status$", url_path)
        if match:
            job_id = int(match.group(1))
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

            try:
                data = json.loads(body)
                status = data.get("status", "applied")
                notes = data.get("notes")

                app_repo = ApplicationRepository()
                # Upsert or update status
                app_repo.upsert_application(
                    job_id=job_id,
                    status=status,
                    notes=notes,
                )
                app_repo.close()

                # Also regenerate static report so static snapshots reflect latest state
                generate_daily_reports()

                self._send_json({
                    "success": True,
                    "job_id": job_id,
                    "status": status,
                    "message": f"Job #{job_id} successfully marked as {status}",
                })
            except Exception as err:
                self._send_json({"error": str(err)}, status_code=400)
            return

        # 2. API: Regenerate Report
        if url_path == "/api/regenerate":
            res = generate_daily_reports()
            self._send_json({"success": True, "details": str(res)})
            return

        self.send_error(404, f"Endpoint not found: {url_path}")

    def _serve_file(self, file_path: Path, mime_type: str):
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: Dict[str, Any], status_code: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Clean terminal logging
        print(f"[HTTP {self.command}] {args[0]} -> {args[1]}")


def find_free_port(start_port: int = 8080, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def run_server(port: int = 8080):
    # Ensure fresh report is ready
    generate_daily_reports()

    active_port = find_free_port(port)
    server_address = ("0.0.0.0", active_port)
    httpd = HTTPServer(server_address, DashboardHandler)

    print("==================================================")
    print("AI JOB AGENT — INTERACTIVE DASHBOARD SERVER")
    print("==================================================")
    print(f"Server running at:  http://localhost:{active_port}")
    print(f"Network URL:        http://127.0.0.1:{active_port}")
    print("Press Ctrl+C to stop.")
    print("==================================================")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve the AI Job Agent interactive dashboard.")
    parser.add_argument("--port", type=int, default=8080, help="Port to serve on (default: 8080)")
    args = parser.parse_args()

    run_server(port=args.port)
