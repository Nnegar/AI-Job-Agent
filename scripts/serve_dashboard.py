#!/usr/bin/env python3
"""
Interactive Dashboard Local Server.
Serves the daily intelligence report and provides REST API endpoints to:
1. Update application status (e.g. mark as 'applied', 'screening', 'interview', 'offered', 'rejected', 'withdrawn') directly in jobs.db.
2. Query live application statuses, pipeline metrics, and paginated historical database jobs.
3. Automatically re-render static report snapshots on status transitions.

Run via:
    python scripts/serve_dashboard.py [--port 8080]
"""

import argparse
import json
import mimetypes
import re
import socket
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.application_repository import ApplicationRepository, normalize_status
from reports.daily_report_generator import generate_daily_reports

REPORTS_DIR = PROJECT_ROOT / "reports"


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        url_path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 1. API: List Applications
        if url_path == "/api/applications":
            app_repo = ApplicationRepository()
            apps = app_repo.get_all()
            app_repo.close()
            self._send_json({"applications": apps})
            return

        # 2. API: Pipeline Summary & Jobs
        if url_path == "/api/pipeline":
            app_repo = ApplicationRepository()
            summary = app_repo.get_pipeline_summary()
            jobs = app_repo.get_pipeline_jobs()
            app_repo.close()
            self._send_json({
                "summary": summary,
                "jobs": jobs,
            })
            return

        # API: Run Pipeline Real-Time Event Stream (SSE)
        if url_path == "/api/pipeline/run-stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform, must-revalidate")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            from analyzer.pipeline_runner import PipelineRunner

            def emit_sse(step_data):
                msg = f"data: {json.dumps(step_data)}\n\n"
                try:
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            try:
                runner = PipelineRunner()
                runner.run_full_pipeline(
                    max_lookback_days=7,
                    max_stage1_batch=20,
                    max_stage2_batch=15,
                    event_callback=emit_sse,
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                emit_sse({
                    "stage": "error",
                    "percent": 100,
                    "callout": f"Pipeline execution error: {str(e)}",
                    "error": str(e),
                })
            return

        # 3. API: Database Historical Query (Paginated)
        if url_path == "/api/database/jobs":
            search = query_params.get("search", [None])[0]
            company = query_params.get("company", [None])[0]
            track = query_params.get("track", [None])[0]
            priority = query_params.get("priority", [None])[0]
            status = query_params.get("status", [None])[0]
            source = query_params.get("source", [None])[0]
            location = query_params.get("location", [None])[0]

            try:
                page = int(query_params.get("page", ["1"])[0])
            except ValueError:
                page = 1

            try:
                limit = int(query_params.get("limit", ["25"])[0])
            except ValueError:
                limit = 25

            app_repo = ApplicationRepository()
            result = app_repo.get_database_jobs(
                search=search,
                company=company,
                track=track,
                priority=priority,
                status=status,
                source=source,
                location=location,
                page=page,
                limit=limit,
            )
            filters = app_repo.get_filter_options()
            app_repo.close()

            result["filters"] = filters
            self._send_json(result)
            return

        # 4. Serve Latest Daily Report
        if url_path in ("/", "/index.html", "/report"):
            report_file = REPORTS_DIR / "latest_report.html"
            if not report_file.exists():
                generate_daily_reports()

            self._serve_file(report_file, "text/html")
            return

        # 5. Serve Other Files in Reports Directory
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
                raw_status = data.get("status")
                notes = data.get("notes")
                applied_date = data.get("applied_date")

                app_repo = ApplicationRepository()
                if raw_status:
                    status = normalize_status(raw_status)
                    app_repo.upsert_application(
                        job_id=job_id,
                        status=status,
                        notes=notes,
                        applied_date=applied_date,
                    )
                elif notes is not None:
                    app_repo.update_notes(job_id=job_id, notes=notes)
                    existing = app_repo.get_by_job_id(job_id)
                    status = existing["status"] if existing else "applied"
                else:
                    status = "applied"
                    app_repo.upsert_application(
                        job_id=job_id,
                        status=status,
                    )
                pipeline_summary = app_repo.get_pipeline_summary()
                app_repo.close()

                # Regenerate static report asynchronously / immediately
                generate_daily_reports()

                self._send_json({
                    "success": True,
                    "job_id": job_id,
                    "status": status,
                    "summary": pipeline_summary,
                    "message": f"Job #{job_id} successfully marked as {status.upper()}",
                })
            except Exception as err:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(err)}, status_code=400)
            return

        # 2. API: Regenerate Report
        if url_path == "/api/regenerate":
            res = generate_daily_reports()
            self._send_json({"success": True, "details": str(res)})
            return

        # 3. API: Run Pipeline (Direct JSON response)
        if url_path == "/api/pipeline/run":
            try:
                from analyzer.pipeline_runner import PipelineRunner
                runner = PipelineRunner()
                summary = runner.run_full_pipeline(
                    max_lookback_days=7,
                    max_stage1_batch=20,
                    max_stage2_batch=15,
                )
                last_run_str = runner.run_repo.get_last_run_display()
                self._send_json({
                    "success": True,
                    "stage": "complete",
                    "last_run": last_run_str,
                    "summary": summary,
                })
            except Exception as err:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(err)}, status_code=500)
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

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
    print("Endpoints:")
    print(f"  • Web Dashboard:     http://localhost:{active_port}/")
    print(f"  • Pipeline API:      http://localhost:{active_port}/api/pipeline")
    print(f"  • Database Jobs API: http://localhost:{active_port}/api/database/jobs")
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
