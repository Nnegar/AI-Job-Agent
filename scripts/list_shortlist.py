import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "database" / "jobs.db"

def list_shortlist():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT s3.job_id, s3.priority, s3.final_score, s2.primary_track, j.company, j.title, j.location
        FROM job_stage3_analysis s3
        JOIN jobs j ON j.id = s3.job_id
        JOIN candidate_job_analysis s2 ON s2.job_id = s3.job_id
        WHERE s3.decision = 'apply'
        ORDER BY s3.final_score DESC
    """).fetchall()

    print(f"Total shortlisted jobs: {len(rows)}")
    for r in rows:
        print(f"ID {r[0]:3d} | Priority: {r[1]:6s} | Score: {r[2]:5.1f} | Track: {r[3]:22s} | {r[4]:15s} | {r[5]} ({r[6]})")

if __name__ == "__main__":
    list_shortlist()
