"""
Daily Digest and Interactive Report Generator.
Generates:
1. reports/daily_digest_YYYY-MM-DD.html (Rich interactive dashboard with status update buttons)
2. reports/daily_digest_YYYY-MM-DD.md (Clean markdown report)
"""

import datetime
import html
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.market.market_analyzer import MarketAnalyzer
from analyzer.personalization.resume_loader import load_resume
from database.application_repository import ApplicationRepository
from database.cover_letter_repository import CoverLetterRepository

DB_PATH = PROJECT_ROOT / "database" / "jobs.db"
REPORTS_DIR = PROJECT_ROOT / "reports"



def get_pipeline_statistics(conn: sqlite3.Connection) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM job_ai_analysis")
    stage1_total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM job_ai_analysis WHERE recommendation = 'send_to_stage_2' AND relevance_score >= 60")
    stage1_passed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidate_job_analysis")
    stage2_total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM job_stage3_analysis WHERE decision = 'apply'")
    shortlist_total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cover_letter_drafts")
    drafts_total = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
    app_statuses = dict(cursor.fetchall())

    return {
        "total_jobs": total_jobs,
        "stage1_total": stage1_total,
        "stage1_passed": stage1_passed,
        "stage2_total": stage2_total,
        "shortlist_total": shortlist_total,
        "drafts_total": drafts_total,
        "app_statuses": app_statuses,
    }


def get_actionable_jobs(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            j.id,
            j.company,
            j.title,
            j.location,
            j.url,
            j.posted_at,
            j.description,
            s3.decision,
            s3.priority,
            s3.final_score,
            s3.application_method,
            s3.readiness,
            s3.decision_reasons,
            s2.primary_track,
            s2.match_score,
            s2.technical_fit_score,
            s2.career_growth_score,
            s2.strengths,
            s2.skill_gaps,
            s2.reasoning,
            c.recommended_cv,
            c.letter_text,
            c.review_status,
            COALESCE(a.status, 'prepared') AS app_status,
            a.applied_date
        FROM jobs j
        JOIN job_stage3_analysis s3 ON j.id = s3.job_id
        JOIN candidate_job_analysis s2 ON j.id = s2.job_id
        LEFT JOIN cover_letter_drafts c ON j.id = c.job_id
        LEFT JOIN applications a ON j.id = a.job_id
        WHERE s3.decision = 'apply'
        ORDER BY
            CASE s3.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            s3.final_score DESC
    """
    cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        try:
            r["strengths_list"] = json.loads(r["strengths"]) if r.get("strengths") else []
        except Exception:
            r["strengths_list"] = []

        try:
            r["skill_gaps_list"] = json.loads(r["skill_gaps"]) if r.get("skill_gaps") else []
        except Exception:
            r["skill_gaps_list"] = []

    return rows


def generate_markdown_report(
    date_str: str,
    stats: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    market: Dict[str, Any],
) -> str:
    lines = []
    lines.append(f"# AI Job Agent — Daily Intelligence Report ({date_str})\n")
    lines.append("## 1. Pipeline Summary\n")
    lines.append(f"- **Total Jobs Ingested**: {stats['total_jobs']}")
    lines.append(f"- **Stage 1 Qualified**: {stats['stage1_passed']} / {stats['stage1_total']}")
    lines.append(f"- **Stage 2 Evaluated**: {stats['stage2_total']}")
    lines.append(f"- **Stage 3 Shortlisted**: **{stats['shortlist_total']} actionable jobs**")
    lines.append(f"- **Cover Letters Prepared**: {stats['drafts_total']}")
    lines.append(f"- **Application Statuses**: {stats['app_statuses']}\n")

    lines.append("## 2. Top Actionable Applications\n")
    lines.append("| ID | Company | Role & Location | Priority | Score | CV Variant | Status | Action |")
    lines.append("|:---:|:---|:---|:---:|:---:|:---|:---:|:---|")

    for j in jobs:
        prio = j["priority"].upper()
        cv = j.get("recommended_cv") or "N/A"
        status = j.get("app_status", "prepared").upper()
        url = j.get("url", "#")
        lines.append(
            f"| **{j['id']}** | **{j['company']}** | [{j['title']}]({url})<br>*{j['location']}* | "
            f"**{prio}** | {j['final_score']:.1f} | `{cv}` | `{status}` | [Apply ↗]({url}) |"
        )

    lines.append("\n## 3. High-ROI Skills to Add to Your Profile\n")
    lines.append("Based on market demand across your shortlisted opportunities, developing these skills unlocks the highest number of high-match roles:\n")

    for g in market.get("high_roi_skills_to_learn", []):
        lines.append(f"### • **{g['skill']}** ({g['category']})")
        lines.append(f"- **Required in**: {g['shortlist_mentions']} shortlisted roles (e.g., {', '.join(g['companies'])})")
        lines.append(f"- **Actionable Project**: {g['action_recommendation']}\n")

    lines.append("## 4. Top In-Demand Technologies in Market\n")
    lines.append("| Technology | Domain | Job Count |")
    lines.append("|:---|:---|:---:|")
    for s in market.get("top_skills", [])[:10]:
        lines.append(f"| {s['skill_name']} | {s['category']} | {s['job_count']} jobs |")

    return "\n".join(lines)


def generate_html_report(
    date_str: str,
    stats: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    market: Dict[str, Any],
) -> str:
    high_count = sum(1 for j in jobs if j["priority"] == "high")
    med_count = sum(1 for j in jobs if j["priority"] == "medium")
    applied_count = sum(1 for j in jobs if j.get("app_status") == "applied")
    prepared_count = sum(1 for j in jobs if j.get("app_status") != "applied")

    jobs_json = json.dumps(
        [
            {
                "id": j["id"],
                "company": j["company"],
                "title": j["title"],
                "location": j["location"],
                "priority": j["priority"],
                "score": j["final_score"],
                "track": j.get("primary_track", ""),
                "status": j.get("app_status", "prepared"),
                "cv": j.get("recommended_cv", ""),
            }
            for j in jobs
        ]
    )

    jobs_cards_html = []
    for j in jobs:
        jid = j["id"]
        priority_class = "priority-high" if j["priority"] == "high" else "priority-medium"
        app_status = j.get("app_status", "prepared")
        status_badge_class = "badge-applied" if app_status == "applied" else "badge-prepared"
        cv_name = j.get("recommended_cv", "General_Technical_CV")
        letter_escaped = html.escape(j.get("letter_text") or "No cover letter generated yet.")
        url = j.get("url") or "#"

        strengths_items = "".join(f"<li>{html.escape(s)}</li>" for s in j.get("strengths_list", [])[:3])
        gaps_items = "".join(f"<li>{html.escape(g)}</li>" for g in j.get("skill_gaps_list", [])[:3])

        card_html = f"""
        <div class="job-card" id="card-{jid}" data-priority="{j['priority']}" data-track="{j.get('primary_track', '')}" data-status="{app_status}" data-company="{html.escape(j['company'].lower())}" data-title="{html.escape(j['title'].lower())}">
            <div class="card-header">
                <div class="card-title-group">
                    <div class="company-badge">{html.escape(j['company'])}</div>
                    <h3 class="job-title">{html.escape(j['title'])}</h3>
                    <div class="job-location">📍 {html.escape(j['location'] or 'Remote / Hybrid')}</div>
                </div>
                <div class="card-badges">
                    <span class="badge {priority_class}">{j['priority'].upper()} PRIORITY</span>
                    <span class="score-badge">{j['final_score']:.1f} Match</span>
                    <span class="badge {status_badge_class}" id="status-badge-{jid}">{app_status.upper()}</span>
                </div>
            </div>

            <div class="card-meta-bar">
                <div class="meta-item"><strong>Track:</strong> <span class="track-tag">{html.escape(j.get('primary_track', 'general'))}</span></div>
                <div class="meta-item"><strong>CV:</strong> <span class="cv-tag">📄 {html.escape(cv_name)}</span></div>
                <div class="meta-item-actions">
                    <a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer" class="btn btn-apply-link">Apply on Company Site ↗</a>
                    <button class="btn btn-applied" id="btn-applied-{jid}" onclick="updateJobStatus({jid}, 'applied')">
                        { '✓ Applied' if app_status == 'applied' else '✓ Mark as Applied' }
                    </button>
                </div>
            </div>

            <div class="card-insights">
                <div class="insight-col">
                    <div class="insight-title">✓ Matching Strengths</div>
                    <ul class="insight-list strengths-list">
                        {strengths_items if strengths_items else "<li>Matches core technical background</li>"}
                    </ul>
                </div>
                <div class="insight-col">
                    <div class="insight-title">⚠️ Prep Points / Skill Gaps</div>
                    <ul class="insight-list gaps-list">
                        {gaps_items if gaps_items else "<li>No critical blockers identified</li>"}
                    </ul>
                </div>
            </div>

            <div class="accordion-section">
                <div class="accordion-header" onclick="toggleAccordion('letter-{jid}')">
                    <span>✉ Tailored Cover Letter Package</span>
                    <span class="accordion-icon" id="icon-letter-{jid}">▼</span>
                </div>
                <div class="accordion-body" id="letter-{jid}">
                    <div class="letter-actions-bar">
                        <span class="letter-status">Status: <strong>{j.get('review_status', 'draft')}</strong></span>
                        <button class="btn btn-copy" onclick="copyLetter({jid})">📋 Copy Letter to Clipboard</button>
                    </div>
                    <textarea class="letter-textarea" id="textarea-letter-{jid}" readonly>{letter_escaped}</textarea>
                </div>
            </div>
        </div>
        """
        jobs_cards_html.append(card_html)

    # Market Skills HTML
    market_skills_rows = []
    for s in market.get("top_skills", [])[:12]:
        pct = min(100, int((s["job_count"] / max(stats["total_jobs"], 1)) * 100 * 2))
        market_skills_rows.append(f"""
        <div class="skill-meter-row">
            <div class="skill-name-col">
                <strong>{html.escape(s['skill_name'])}</strong>
                <span class="skill-cat-pill">{s['category']}</span>
            </div>
            <div class="skill-bar-wrapper">
                <div class="skill-bar-fill" style="width: {pct}%;"></div>
            </div>
            <div class="skill-count-col">{s['job_count']} roles</div>
        </div>
        """)

    # High ROI Gaps HTML
    high_roi_cards = []
    for idx, g in enumerate(market.get("high_roi_skills_to_learn", []), start=1):
        companies_str = ", ".join(html.escape(c) for c in g["companies"])
        high_roi_cards.append(f"""
        <div class="roi-card">
            <div class="roi-card-header">
                <div class="roi-rank">#{idx}</div>
                <div>
                    <h4 class="roi-skill-name">{html.escape(g['skill'])}</h4>
                    <span class="skill-cat-pill">{g['category']}</span>
                </div>
                <div class="roi-impact-badge">{g['shortlist_mentions']} Shortlisted Roles</div>
            </div>
            <div class="roi-companies"><strong>Target Companies:</strong> {companies_str}</div>
            <div class="roi-recommendation">
                <strong>Recommended Project:</strong> {html.escape(g['action_recommendation'])}
            </div>
        </div>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Job Agent — Daily Intelligence Report ({date_str})</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --surface-color: #1e293b;
            --surface-hover: #283548;
            --surface-card: #182234;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-primary: #3b82f6;
            --accent-primary-hover: #2563eb;
            --accent-green: #10b981;
            --accent-green-hover: #059669;
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
            --danger-color: #ef4444;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: var(--font-family);
            line-height: 1.5;
            padding-bottom: 60px;
        }}

        /* Container */
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px 20px;
        }}

        /* Header */
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .header-title-group h1 {{
            font-size: 26px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .header-title-group p {{
            color: var(--text-secondary);
            font-size: 14px;
            margin-top: 4px;
        }}
        .status-pill-live {{
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.3);
            font-size: 12px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 9999px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .status-pill-live::before {{
            content: "";
            width: 8px;
            height: 8px;
            background-color: var(--accent-green);
            border-radius: 50%;
            display: inline-block;
        }}

        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .stat-card {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
        }}
        .stat-label {{
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 6px;
        }}
        .stat-sub {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        /* Tabs */
        .tab-nav {{
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 24px;
        }}
        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 15px;
            font-weight: 600;
            padding: 10px 18px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }}
        .tab-btn:hover {{
            color: var(--text-primary);
        }}
        .tab-btn.active {{
            color: var(--accent-primary);
            border-bottom-color: var(--accent-primary);
        }}

        /* Controls Bar */
        .controls-bar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 14px;
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 20px;
        }}
        .filter-buttons {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            background: var(--bg-color);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .filter-btn:hover {{
            color: var(--text-primary);
            border-color: var(--text-secondary);
        }}
        .filter-btn.active {{
            background: var(--accent-primary);
            color: #ffffff;
            border-color: var(--accent-primary);
        }}
        .search-box {{
            flex: 1;
            min-width: 240px;
            max-width: 360px;
        }}
        .search-input {{
            width: 100%;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 12px;
            color: var(--text-primary);
            font-size: 14px;
        }}
        .search-input:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}

        /* Job Cards */
        .jobs-list {{
            display: flex;
            flex-direction: column;
            gap: 18px;
        }}
        .job-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px 22px;
            transition: border-color 0.2s, box-shadow 0.2s;
        }}
        .job-card:hover {{
            border-color: #475569;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
        }}
        .company-badge {{
            font-size: 12px;
            font-weight: 700;
            color: var(--accent-primary);
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }}
        .job-title {{
            font-size: 19px;
            font-weight: 700;
            color: var(--text-primary);
            margin: 4px 0 6px 0;
        }}
        .job-location {{
            font-size: 13px;
            color: var(--text-secondary);
        }}
        .card-badges {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 0.5px;
        }}
        .priority-high {{
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}
        .priority-medium {{
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}
        .score-badge {{
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            font-size: 13px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
        }}
        .badge-prepared {{
            background: rgba(139, 92, 246, 0.15);
            color: #c084fc;
            border: 1px solid rgba(139, 92, 246, 0.3);
        }}
        .badge-applied {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        /* Meta bar */
        .card-meta-bar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            background: var(--surface-color);
            border-radius: 8px;
            padding: 10px 14px;
            margin: 14px 0;
            font-size: 13px;
        }}
        .track-tag, .cv-tag {{
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            padding: 2px 8px;
            border-radius: 4px;
            color: var(--text-primary);
        }}
        .meta-item-actions {{
            display: flex;
            gap: 10px;
        }}

        /* Buttons */
        .btn {{
            font-size: 13px;
            font-weight: 600;
            padding: 7px 14px;
            border-radius: 6px;
            cursor: pointer;
            border: none;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            text-decoration: none;
            gap: 6px;
        }}
        .btn-apply-link {{
            background: var(--accent-primary);
            color: #ffffff;
        }}
        .btn-apply-link:hover {{
            background: var(--accent-primary-hover);
        }}
        .btn-applied {{
            background: var(--accent-green);
            color: #ffffff;
        }}
        .btn-applied:hover {{
            background: var(--accent-green-hover);
        }}
        .btn-applied-done {{
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
            cursor: default;
        }}
        .btn-copy {{
            background: var(--surface-color);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }}
        .btn-copy:hover {{
            background: var(--surface-hover);
        }}

        /* Insights */
        .card-insights {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
            margin-bottom: 14px;
        }}
        @media (max-width: 768px) {{
            .card-insights {{ grid-template-columns: 1fr; }}
        }}
        .insight-col {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 14px;
        }}
        .insight-title {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
            color: var(--text-secondary);
        }}
        .insight-list {{
            list-style: none;
            font-size: 13px;
            color: var(--text-primary);
        }}
        .insight-list li {{
            margin-bottom: 4px;
            position: relative;
            padding-left: 14px;
        }}
        .strengths-list li::before {{
            content: "•";
            color: var(--accent-green);
            position: absolute;
            left: 0;
            font-weight: bold;
        }}
        .gaps-list li::before {{
            content: "•";
            color: var(--accent-amber);
            position: absolute;
            left: 0;
            font-weight: bold;
        }}

        /* Accordion */
        .accordion-section {{
            border-top: 1px solid var(--border-color);
            padding-top: 12px;
        }}
        .accordion-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            padding: 6px 0;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
        }}
        .accordion-header:hover {{
            color: var(--text-primary);
        }}
        .accordion-body {{
            display: none;
            margin-top: 10px;
        }}
        .accordion-body.open {{
            display: block;
        }}
        .letter-actions-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        .letter-textarea {{
            width: 100%;
            height: 240px;
            background: #090d16;
            color: #e2e8f0;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            font-family: var(--font-family);
            font-size: 13px;
            line-height: 1.6;
            resize: vertical;
        }}

        /* Market Intelligence Section */
        .market-section {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }}
        @media (max-width: 900px) {{
            .market-section {{ grid-template-columns: 1fr; }}
        }}
        .market-box {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 20px;
        }}
        .market-box h3 {{
            font-size: 17px;
            font-weight: 700;
            margin-bottom: 16px;
            color: var(--text-primary);
        }}

        /* Skill Meter */
        .skill-meter-row {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
            font-size: 13px;
        }}
        .skill-name-col {{
            width: 170px;
            display: flex;
            flex-direction: column;
        }}
        .skill-cat-pill {{
            font-size: 10px;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        .skill-bar-wrapper {{
            flex: 1;
            height: 8px;
            background: var(--bg-color);
            border-radius: 4px;
            overflow: hidden;
        }}
        .skill-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent-primary), var(--accent-green));
            border-radius: 4px;
        }}
        .skill-count-col {{
            width: 60px;
            text-align: right;
            color: var(--text-secondary);
            font-weight: 600;
        }}

        /* ROI Cards */
        .roi-cards-list {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}
        .roi-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px 16px;
        }}
        .roi-card-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .roi-rank {{
            background: rgba(245, 158, 11, 0.15);
            color: var(--accent-amber);
            font-weight: 700;
            font-size: 13px;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .roi-skill-name {{
            font-size: 15px;
            font-weight: 700;
        }}
        .roi-impact-badge {{
            margin-left: auto;
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
        }}
        .roi-companies {{
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 6px;
        }}
        .roi-recommendation {{
            font-size: 12px;
            color: #cbd5e1;
            background: #0f172a;
            padding: 8px 12px;
            border-radius: 6px;
            border-left: 3px solid var(--accent-primary);
        }}

        /* Toast notification */
        .toast {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #10b981;
            color: #ffffff;
            font-weight: 600;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.3s;
            pointer-events: none;
            z-index: 1000;
        }}
        .toast.show {{
            opacity: 1;
            transform: translateY(0);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-title-group">
                <h1>AI Job Agent — Daily Intelligence Report</h1>
                <p>Generated on {date_str} • Candidate: <strong>Negar Najafi</strong></p>
            </div>
            <div>
                <span class="status-pill-live">Pipeline Healthy & Up to Date</span>
            </div>
        </header>

        <!-- Stats Overview -->
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">Actionable Shortlist</span>
                <span class="stat-value">{stats['shortlist_total']}</span>
                <span class="stat-sub">{high_count} High Priority • {med_count} Medium</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Prepared Packages</span>
                <span class="stat-value">{prepared_count}</span>
                <span class="stat-sub">Tailored CV & Cover Letters</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Applied To Date</span>
                <span class="stat-value" id="stat-applied-count">{applied_count}</span>
                <span class="stat-sub">Tracked in Database</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Market Monitored</span>
                <span class="stat-value">{stats['total_jobs']}</span>
                <span class="stat-sub">{stats['stage1_passed']} Qualified Roles</span>
            </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="tab-nav">
            <button class="tab-btn active" onclick="switchTab('shortlist')">🎯 Actionable Applications ({len(jobs)})</button>
            <button class="tab-btn" onclick="switchTab('market')">📈 Market Direction & Skills to Add ({len(market.get('high_roi_skills_to_learn', []))})</button>
        </div>

        <!-- Tab 1: Shortlist -->
        <div id="tab-shortlist">
            <div class="controls-bar">
                <div class="filter-buttons">
                    <button class="filter-btn active" onclick="filterJobs('all', this)">All ({len(jobs)})</button>
                    <button class="filter-btn" onclick="filterJobs('high', this)">High Priority ({high_count})</button>
                    <button class="filter-btn" onclick="filterJobs('medium', this)">Medium Priority ({med_count})</button>
                    <button class="filter-btn" onclick="filterJobs('prepared', this)">Prepared ({prepared_count})</button>
                    <button class="filter-btn" onclick="filterJobs('applied', this)">Applied ({applied_count})</button>
                </div>
                <div class="search-box">
                    <input type="text" class="search-input" id="search-input" placeholder="Search company, title, or city..." oninput="handleSearch()">
                </div>
            </div>

            <div class="jobs-list" id="jobs-container">
                {"".join(jobs_cards_html)}
            </div>
        </div>

        <!-- Tab 2: Market Intelligence -->
        <div id="tab-market" style="display: none;">
            <div class="market-section">
                <!-- Left: High ROI Skills to Add -->
                <div class="market-box">
                    <h3>💡 Skills You Should Add to Your Profile</h3>
                    <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 16px;">
                        These technologies appear most frequently across your high-match shortlisted opportunities. Building hands-on demonstrations for these will maximize your application-to-interview conversion:
                    </p>
                    <div class="roi-cards-list">
                        {"".join(high_roi_cards)}
                    </div>
                </div>

                <!-- Right: Top Demanded Skills -->
                <div class="market-box">
                    <h3>📊 Top In-Demand Technologies in Market</h3>
                    <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 16px;">
                        Skill frequency across all {stats['total_jobs']} European engineering opportunities evaluated:
                    </p>
                    <div class="skills-meters-list">
                        {"".join(market_skills_rows)}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div class="toast" id="toast">Notification message</div>

    <script>
        function switchTab(tabId) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (tabId === 'shortlist') {{
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
                document.getElementById('tab-shortlist').style.display = 'block';
                document.getElementById('tab-market').style.display = 'none';
            }} else {{
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                document.getElementById('tab-shortlist').style.display = 'none';
                document.getElementById('tab-market').style.display = 'block';
            }}
        }}

        function toggleAccordion(id) {{
            const body = document.getElementById(id);
            const icon = document.getElementById('icon-' + id);
            if (body.classList.contains('open')) {{
                body.classList.remove('open');
                icon.innerText = '▼';
            }} else {{
                body.classList.add('open');
                icon.innerText = '▲';
            }}
        }}

        function copyLetter(jobId) {{
            const textarea = document.getElementById('textarea-letter-' + jobId);
            textarea.select();
            navigator.clipboard.writeText(textarea.value);
            showToast('✓ Cover letter copied to clipboard!');
        }}

        async function updateJobStatus(jobId, newStatus) {{
            const btn = document.getElementById('btn-applied-' + jobId);
            const badge = document.getElementById('status-badge-' + jobId);
            const card = document.getElementById('card-' + jobId);

            btn.disabled = true;
            btn.innerText = 'Updating...';

            try {{
                const res = await fetch(`/api/applications/${{jobId}}/status`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ status: newStatus }})
                }});

                if (res.ok) {{
                    badge.className = 'badge badge-applied';
                    badge.innerText = 'APPLIED';
                    btn.className = 'btn btn-applied-done';
                    btn.innerText = '✓ Applied';
                    card.setAttribute('data-status', 'applied');
                    showToast(`✓ Job #${{jobId}} marked as APPLIED in database!`);
                    incrementAppliedCount();
                }} else {{
                    throw new Error('API unavailable');
                }}
            }} catch (err) {{
                // Offline fallback (when viewing static HTML file directly)
                localStorage.setItem(`app_status_${{jobId}}`, newStatus);
                badge.className = 'badge badge-applied';
                badge.innerText = 'APPLIED (Local)';
                btn.className = 'btn btn-applied-done';
                btn.innerText = '✓ Applied (Saved Locally)';
                card.setAttribute('data-status', 'applied');
                showToast(`✓ Job #${{jobId}} marked as applied (saved locally). Start dashboard server for full DB sync.`);
                incrementAppliedCount();
            }}
        }}

        function incrementAppliedCount() {{
            const el = document.getElementById('stat-applied-count');
            if (el) {{
                const current = parseInt(el.innerText, 10) || 0;
                el.innerText = current + 1;
            }}
        }}

        function filterJobs(filter, btn) {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const cards = document.querySelectorAll('.job-card');
            cards.forEach(card => {{
                const priority = card.getAttribute('data-priority');
                const status = card.getAttribute('data-status');

                if (filter === 'all') {{
                    card.style.display = 'block';
                }} else if (filter === 'high' || filter === 'medium') {{
                    card.style.display = (priority === filter) ? 'block' : 'none';
                }} else if (filter === 'prepared' || filter === 'applied') {{
                    card.style.display = (status === filter) ? 'block' : 'none';
                }}
            }});
        }}

        function handleSearch() {{
            const term = document.getElementById('search-input').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.job-card');
            cards.forEach(card => {{
                const comp = card.getAttribute('data-company') || '';
                const title = card.getAttribute('data-title') || '';
                if (comp.includes(term) || title.includes(term)) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}

        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3500);
        }}

        // Check local storage for offline state restoration
        window.addEventListener('DOMContentLoaded', () => {{
            const cards = document.querySelectorAll('.job-card');
            cards.forEach(card => {{
                const jid = card.id.replace('card-', '');
                const localStatus = localStorage.getItem(`app_status_${{jid}}`);
                if (localStatus === 'applied') {{
                    const badge = document.getElementById('status-badge-' + jid);
                    const btn = document.getElementById('btn-applied-' + jid);
                    if (badge && btn && card.getAttribute('data-status') !== 'applied') {{
                        badge.className = 'badge badge-applied';
                        badge.innerText = 'APPLIED';
                        btn.className = 'btn btn-applied-done';
                        btn.innerText = '✓ Applied';
                        card.setAttribute('data-status', 'applied');
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>
"""
    return html_content


def generate_daily_reports(db_path: Path = DB_PATH, reports_dir: Path = REPORTS_DIR) -> Dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.date.today().isoformat()

    conn = sqlite3.connect(db_path)
    stats = get_pipeline_statistics(conn)
    jobs = get_actionable_jobs(conn)
    conn.close()

    market_analyzer = MarketAnalyzer(db_path)
    market_report = market_analyzer.get_market_intelligence_report()
    market_analyzer.close()

    md_content = generate_markdown_report(today_str, stats, jobs, market_report)
    md_file = reports_dir / f"daily_digest_{today_str}.md"
    md_file.write_text(md_content, encoding="utf-8")

    html_content = generate_html_report(today_str, stats, jobs, market_report)
    html_file = reports_dir / f"daily_digest_{today_str}.html"
    html_file.write_text(html_content, encoding="utf-8")

    # Also keep a pointer index.html for convenient viewing
    latest_html = reports_dir / "latest_report.html"
    latest_html.write_text(html_content, encoding="utf-8")

    return {
        "md_path": md_file,
        "html_path": html_file,
        "latest_html": latest_html,
        "jobs_count": len(jobs),
    }


if __name__ == "__main__":
    result = generate_daily_reports()
    print("==================================================")
    print("DAILY DIGEST GENERATED SUCCESSFULLY")
    print(f"Actionable Jobs: {result['jobs_count']}")
    print(f"Markdown Report: {result['md_path']}")
    print(f"HTML Report:     {result['html_path']}")
    print(f"Latest Link:     {result['latest_html']}")
    print("==================================================")
