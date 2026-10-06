#!/usr/bin/env python3
"""
Daily Digest and Interactive Report Generator.
Generates:
1. reports/daily_digest_YYYY-MM-DD.html (Complete 4-tab interactive dashboard: Action Queue, Application Pipeline Tracker with Details Modal, Job Database Archive, Market Intelligence)
2. reports/daily_digest_YYYY-MM-DD.md (Clean markdown digest report)
3. reports/latest_report.html (Symlink/copy for convenient local opening)
"""

import datetime
import html
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.market.gap_classifier import classify_gaps
from analyzer.market.market_analyzer import MarketAnalyzer
from database.application_repository import ApplicationRepository, normalize_status

DB_PATH = PROJECT_ROOT / "database" / "jobs.db"
REPORTS_DIR = PROJECT_ROOT / "reports"


def format_freshness(
    posted_at: Optional[str],
    collected_at: Optional[str] = None,
    ref_date: Optional[datetime.date] = None,
) -> Dict[str, str]:
    """
    Computes a human-readable freshness badge based on posting date.
    Returns: {"badge": str, "label": str, "class": str}
    """
    if ref_date is None:
        ref_date = datetime.date.today()

    date_to_use = None
    if posted_at:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", posted_at)
        if m:
            try:
                date_to_use = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        if not date_to_use:
            text = posted_at.lower()
            if "today" in text or "just" in text or "hour" in text:
                return {"badge": "🟢 Today", "label": "Today", "class": "fresh-today"}
            if "yesterday" in text:
                return {"badge": "🟢 1d ago", "label": "1d ago", "class": "fresh-recent"}
            m_days = re.search(r"(\d+)\s*(?:d|day|days)", text)
            if m_days:
                days = int(m_days.group(1))
                if days <= 3:
                    return {"badge": f"🟢 {days}d ago", "label": f"{days}d ago", "class": "fresh-recent"}
                elif days <= 7:
                    return {"badge": f"🔵 {days}d ago", "label": f"{days}d ago", "class": "fresh-week"}
                elif days <= 14:
                    return {"badge": f"🟡 {days}d ago", "label": f"{days}d ago", "class": "fresh-two-weeks"}
                else:
                    return {"badge": f"⚪ {days}d ago", "label": f"{days}d ago", "class": "fresh-older"}

    if not date_to_use and collected_at:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", collected_at)
        if m:
            try:
                date_to_use = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

    if date_to_use:
        diff = (ref_date - date_to_use).days
        if diff <= 0:
            return {"badge": "🟢 Today", "label": "Today", "class": "fresh-today"}
        elif diff == 1:
            return {"badge": "🟢 1d ago", "label": "1d ago", "class": "fresh-recent"}
        elif diff <= 3:
            return {"badge": f"🟢 {diff}d ago", "label": f"{diff}d ago", "class": "fresh-recent"}
        elif diff <= 7:
            return {"badge": f"🔵 {diff}d ago", "label": f"{diff}d ago", "class": "fresh-week"}
        elif diff <= 14:
            return {"badge": f"🟡 {diff}d ago", "label": f"{diff}d ago", "class": "fresh-two-weeks"}
        else:
            return {"badge": f"⚪ {diff}d ago", "label": f"{diff}d ago", "class": "fresh-older"}

    return {"badge": "🟢 Recent", "label": "Recent", "class": "fresh-recent"}


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
    raw_statuses = dict(cursor.fetchall())
    app_statuses: Dict[str, int] = {}
    for st, count in raw_statuses.items():
        norm = normalize_status(st)
        app_statuses[norm] = app_statuses.get(norm, 0) + count

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
    """
    Returns only jobs requiring candidate action (status is NULL or 'prepared').
    """
    app_repo = ApplicationRepository()
    rows = app_repo.get_action_queue()
    app_repo.close()

    for r in rows:
        try:
            r["strengths_list"] = json.loads(r["strengths"]) if r.get("strengths") else []
        except Exception:
            r["strengths_list"] = []

        try:
            raw_gaps = json.loads(r["skill_gaps"]) if r.get("skill_gaps") else []
        except Exception:
            raw_gaps = []

        r["skill_gaps_classified"] = classify_gaps(raw_gaps)
        r["freshness"] = format_freshness(r.get("posted_at"), r.get("collected_at"))

    return rows


def get_pipeline_jobs(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Returns ONLY jobs active in the application tracker (applied, screening, interview, offered, rejected, withdrawn).
    """
    app_repo = ApplicationRepository()
    rows = app_repo.get_pipeline_jobs()
    app_repo.close()

    for r in rows:
        try:
            r["strengths_list"] = json.loads(r["strengths"]) if r.get("strengths") else []
        except Exception:
            r["strengths_list"] = []

        try:
            raw_gaps = json.loads(r["skill_gaps"]) if r.get("skill_gaps") else []
        except Exception:
            raw_gaps = []

        r["skill_gaps_classified"] = classify_gaps(raw_gaps)
        r["freshness"] = format_freshness(r.get("posted_at"), r.get("collected_at"))

    return rows


def get_all_database_jobs(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Returns full database inventory for Tab 3 (Job Database Archive).
    """
    app_repo = ApplicationRepository()
    result = app_repo.get_database_jobs(limit=10000)
    app_repo.close()

    for r in result["items"]:
        r["freshness"] = format_freshness(r.get("posted_at"), r.get("collected_at"))

    return result["items"]


def generate_markdown_report(
    date_str: str,
    stats: Dict[str, Any],
    action_jobs: List[Dict[str, Any]],
    pipeline_jobs: List[Dict[str, Any]],
    pipeline_summary: Dict[str, int],
    market: Dict[str, Any],
) -> str:
    lines = []
    lines.append(f"# AI Job Agent — Daily Intelligence Report ({date_str})\n")
    lines.append("## 1. Application Pipeline Summary\n")
    lines.append(f"- **Action Queue (Prepared)**: **{len(action_jobs)} jobs awaiting application**")
    lines.append(f"- **Active Pipeline**: {pipeline_summary.get('all_active', 0)} Active | "
                 f"{pipeline_summary.get('applied', 0)} Applied | "
                 f"{pipeline_summary.get('screening', 0)} Screening | "
                 f"{pipeline_summary.get('interview', 0)} Interview | "
                 f"{pipeline_summary.get('offered', 0)} Offers | "
                 f"{pipeline_summary.get('rejected', 0)} Rejected | "
                 f"{pipeline_summary.get('withdrawn', 0)} Withdrawn")
    lines.append(f"- **Total Ingested Database**: {stats['total_jobs']} European opportunities\n")

    lines.append("## 2. Action Queue — Top Applications Ready to Submit\n")
    lines.append("| ID | Company | Role & Location | Freshness | Priority | Match | CV Variant | Action |")
    lines.append("|:---:|:---|:---|:---:|:---:|:---:|:---|:---|")

    for j in action_jobs:
        prio = j["priority"].upper()
        cv = j.get("recommended_cv") or "N/A"
        fresh = j["freshness"]["badge"]
        url = j.get("url", "#")
        lines.append(
            f"| **{j['id']}** | **{j['company']}** | [{j['title']}]({url})<br>*{j['location']}* | "
            f"`{fresh}` | **{prio}** | {j['final_score']:.1f}% | `{cv}` | [Apply ↗]({url}) |"
        )

    if pipeline_jobs:
        lines.append("\n## 3. Active Application Tracker\n")
        lines.append("| ID | Company | Role | Stage | Applied Date | CV Used |")
        lines.append("|:---:|:---|:---|:---:|:---:|:---|")
        for pj in pipeline_jobs:
            lines.append(
                f"| **{pj['id']}** | **{pj['company']}** | {pj['title']} | "
                f"`{pj['app_status'].upper()}` | {pj.get('applied_date') or 'N/A'} | `{pj.get('recommended_cv', 'N/A')}` |"
            )

    lines.append("\n## 4. Market Direction: Where Your Target Market Is Moving\n")
    for dm in market.get("domain_momentum", []):
        lines.append(f"- **{dm['domain']}** [{dm['status'].upper()}]: {dm['description']}")

    lines.append("\n## 5. Your Skill Position (Market Demand vs. Profile)\n")
    lines.append("| Skill | Domain | Market % | Your Fit % | Action Recommendation |")
    lines.append("|:---|:---|:---:|:---:|:---:|")
    for sp in market.get("candidate_skill_position", []):
        lines.append(f"| **{sp['skill']}** | {sp['domain']} | {sp['market_demand']}% | {sp['your_level']}% | **{sp['action'].upper()}** |")

    lines.append("\n## 6. High-ROI Skills to Add to Your Profile\n")
    for g in market.get("high_roi_skills_to_learn", []):
        lines.append(f"### • **{g['skill']}** ({g['category']})")
        lines.append(f"- **Required in**: {g['shortlist_mentions']} shortlisted roles (e.g., {', '.join(g['companies'])})")
        lines.append(f"- **Actionable Project**: {g['action_recommendation']}\n")

    return "\n".join(lines)


def generate_html_report(
    date_str: str,
    stats: Dict[str, Any],
    action_jobs: List[Dict[str, Any]],
    pipeline_jobs: List[Dict[str, Any]],
    all_db_jobs: List[Dict[str, Any]],
    pipeline_summary: Dict[str, int],
    market: Dict[str, Any],
) -> str:
    high_count = sum(1 for j in action_jobs if j["priority"] == "high")
    med_count = sum(1 for j in action_jobs if j["priority"] == "medium")
    action_count = len(action_jobs)
    total_db_count = len(all_db_jobs)
    active_pipe_count = pipeline_summary.get("all_active", 0)

    from database.pipeline_run_repository import PipelineRunRepository
    run_repo = PipelineRunRepository()
    last_run_display = run_repo.get_last_run_display()
    run_repo.close()

    # 1. Generate Action Queue Cards HTML (Tab 1)
    action_cards_html = []
    for j in action_jobs:
        jid = j["id"]
        priority_class = "priority-high" if j["priority"] == "high" else "priority-medium"
        cv_name = j.get("recommended_cv", "General_Technical_CV")
        letter_escaped = html.escape(j.get("letter_text") or "No cover letter generated yet.")
        url = j.get("url") or "#"
        fresh = j["freshness"]

        strengths_items = "".join(f"<li>{html.escape(s)}</li>" for s in j.get("strengths_list", [])[:3])

        # 3-Tier Skill Gap rendering
        gap_items_html = []
        for g in j.get("skill_gaps_classified", [])[:3]:
            tier = g["tier"]
            badge_cls = g["badge_class"]
            skill_name = html.escape(g["skill"])
            desc = html.escape(g["description"])
            gap_items_html.append(f"""
                <li class="gap-item">
                    <span class="gap-pill {badge_cls}">{tier}</span>
                    <strong class="gap-name">{skill_name}</strong>: {desc}
                </li>
            """)
        gaps_rendered = "".join(gap_items_html) if gap_items_html else "<li>No critical blockers identified</li>"

        card_html = f"""
        <div class="job-card" id="card-{jid}" data-priority="{j['priority']}" data-track="{j.get('primary_track', '')}" data-company="{html.escape(j['company'].lower())}" data-title="{html.escape(j['title'].lower())}">
            <div class="card-header">
                <div class="card-title-group">
                    <div class="company-badge-row">
                        <span class="company-badge">{html.escape(j['company'])}</span>
                        <span class="freshness-badge {fresh['class']}">{fresh['badge']}</span>
                    </div>
                    <h3 class="job-title">{html.escape(j['title'])}</h3>
                    <div class="job-location">📍 {html.escape(j['location'] or 'Europe / Hybrid')}</div>
                </div>
                <div class="card-badges">
                    <span class="badge {priority_class}">{j['priority'].upper()} PRIORITY</span>
                    <span class="score-badge">{j['final_score']:.1f}% Match</span>
                    <span class="badge badge-prepared">PREPARED</span>
                </div>
            </div>

            <div class="card-meta-bar">
                <div class="meta-item"><strong>Track:</strong> <span class="track-tag">{html.escape(j.get('primary_track', 'general'))}</span></div>
                <div class="meta-item"><strong>CV Package:</strong> <span class="cv-tag">📄 {html.escape(cv_name)}</span></div>
                <div class="meta-item-actions">
                    <a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer" class="btn btn-apply-link">Apply on Company Site ↗</a>
                    <button class="btn btn-applied" id="btn-applied-{jid}" onclick="markAsApplied({jid}, '{html.escape(j['company'])}', '{html.escape(j['title'])}')">
                        ✓ Mark as Applied
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
                    <div class="insight-title">⚠️ Prep Points / Skill Gaps (3-Tier Classification)</div>
                    <ul class="insight-list gaps-list">
                        {gaps_rendered}
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
        action_cards_html.append(card_html)

    # 2. Pipeline Jobs JSON Serialization for client-side table rendering, filtering, and details modal
    pipeline_jobs_data = []
    for pj in pipeline_jobs:
        score = pj.get("final_score") or pj.get("match_score") or 0
        pipeline_jobs_data.append({
            "id": pj["id"],
            "company": pj.get("company") or "Unknown",
            "title": pj.get("title") or "Technical Role",
            "location": pj.get("location") or "Europe / Remote",
            "track": pj.get("primary_track") or "general",
            "priority": pj.get("priority") or "medium",
            "score": float(score),
            "stage": normalize_status(pj.get("app_status") or "applied"),
            "applied_date": pj.get("applied_date") or "",
            "url": pj.get("url") or "#",
            "cv": pj.get("recommended_cv") or "General_CV",
            "letter": pj.get("letter_text") or "",
            "notes": pj.get("notes") or "",
            "created_at": pj.get("application_created_at") or "",
        })
    pipeline_jobs_json = json.dumps(pipeline_jobs_data)

    # 3. All DB Jobs JSON Serialization for Tab 3 (Complete Historical Database)
    db_jobs_data = []
    for dj in all_db_jobs:
        score = dj.get("match_score") or 0
        db_jobs_data.append({
            "id": dj["id"],
            "company": dj.get("company") or "Unknown",
            "title": dj.get("title") or "Role",
            "location": dj.get("location") or "Europe",
            "source": dj.get("source") or "greenhouse",
            "track": dj.get("primary_track") or "general",
            "priority": dj.get("priority") or "none",
            "score": float(score),
            "status": dj.get("app_status") or "discovered",
            "freshness": dj["freshness"]["badge"],
            "url": dj.get("url") or "#",
        })
    db_jobs_json = json.dumps(db_jobs_data)

    # Distinct filters for dropdowns
    companies_db = sorted(list(set(j["company"] for j in all_db_jobs if j.get("company"))))
    tracks_db = sorted(list(set(j.get("primary_track", "general") for j in all_db_jobs if j.get("primary_track"))))
    sources_db = sorted(list(set(j.get("source", "greenhouse") for j in all_db_jobs if j.get("source"))))

    pipe_companies = sorted(list(set(j["company"] for j in pipeline_jobs_data if j.get("company"))))
    pipe_tracks = sorted(list(set(j.get("track", "general") for j in pipeline_jobs_data if j.get("track"))))

    # Market Moving: Domain Momentum HTML (Tab 4)
    domain_momentum_rows = []
    for dm in market.get("domain_momentum", []):
        domain_momentum_rows.append(f"""
        <div class="momentum-item">
            <div class="momentum-header">
                <span class="momentum-domain">{html.escape(dm['domain'])}</span>
                <span class="trend-tag {dm['trend_class']}">{dm['status'].upper()}</span>
            </div>
            <div class="momentum-bar-wrap">
                <div class="momentum-bar-fill {dm['trend_class']}" style="width: {dm['score']}%;"></div>
            </div>
            <p class="momentum-desc">{html.escape(dm['description'])}</p>
        </div>
        """)

    # Your Skill Position Table HTML (Tab 4)
    skill_position_rows = []
    for sp in market.get("candidate_skill_position", []):
        skill_position_rows.append(f"""
        <tr>
            <td class="col-skill">
                <strong>{html.escape(sp['skill'])}</strong>
                <span class="sub-domain">{html.escape(sp['domain'])}</span>
            </td>
            <td class="col-meter">
                <div class="meter-pair">
                    <div class="meter-bar-wrap">
                        <div class="meter-fill market-fill" style="width: {sp['market_demand']}%;"></div>
                    </div>
                    <span class="meter-pct">{sp['market_demand']}%</span>
                </div>
            </td>
            <td class="col-meter">
                <div class="meter-pair">
                    <div class="meter-bar-wrap">
                        <div class="meter-fill candidate-fill" style="width: {sp['your_level']}%;"></div>
                    </div>
                    <span class="meter-pct">{sp['your_level']}%</span>
                </div>
            </td>
            <td class="col-action">
                <span class="action-pill {sp['action_class']}">{sp['action'].upper()}</span>
            </td>
            <td class="col-notes">{html.escape(sp['notes'])}</td>
        </tr>
        """)

    # High ROI Skills Cards HTML (Tab 4)
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
            <div class="roi-companies"><strong>Target Roles:</strong> {companies_str}</div>
            <div class="roi-recommendation">
                <strong>Demonstration Blueprint:</strong> {html.escape(g['action_recommendation'])}
            </div>
        </div>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Job Agent — Daily Intelligence Report & Application Pipeline ({date_str})</title>
    <style>
        :root {{
            --bg-color: #0b1120;
            --surface-color: #172033;
            --surface-hover: #1f2c45;
            --surface-card: #131c2e;
            --border-color: #27354f;
            --border-light: #374766;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-primary: #3b82f6;
            --accent-primary-hover: #2563eb;
            --accent-green: #10b981;
            --accent-green-hover: #059669;
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
            --accent-coral: #ef4444;
            --accent-cyan: #06b6d4;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: var(--font-family);
            line-height: 1.5;
            padding-bottom: 80px;
        }}

        .container {{
            max-width: 1360px;
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
            flex-wrap: wrap;
            gap: 16px;
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
        .header-runner-panel {{
            display: flex;
            align-items: center;
            gap: 14px;
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.2);
            padding: 8px 14px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}
        .header-status-line {{
            display: flex;
            align-items: center;
            gap: 7px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
        }}
        .status-indicator-dot {{
            width: 9px;
            height: 9px;
            background-color: var(--accent-green);
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px rgba(16, 185, 129, 0.7);
            animation: pulse-dot 2.5s infinite;
        }}
        @keyframes pulse-dot {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.5; transform: scale(0.85); }}
        }}
        .status-text-main {{
            color: var(--text-primary);
            font-weight: 600;
        }}
        .status-sep {{
            color: var(--text-muted);
        }}
        .status-last-run {{
            color: var(--text-secondary);
            font-family: var(--font-mono, monospace);
            font-size: 12px;
        }}
        .btn-run-pipeline {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.18);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.5px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35);
        }}
        .btn-run-pipeline:hover {{
            background: linear-gradient(135deg, #1d4ed8, #1e40af);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.45);
        }}
        .btn-run-pipeline:active {{
            transform: translateY(0);
        }}
        .btn-run-pipeline .run-icon {{
            font-size: 10px;
        }}

        /* Temporary Pipeline Run Screen (Modal) */
        .run-modal-backdrop {{
            position: fixed;
            inset: 0;
            background: rgba(10, 15, 29, 0.85);
            backdrop-filter: blur(10px);
            z-index: 5000;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .run-modal-card {{
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 16px;
            box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.85);
            width: 100%;
            max-width: 780px;
            max-height: 90vh;
            overflow-y: auto;
            padding: 32px;
            color: #f8fafc;
            animation: modalFadeIn 0.25s ease-out;
        }}
        @keyframes modalFadeIn {{
            from {{ opacity: 0; transform: scale(0.97) translateY(8px); }}
            to {{ opacity: 1; transform: scale(1) translateY(0); }}
        }}
        .run-modal-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 22px;
        }}
        .run-spinner-ring {{
            width: 32px;
            height: 32px;
            border: 3px solid rgba(59, 130, 246, 0.2);
            border-top-color: #3b82f6;
            border-radius: 50%;
            animation: run-spin 1s linear infinite;
        }}
        @keyframes run-spin {{
            to {{ transform: rotate(360deg); }}
        }}
        .run-modal-title {{
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: #f8fafc;
            margin: 0;
        }}
        .run-modal-subtitle {{
            font-size: 13px;
            color: #94a3b8;
            margin-top: 4px;
        }}

        /* Master progress */
        .master-progress-section {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 20px;
        }}
        .master-progress-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 14px;
            font-weight: 600;
            color: #e2e8f0;
            margin-bottom: 10px;
        }}
        .master-progress-track {{
            height: 14px;
            background: #0f172a;
            border-radius: 7px;
            overflow: hidden;
            border: 1px solid #334155;
        }}
        .master-progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #06b6d4, #10b981);
            border-radius: 7px;
            transition: width 0.35s ease;
        }}
        .progress-pct {{
            font-family: var(--font-mono, monospace);
            color: #38bdf8;
            font-weight: 700;
        }}

        /* Checklist */
        .run-checklist-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 10px;
            margin-bottom: 20px;
        }}
        .run-check-item {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 13px;
            font-weight: 500;
            color: #94a3b8;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: all 0.2s ease;
        }}
        .run-check-item.active {{
            color: #38bdf8;
            border-color: #38bdf8;
            background: rgba(56, 189, 248, 0.08);
        }}
        .run-check-item.done {{
            color: #34d399;
            border-color: rgba(52, 211, 153, 0.4);
            background: rgba(52, 211, 153, 0.06);
        }}
        .check-icon {{
            font-weight: 700;
        }}

        /* Live Callout */
        .run-status-callout {{
            background: rgba(30, 41, 59, 0.9);
            border-left: 4px solid #38bdf8;
            border-radius: 0 8px 8px 0;
            padding: 12px 16px;
            font-family: var(--font-mono, monospace);
            font-size: 13px;
            color: #7dd3fc;
            margin-bottom: 20px;
        }}

        /* Informative Multi-Stage Details */
        .run-details-scrollable {{
            display: flex;
            flex-direction: column;
            gap: 14px;
            max-height: 380px;
            overflow-y: auto;
            padding-right: 4px;
        }}
        .stage-detail-box {{
            background: #162032;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 14px 18px;
        }}
        .stage-detail-title {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 8px;
        }}
        .badge-sub-count {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 6px;
            background: #1e293b;
            color: #94a3b8;
            font-family: var(--font-mono, monospace);
        }}
        .stage-source-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }}
        .source-chip {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 12px;
            color: #cbd5e1;
        }}
        .source-chip.done {{
            border-color: rgba(52, 211, 153, 0.4);
            color: #34d399;
        }}
        .stage-dedupe-lines {{
            font-size: 12px;
            color: #94a3b8;
            display: flex;
            flex-direction: column;
            gap: 4px;
            margin-top: 6px;
        }}
        .dedupe-line.highlight {{
            color: #38bdf8;
            font-weight: 700;
        }}
        .mini-progress-track {{
            height: 8px;
            background: #0f172a;
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid #334155;
            margin: 8px 0;
        }}
        .mini-progress-fill {{
            height: 100%;
            background: #3b82f6;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}
        .mini-progress-fill.green {{
            background: #10b981;
        }}
        .stage-counts-row {{
            display: flex;
            gap: 12px;
            margin-top: 6px;
        }}
        .count-badge {{
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 6px;
            font-weight: 600;
        }}
        .count-badge.green {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .count-badge.red {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .count-badge.amber {{ background: rgba(245, 158, 11, 0.15); color: #fde047; border: 1px solid rgba(245, 158, 11, 0.3); }}

        .final-check-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            font-size: 12px;
            color: #94a3b8;
            margin-top: 6px;
        }}
        .final-item.done {{
            color: #34d399;
            font-weight: 600;
        }}

        /* Completion View */
        .complete-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 22px;
        }}
        .complete-celebration-badge {{
            font-size: 32px;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 50%;
            width: 54px;
            height: 54px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .complete-title {{
            font-size: 22px;
            font-weight: 800;
            color: #f8fafc;
            margin: 0;
            letter-spacing: 0.5px;
        }}
        .complete-subtitle {{
            font-size: 14px;
            color: #94a3b8;
            margin-top: 4px;
        }}
        .complete-metrics-wrap {{
            margin-bottom: 22px;
        }}
        .complete-summary-table {{
            width: 100%;
            border-collapse: collapse;
            background: #162032;
            border: 1px solid #334155;
            border-radius: 10px;
            overflow: hidden;
            font-size: 14px;
        }}
        .complete-summary-table td {{
            padding: 12px 18px;
            border-bottom: 1px solid #1e293b;
            color: #cbd5e1;
        }}
        .complete-summary-table tr:last-child td {{
            border-bottom: none;
        }}
        .complete-summary-table .metric-num {{
            text-align: right;
            font-family: var(--font-mono, monospace);
            font-weight: 700;
            font-size: 15px;
        }}
        .complete-summary-table .highlight-row td {{
            background: rgba(16, 185, 129, 0.08);
            font-weight: 700;
        }}
        .text-green {{ color: #34d399 !important; }}
        .text-blue {{ color: #38bdf8 !important; }}
        .text-amber {{ color: #fbbf24 !important; }}

        .complete-domain-section {{
            margin-bottom: 20px;
        }}
        .domain-sec-title {{
            font-size: 12px;
            font-weight: 700;
            color: #94a3b8;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }}
        .domain-pills-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 10px;
        }}
        .domain-pill-card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .domain-name {{
            font-size: 13px;
            font-weight: 600;
            color: #e2e8f0;
        }}
        .domain-val {{
            font-family: var(--font-mono, monospace);
            font-weight: 700;
            color: #38bdf8;
            background: rgba(56, 189, 248, 0.15);
            padding: 2px 8px;
            border-radius: 6px;
        }}

        .queue-impact-card {{
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.15), rgba(16, 185, 129, 0.15));
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 10px;
            padding: 14px 18px;
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 24px;
        }}
        .impact-icon {{
            font-size: 24px;
        }}
        .impact-title {{
            font-size: 15px;
            font-weight: 700;
            color: #f8fafc;
        }}
        .impact-sub {{
            font-size: 12px;
            color: #94a3b8;
            margin-top: 2px;
        }}

        .complete-actions-bar {{
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }}
        .btn-view-new-jobs {{
            background: linear-gradient(135deg, #10b981, #059669);
            color: #ffffff;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
        }}
        .btn-view-new-jobs:hover {{
            background: linear-gradient(135deg, #059669, #047857);
            transform: translateY(-1px);
        }}
        .btn-close-runner {{
            background: #1e293b;
            color: #cbd5e1;
            border: 1px solid #475569;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn-close-runner:hover {{
            background: #334155;
            color: #f8fafc;
        }}

        /* Top Metric Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }}
        .stat-card::before {{
            content: "";
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: var(--accent-primary);
        }}
        .stat-card.card-green::before {{ background: var(--accent-green); }}
        .stat-card.card-purple::before {{ background: var(--accent-purple); }}
        .stat-card.card-amber::before {{ background: var(--accent-amber); }}

        .stat-label {{
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.6px;
        }}
        .stat-value {{
            font-size: 30px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 6px;
        }}
        .stat-sub {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        /* Navigation Tabs */
        .nav-tabs {{
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 24px;
            overflow-x: auto;
        }}
        .nav-tab-btn {{
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 15px;
            font-weight: 600;
            padding: 12px 20px;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
        }}
        .nav-tab-btn:hover {{
            color: var(--text-primary);
        }}
        .nav-tab-btn.active {{
            color: var(--accent-primary);
            border-bottom-color: var(--accent-primary);
        }}
        .tab-count-badge {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 9999px;
            font-weight: 700;
        }}
        .nav-tab-btn.active .tab-count-badge {{
            background: var(--accent-primary);
            color: #ffffff;
            border-color: var(--accent-primary);
        }}

        /* Action Queue (Tab 1) Styles */
        .section-intro-bar {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 14px 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .section-intro-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--text-primary);
        }}
        .section-intro-sub {{
            font-size: 13px;
            color: var(--text-secondary);
        }}
        .action-counter-pill {{
            background: rgba(139, 92, 246, 0.15);
            color: #c084fc;
            border: 1px solid rgba(139, 92, 246, 0.3);
            font-size: 13px;
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 8px;
        }}

        .filter-controls-bar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 14px;
            margin-bottom: 20px;
        }}
        .filter-btn-group {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            background: var(--surface-color);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .filter-btn:hover {{
            color: var(--text-primary);
            border-color: var(--border-light);
        }}
        .filter-btn.active {{
            background: var(--accent-primary);
            color: #ffffff;
            border-color: var(--accent-primary);
        }}
        .search-input-wrap {{
            flex: 1;
            min-width: 250px;
            max-width: 380px;
        }}
        .search-box-input {{
            width: 100%;
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 14px;
            color: var(--text-primary);
            font-size: 14px;
        }}
        .search-box-input:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}

        /* Job Cards */
        .jobs-list {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        .job-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 22px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }}
        .job-card.vanishing {{
            opacity: 0;
            transform: translateX(-40px) scale(0.95);
            max-height: 0;
            padding: 0;
            margin: 0;
            border: none;
            overflow: hidden;
        }}
        .job-card:hover {{
            border-color: #3b4d6b;
            box-shadow: 0 6px 24px rgba(0, 0, 0, 0.3);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .company-badge-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 4px;
        }}
        .company-badge {{
            font-size: 13px;
            font-weight: 700;
            color: var(--accent-primary);
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }}
        .freshness-badge {{
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 9999px;
            display: inline-flex;
            align-items: gap: 4px;
        }}
        .fresh-today, .fresh-recent {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}
        .fresh-week {{
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}
        .fresh-two-weeks {{
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}
        .fresh-older {{
            background: rgba(148, 163, 184, 0.15);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }}

        .job-title {{
            font-size: 20px;
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
            padding: 5px 11px;
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
            padding: 5px 11px;
            border-radius: 6px;
        }}
        .badge-prepared {{
            background: rgba(139, 92, 246, 0.15);
            color: #c084fc;
            border: 1px solid rgba(139, 92, 246, 0.3);
        }}

        /* Meta bar */
        .card-meta-bar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            background: var(--surface-color);
            border-radius: 10px;
            padding: 12px 16px;
            margin: 16px 0;
            font-size: 13px;
        }}
        .track-tag, .cv-tag {{
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            padding: 3px 10px;
            border-radius: 6px;
            color: var(--text-primary);
            font-weight: 600;
        }}
        .meta-item-actions {{
            display: flex;
            gap: 10px;
        }}

        /* Buttons */
        .btn {{
            font-size: 13px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 7px;
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
        .btn-copy {{
            background: var(--surface-color);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }}
        .btn-copy:hover {{
            background: var(--surface-hover);
        }}
        .btn-secondary-sm {{
            background: var(--surface-color);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            font-size: 12px;
            padding: 5px 10px;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        .btn-secondary-sm:hover {{
            background: var(--surface-hover);
        }}
        .btn-primary-sm {{
            background: var(--accent-primary);
            color: #ffffff;
            font-size: 12px;
            padding: 5px 12px;
            border-radius: 6px;
            cursor: pointer;
            border: none;
        }}
        .btn-primary-sm:hover {{
            background: var(--accent-primary-hover);
        }}
        .btn-success-sm {{
            background: var(--accent-green);
            color: #ffffff;
            font-size: 12px;
            padding: 5px 12px;
            border-radius: 6px;
            cursor: pointer;
            border: none;
        }}
        .btn-success-sm:hover {{
            background: var(--accent-green-hover);
        }}

        /* Insights & 3-Tier Skill Gaps */
        .card-insights {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 16px;
        }}
        @media (max-width: 800px) {{
            .card-insights {{ grid-template-columns: 1fr; }}
        }}
        .insight-col {{
            background: rgba(11, 17, 32, 0.7);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px 16px;
        }}
        .insight-title {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            margin-bottom: 8px;
            color: var(--text-secondary);
        }}
        .insight-list {{
            list-style: none;
            font-size: 13px;
        }}
        .strengths-list li {{
            margin-bottom: 6px;
            position: relative;
            padding-left: 16px;
            color: var(--text-primary);
        }}
        .strengths-list li::before {{
            content: "•";
            color: var(--accent-green);
            position: absolute;
            left: 0;
            font-weight: bold;
        }}

        .gap-item {{
            margin-bottom: 8px;
            line-height: 1.4;
            color: #cbd5e1;
        }}
        .gap-pill {{
            font-size: 10px;
            font-weight: 800;
            padding: 2px 7px;
            border-radius: 4px;
            letter-spacing: 0.5px;
            display: inline-block;
            margin-right: 6px;
            text-transform: uppercase;
        }}
        .tier-missing {{
            background: rgba(239, 68, 68, 0.2);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }}
        .tier-partial {{
            background: rgba(245, 158, 11, 0.2);
            color: #fde047;
            border: 1px solid rgba(245, 158, 11, 0.4);
        }}
        .tier-strategic {{
            background: rgba(139, 92, 246, 0.2);
            color: #c4b5fd;
            border: 1px solid rgba(139, 92, 246, 0.4);
        }}
        .gap-name {{
            color: #f1f5f9;
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
            padding: 8px 0;
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
            background: #070c18;
            color: #e2e8f0;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 14px;
            font-family: var(--font-family);
            font-size: 13px;
            line-height: 1.6;
            resize: vertical;
        }}

        /* Application Pipeline (Tab 2) Styles */
        .pipeline-stage-boxes {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
            margin-bottom: 22px;
        }}
        .stage-box {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px 14px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .stage-box:hover, .stage-box.active {{
            border-color: var(--accent-primary);
            background: var(--surface-hover);
        }}
        .stage-box.active {{
            border-bottom: 3px solid var(--accent-primary);
        }}
        .stage-box-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-secondary);
            letter-spacing: 0.5px;
        }}
        .stage-box-val {{
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 2px;
        }}

        .filter-grid-bar {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 10px;
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 18px;
        }}
        .filter-control-cell label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }}
        .filter-select, .filter-input {{
            width: 100%;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 6px 10px;
            color: var(--text-primary);
            font-size: 13px;
        }}
        .filter-select:focus, .filter-input:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}

        .table-responsive-wrap {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow-x: auto;
            margin-bottom: 16px;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}
        .data-table th {{
            background: var(--surface-color);
            color: var(--text-secondary);
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
        }}
        .data-table td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}
        .data-table tr:hover td {{
            background: var(--surface-hover);
        }}

        /* Stage Badges */
        .stage-pill {{
            font-size: 11px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            letter-spacing: 0.5px;
            display: inline-block;
            text-transform: uppercase;
        }}
        .stage-applied {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .stage-screening {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
        .stage-interview, .stage-interviewing {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }}
        .stage-offered, .stage-offer {{ background: rgba(245, 158, 11, 0.2); color: #fde047; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .stage-rejected {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .stage-withdrawn {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }}
        .stage-prepared {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }}
        .stage-discovered {{ background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3); }}

        /* Action Cell in Pipeline Table */
        .pipe-table-actions {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }}
        .stage-dropdown-mini {{
            background: var(--bg-color);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 4px 6px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
        }}
        .stage-dropdown-mini:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}

        /* Pagination Bar */
        .pagination-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            font-size: 13px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .pagination-info {{
            color: var(--text-secondary);
        }}
        .pagination-btns {{
            display: flex;
            gap: 6px;
            align-items: center;
        }}
        .page-btn {{
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 5px 11px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }}
        .page-btn:hover {{
            background: var(--surface-hover);
        }}
        .page-btn.active {{
            background: var(--accent-primary);
            color: #ffffff;
            border-color: var(--accent-primary);
        }}
        .page-btn:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}

        /* Application Details Modal / Drawer */
        .modal-overlay {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 2000;
            backdrop-filter: blur(4px);
            padding: 20px;
        }}
        .modal-overlay.open {{
            display: flex;
        }}
        .modal-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            width: 100%;
            max-width: 820px;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
            overflow: hidden;
        }}
        .modal-header {{
            padding: 18px 22px;
            border-bottom: 1px solid var(--border-color);
            background: var(--surface-color);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}
        .modal-header h3 {{
            font-size: 19px;
            font-weight: 700;
            color: var(--text-primary);
        }}
        .modal-header p {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 2px;
        }}
        .modal-close-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 24px;
            cursor: pointer;
            line-height: 1;
        }}
        .modal-close-btn:hover {{
            color: var(--text-primary);
        }}
        .modal-body {{
            padding: 22px;
            overflow-y: auto;
            flex: 1;
        }}
        .modal-section-title {{
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            color: var(--text-secondary);
            margin-bottom: 10px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 4px;
        }}

        /* Timeline in Modal */
        .timeline-wrap {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--surface-color);
            padding: 14px 18px;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow-x: auto;
            gap: 12px;
        }}
        .timeline-step {{
            text-align: center;
            position: relative;
            flex: 1;
        }}
        .timeline-dot {{
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: var(--border-color);
            margin: 0 auto 6px auto;
        }}
        .timeline-step.active .timeline-dot {{
            background: var(--accent-primary);
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.6);
        }}
        .timeline-step.passed .timeline-dot {{
            background: var(--accent-green);
        }}
        .timeline-label {{
            font-size: 11px;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
        }}
        .timeline-step.active .timeline-label {{
            color: var(--accent-primary);
        }}

        /* Notes CRM Fields */
        .notes-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
            margin-bottom: 16px;
        }}
        @media (max-width: 600px) {{
            .notes-grid {{ grid-template-columns: 1fr; }}
        }}
        .notes-field-group label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }}
        .notes-input {{
            width: 100%;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 8px 12px;
            color: var(--text-primary);
            font-size: 13px;
        }}
        .notes-textarea {{
            width: 100%;
            height: 90px;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 8px 12px;
            color: var(--text-primary);
            font-size: 13px;
            resize: vertical;
            line-height: 1.5;
        }}
        .notes-input:focus, .notes-textarea:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}
        .modal-footer {{
            padding: 14px 22px;
            background: var(--surface-color);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }}

        /* Market Intelligence (Tab 4) Styles */
        .market-split-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }}
        @media (max-width: 900px) {{
            .market-split-grid {{ grid-template-columns: 1fr; }}
        }}
        .market-box {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 22px;
        }}
        .market-box h3 {{
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 6px;
        }}
        .market-box-sub {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 20px;
        }}

        /* Momentum Bars */
        .momentum-list {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .momentum-item {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px 16px;
        }}
        .momentum-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        .momentum-domain {{
            font-size: 14px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: 0.5px;
        }}
        .trend-tag {{
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            letter-spacing: 0.5px;
        }}
        .trend-high {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
        .trend-growing {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .trend-stable {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; }}

        .momentum-bar-wrap {{
            height: 10px;
            background: var(--bg-color);
            border-radius: 5px;
            overflow: hidden;
            margin-bottom: 8px;
        }}
        .momentum-bar-fill {{
            height: 100%;
            border-radius: 5px;
        }}
        .momentum-bar-fill.trend-high {{ background: linear-gradient(90deg, #ef4444, #f97316); }}
        .momentum-bar-fill.trend-growing {{ background: linear-gradient(90deg, #10b981, #06b6d4); }}
        .momentum-bar-fill.trend-stable {{ background: linear-gradient(90deg, #3b82f6, #8b5cf6); }}
        .momentum-desc {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* Skill Position Table */
        .skill-pos-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .skill-pos-table th {{
            background: var(--surface-card);
            padding: 10px 12px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border-color);
            text-align: left;
        }}
        .skill-pos-table td {{
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}
        .col-skill .sub-domain {{
            display: block;
            font-size: 10px;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        .meter-pair {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .meter-bar-wrap {{
            flex: 1;
            height: 8px;
            background: var(--bg-color);
            border-radius: 4px;
            overflow: hidden;
            min-width: 70px;
        }}
        .meter-fill {{ height: 100%; border-radius: 4px; }}
        .market-fill {{ background: var(--accent-primary); }}
        .candidate-fill {{ background: var(--accent-green); }}
        .meter-pct {{
            font-size: 11px;
            font-weight: 700;
            color: var(--text-secondary);
            width: 32px;
        }}
        .action-pill {{
            font-size: 11px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            letter-spacing: 0.5px;
            display: inline-block;
            text-transform: uppercase;
        }}
        .action-maintain {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .action-build {{ background: rgba(245, 158, 11, 0.2); color: #fde047; }}
        .action-explore {{ background: rgba(139, 92, 246, 0.2); color: #c4b5fd; }}
        .action-learn {{ background: rgba(6, 182, 212, 0.2); color: #67e8f9; }}
        .col-notes {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* ROI Blueprint Cards */
        .roi-cards-list {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}
        .roi-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px;
        }}
        .roi-card-header {{
            display: flex;
            align-items: center;
            gap: 12px;
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
        .skill-cat-pill {{
            font-size: 10px;
            color: var(--text-muted);
            text-transform: uppercase;
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
            margin-bottom: 8px;
        }}
        .roi-recommendation {{
            font-size: 12px;
            color: #cbd5e1;
            background: #090e1a;
            padding: 10px 12px;
            border-radius: 6px;
            border-left: 3px solid var(--accent-primary);
            line-height: 1.5;
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
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.3s;
            pointer-events: none;
            z-index: 3000;
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
                <h1>AI Job Agent — Daily Intelligence Report & Application Pipeline</h1>
                <p>Negar Najafi • MSc Telecommunications Engineering (Politecnico di Milano) • Milan, Italy • Europe Focus</p>
            </div>
            <div class="header-runner-panel">
                <div class="header-status-line">
                    <span class="status-indicator-dot"></span>
                    <span class="status-text-main" id="header-status-text">Up to date</span>
                    <span class="status-sep">·</span>
                    <span class="status-last-run" id="header-last-run">Last run: {last_run_display}</span>
                </div>
                <button class="btn-run-pipeline" id="btn-run-pipeline" onclick="openPipelineRunModal()">
                    <span class="run-icon">▶</span> RUN PIPELINE
                </button>
            </div>
        </header>

        <!-- Top Overall Statistics -->
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">Action Queue</span>
                <span class="stat-value" id="top-action-count">{action_count}</span>
                <span class="stat-sub">{high_count} High Priority • {med_count} Medium</span>
            </div>
            <div class="stat-card card-green">
                <span class="stat-label">Active Applications</span>
                <span class="stat-value" id="top-pipeline-count">{active_pipe_count}</span>
                <span class="stat-sub">{pipeline_summary.get('applied', 0)} Applied • {pipeline_summary.get('screening', 0)} Screening • {pipeline_summary.get('interview', 0)} Interview</span>
            </div>
            <div class="stat-card card-purple">
                <span class="stat-label">Job Database</span>
                <span class="stat-value">{total_db_count}</span>
                <span class="stat-sub">Ingested European Tech Roles</span>
            </div>
            <div class="stat-card card-amber">
                <span class="stat-label">Target Markets</span>
                <span class="stat-value">6 Domains</span>
                <span class="stat-sub">Network Security • Telecom AI • SRE</span>
            </div>
        </div>

        <!-- 4-Tab Navigation -->
        <div class="nav-tabs">
            <button class="nav-tab-btn active" id="tab-btn-applications" onclick="switchNavTab('applications')">
                📋 Applications (Action Queue)
                <span class="tab-count-badge" id="badge-applications-count">{action_count}</span>
            </button>
            <button class="nav-tab-btn" id="tab-btn-pipeline" onclick="switchNavTab('pipeline')">
                🚀 Application Pipeline (Tracker)
                <span class="tab-count-badge" id="badge-pipeline-count">{len(pipeline_jobs)}</span>
            </button>
            <button class="nav-tab-btn" id="tab-btn-database" onclick="switchNavTab('database')">
                🗄️ Job Database Archive
                <span class="tab-count-badge">{total_db_count}</span>
            </button>
            <button class="nav-tab-btn" id="tab-btn-market" onclick="switchNavTab('market')">
                📈 Market Intelligence
                <span class="tab-count-badge">{len(market.get('candidate_skill_position', []))}</span>
            </button>
        </div>

        <!-- ======================================================== -->
        <!-- TAB 1: APPLICATIONS (ACTION QUEUE)                      -->
        <!-- ======================================================== -->
        <div id="tab-applications" class="tab-content">
            <div class="section-intro-bar">
                <div>
                    <div class="section-intro-title">Action Queue: Prepared Applications Ready to Submit</div>
                    <div class="section-intro-sub">
                        Contains only top vetted jobs requiring your action. Clicking <strong>[✓ Mark as Applied]</strong> moves the job directly into your active Application Pipeline.
                    </div>
                </div>
                <div class="action-counter-pill" id="action-queue-summary-pill">
                    {action_count} Prepared • {high_count} High Priority • {med_count} Medium
                </div>
            </div>

            <div class="filter-controls-bar">
                <div class="filter-btn-group">
                    <button class="filter-btn active" onclick="filterActionJobs('all', this)">All Ready ({action_count})</button>
                    <button class="filter-btn" onclick="filterActionJobs('high', this)">High Priority ({high_count})</button>
                    <button class="filter-btn" onclick="filterActionJobs('medium', this)">Medium Priority ({med_count})</button>
                    <button class="filter-btn" onclick="filterActionJobs('telecom ai', this)">Telecom AI</button>
                    <button class="filter-btn" onclick="filterActionJobs('network security', this)">Network Security</button>
                </div>
                <div class="search-input-wrap">
                    <input type="text" class="search-box-input" id="action-search-input" placeholder="Search company, title, or city..." oninput="handleActionSearch()">
                </div>
            </div>

            <div class="jobs-list" id="action-jobs-container">
                {"".join(action_cards_html) if action_cards_html else '<div class="empty-state" style="text-align:center; padding:40px; color:var(--text-secondary);">No jobs remaining in action queue. Great job applying!</div>'}
            </div>
        </div>

        <!-- ======================================================== -->
        <!-- TAB 2: APPLICATION PIPELINE (TRACKER - ONLY APPLIED)     -->
        <!-- ======================================================== -->
        <div id="tab-pipeline" class="tab-content" style="display: none;">
            <div class="section-intro-bar">
                <div>
                    <div class="section-intro-title">Application Pipeline Tracker</div>
                    <div class="section-intro-sub">
                        Real-time tracking of jobs you have submitted. Advance applications from Applied to Screening, Interview, and Offer stages.
                    </div>
                </div>
            </div>

            <!-- Top Stage Counters (Click to Filter Table!) -->
            <div class="pipeline-stage-boxes">
                <div class="stage-box active" id="sbox-all-active" onclick="filterPipelineStage('all_active', this)">
                    <div class="stage-box-title">ALL ACTIVE</div>
                    <div class="stage-box-val" id="cnt-pipe-active">{pipeline_summary.get('all_active', 0)}</div>
                </div>
                <div class="stage-box" id="sbox-applied" onclick="filterPipelineStage('applied', this)">
                    <div class="stage-box-title">APPLIED</div>
                    <div class="stage-box-val" id="cnt-pipe-applied">{pipeline_summary.get('applied', 0)}</div>
                </div>
                <div class="stage-box" id="sbox-screening" onclick="filterPipelineStage('screening', this)">
                    <div class="stage-box-title">SCREENING</div>
                    <div class="stage-box-val" id="cnt-pipe-screening">{pipeline_summary.get('screening', 0)}</div>
                </div>
                <div class="stage-box" id="sbox-interview" onclick="filterPipelineStage('interview', this)">
                    <div class="stage-box-title">INTERVIEW</div>
                    <div class="stage-box-val" id="cnt-pipe-interview">{pipeline_summary.get('interview', 0)}</div>
                </div>
                <div class="stage-box" id="sbox-offered" onclick="filterPipelineStage('offered', this)">
                    <div class="stage-box-title">OFFERS</div>
                    <div class="stage-box-val" id="cnt-pipe-offered">{pipeline_summary.get('offered', 0)}</div>
                </div>
                <div class="stage-box" id="sbox-rejected" onclick="filterPipelineStage('rejected', this)">
                    <div class="stage-box-title">REJECTED</div>
                    <div class="stage-box-val" id="cnt-pipe-rejected">{pipeline_summary.get('rejected', 0)}</div>
                </div>
                <div class="stage-box" id="sbox-withdrawn" onclick="filterPipelineStage('withdrawn', this)">
                    <div class="stage-box-title">WITHDRAWN</div>
                    <div class="stage-box-val" id="cnt-pipe-withdrawn">{pipeline_summary.get('withdrawn', 0)}</div>
                </div>
            </div>

            <!-- Pipeline Filter Bar -->
            <div class="filter-grid-bar">
                <div class="filter-control-cell">
                    <label>Search Applications</label>
                    <input type="text" class="filter-input" id="pipe-search" placeholder="Company, title, city..." oninput="filterPipelineTable()">
                </div>
                <div class="filter-control-cell">
                    <label>Stage</label>
                    <select class="filter-select" id="pipe-filter-stage" onchange="filterPipelineTable()">
                        <option value="all_active">All Active (Applied, Screen, Interview, Offer)</option>
                        <option value="all">All Applications (Including Exits)</option>
                        <option value="applied">Applied</option>
                        <option value="screening">Screening</option>
                        <option value="interview">Interview</option>
                        <option value="offered">Offered 🎉</option>
                        <option value="rejected">Rejected</option>
                        <option value="withdrawn">Withdrawn</option>
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Company</label>
                    <select class="filter-select" id="pipe-filter-company" onchange="filterPipelineTable()">
                        <option value="all">All Companies</option>
                        {"".join(f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in pipe_companies)}
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Career Track</label>
                    <select class="filter-select" id="pipe-filter-track" onchange="filterPipelineTable()">
                        <option value="all">All Tracks</option>
                        {"".join(f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in pipe_tracks)}
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Priority</label>
                    <select class="filter-select" id="pipe-filter-priority" onchange="filterPipelineTable()">
                        <option value="all">All Priorities</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                    </select>
                </div>
                <div class="filter-control-cell" style="max-width: 120px;">
                    <label>Per Page</label>
                    <select class="filter-select" id="pipe-page-size" onchange="changePipePageSize(this.value)">
                        <option value="25">25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                </div>
            </div>

            <!-- Pipeline Paginated Table -->
            <div class="table-responsive-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 50px;">ID</th>
                            <th>Company</th>
                            <th>Job Title</th>
                            <th>Location</th>
                            <th>Track</th>
                            <th>Match</th>
                            <th>Priority</th>
                            <th>Stage</th>
                            <th>Applied</th>
                            <th>Next Action</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody id="pipe-table-body">
                        <!-- Populated dynamically by JavaScript -->
                    </tbody>
                </table>
            </div>

            <!-- Pipeline Pagination Bar -->
            <div class="pagination-bar">
                <div class="pagination-info" id="pipe-pagination-info">Showing 1–25 applications</div>
                <div class="pagination-btns" id="pipe-pagination-controls">
                    <!-- Populated dynamically by JavaScript -->
                </div>
            </div>
        </div>

        <!-- ======================================================== -->
        <!-- TAB 3: COMPLETE JOB DATABASE ARCHIVE                     -->
        <!-- ======================================================== -->
        <div id="tab-database" class="tab-content" style="display: none;">
            <div class="section-intro-bar">
                <div>
                    <div class="section-intro-title">Complete Job Database Archive ({total_db_count} Jobs)</div>
                    <div class="section-intro-sub">
                        Master archive of every job collected by the AI across European sources. Cleanly paginated for high-volume historical scale.
                    </div>
                </div>
            </div>

            <!-- Database Filters Grid -->
            <div class="filter-grid-bar">
                <div class="filter-control-cell">
                    <label>Search Keyword</label>
                    <input type="text" class="filter-input" id="db-search" placeholder="Company, title, skill..." oninput="filterDatabaseTable()">
                </div>
                <div class="filter-control-cell">
                    <label>Status</label>
                    <select class="filter-select" id="db-filter-status" onchange="filterDatabaseTable()">
                        <option value="all">All Statuses</option>
                        <option value="prepared">Prepared (Ready in Queue)</option>
                        <option value="applied">Applied</option>
                        <option value="screening">Screening</option>
                        <option value="interview">Interview</option>
                        <option value="offered">Offered</option>
                        <option value="rejected">Rejected</option>
                        <option value="discovered">Discovered (Unscreened)</option>
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Company</label>
                    <select class="filter-select" id="db-filter-company" onchange="filterDatabaseTable()">
                        <option value="all">All Companies</option>
                        {"".join(f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in companies_db)}
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Career Track</label>
                    <select class="filter-select" id="db-filter-track" onchange="filterDatabaseTable()">
                        <option value="all">All Tracks</option>
                        {"".join(f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in tracks_db)}
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Priority</label>
                    <select class="filter-select" id="db-filter-priority" onchange="filterDatabaseTable()">
                        <option value="all">All Priorities</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                        <option value="none">None</option>
                    </select>
                </div>
                <div class="filter-control-cell">
                    <label>Source</label>
                    <select class="filter-select" id="db-filter-source" onchange="filterDatabaseTable()">
                        <option value="all">All Sources</option>
                        {"".join(f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in sources_db)}
                    </select>
                </div>
                <div class="filter-control-cell" style="max-width: 120px;">
                    <label>Per Page</label>
                    <select class="filter-select" id="db-page-size" onchange="changeDbPageSize(this.value)">
                        <option value="25">25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                </div>
            </div>

            <!-- Database Table -->
            <div class="table-responsive-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 50px;">ID</th>
                            <th>Company</th>
                            <th>Job Title</th>
                            <th>Location</th>
                            <th>Track</th>
                            <th>Score</th>
                            <th>Priority</th>
                            <th>Status</th>
                            <th>Freshness</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="db-table-body">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>
            </div>

            <!-- Database Pagination Bar -->
            <div class="pagination-bar">
                <div class="pagination-info" id="db-pagination-info">Showing 1–25 of {total_db_count} jobs</div>
                <div class="pagination-btns" id="db-pagination-controls">
                    <!-- Populated by JavaScript -->
                </div>
            </div>
        </div>

        <!-- ======================================================== -->
        <!-- TAB 4: REDESIGNED MARKET INTELLIGENCE                    -->
        <!-- ======================================================== -->
        <div id="tab-market" class="tab-content" style="display: none;">
            <div class="market-split-grid">
                <!-- Left: Where Your Target Market Is Moving -->
                <div class="market-box">
                    <h3>🚀 Where Your Target Market Is Moving</h3>
                    <p class="market-box-sub">
                        Domain momentum tracking across European engineering job postings.
                    </p>
                    <div class="momentum-list">
                        {"".join(domain_momentum_rows)}
                    </div>
                </div>

                <!-- Right: High ROI Skills to Add -->
                <div class="market-box">
                    <h3>💡 High-ROI Skills to Add to Your Profile</h3>
                    <p class="market-box-sub">
                        Technologies appearing most frequently across shortlisted roles with practical demonstration blueprints:
                    </p>
                    <div class="roi-cards-list">
                        {"".join(high_roi_cards)}
                    </div>
                </div>
            </div>

            <!-- Bottom: Your Skill Position Comparative Matrix -->
            <div class="market-box" style="margin-top: 24px;">
                <h3>🎯 Your Skill Position (Market Demand vs. Profile Proficiency)</h3>
                <p class="market-box-sub">
                    Direct side-by-side comparison of market demand in European opportunities versus your verified engineering background:
                </p>
                <div style="overflow-x: auto;">
                    <table class="skill-pos-table">
                        <thead>
                            <tr>
                                <th>Skill / Technology</th>
                                <th style="width: 180px;">Market Demand</th>
                                <th style="width: 180px;">Your Proficiency</th>
                                <th>Strategic Action</th>
                                <th>Context & Strategic Blueprint</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(skill_position_rows)}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Application Details & Notes Modal / Drawer -->
    <div class="modal-overlay" id="app-modal" onclick="closeModalOnOverlay(event)">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h3 id="modal-title">Job Title</h3>
                    <p id="modal-sub">Company • Location • Track</p>
                </div>
                <button class="modal-close-btn" onclick="closeModal()">×</button>
            </div>
            <div class="modal-body">
                <!-- Timeline -->
                <div class="modal-section-title">Application Timeline</div>
                <div class="timeline-wrap" id="modal-timeline">
                    <!-- Populated dynamically -->
                </div>

                <!-- Notes & Recruiter CRM -->
                <div class="modal-section-title">Recruiter Contact & Interview Notes</div>
                <div class="notes-grid">
                    <div class="notes-field-group">
                        <label>Recruiter / Point of Contact</label>
                        <input type="text" class="notes-input" id="modal-notes-recruiter" placeholder="Name, Email, or LinkedIn URL">
                    </div>
                    <div class="notes-field-group">
                        <label>Target Compensation / Salary</label>
                        <input type="text" class="notes-input" id="modal-notes-salary" placeholder="e.g. €75,000 - €85,000 + equity">
                    </div>
                    <div class="notes-field-group">
                        <label>Next Follow-Up Date</label>
                        <input type="date" class="notes-input" id="modal-notes-followup">
                    </div>
                    <div class="notes-field-group">
                        <label>Careers Portal URL</label>
                        <input type="text" class="notes-input" id="modal-notes-url" readonly>
                    </div>
                </div>

                <div class="notes-field-group" style="margin-bottom: 20px;">
                    <label>Interview Notes, Technical Questions & Feedback</label>
                    <textarea class="notes-textarea" id="modal-notes-text" placeholder="Record interview feedback, topics discussed, architecture questions..."></textarea>
                </div>

                <!-- Cover Letter Used -->
                <div class="modal-section-title" style="display: flex; justify-content: space-between; align-items: center;">
                    <span>Submitted Cover Letter Package</span>
                    <button class="btn btn-secondary-sm" onclick="copyModalLetter()">📋 Copy Letter</button>
                </div>
                <textarea class="letter-textarea" id="modal-letter-text" readonly style="height: 180px;"></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn btn-copy" onclick="closeModal()">Close</button>
                <button class="btn btn-applied" id="modal-btn-save" onclick="saveModalNotes()">💾 Save Notes</button>
            </div>
        </div>
    </div>

    <!-- Temporary Pipeline Run Screen (Modal) -->
    <div id="pipeline-run-modal" class="run-modal-backdrop" style="display: none;">
        <div class="run-modal-card">
            
            <!-- STATE A: RUNNING VIEW -->
            <div id="pipe-run-progress-view">
                <div class="run-modal-header">
                    <div class="run-spinner-ring"></div>
                    <div>
                        <h2 class="run-modal-title">RUNNING JOB PIPELINE</h2>
                        <p class="run-modal-subtitle">Collecting and analyzing new European opportunities</p>
                    </div>
                </div>

                <!-- Master Progress Bar -->
                <div class="master-progress-section">
                    <div class="master-progress-header">
                        <span class="progress-label" id="run-current-stage-title">Executing autonomous pipeline...</span>
                        <span class="progress-pct" id="run-master-pct">0%</span>
                    </div>
                    <div class="master-progress-track">
                        <div class="master-progress-fill" id="run-master-fill" style="width: 0%;"></div>
                    </div>
                </div>

                <!-- Stage Checklist -->
                <div class="run-checklist-grid">
                    <div class="run-check-item" id="chk-step-1">
                        <span class="check-icon">○</span> Collect jobs
                    </div>
                    <div class="run-check-item" id="chk-step-2">
                        <span class="check-icon">○</span> Deduplicate
                    </div>
                    <div class="run-check-item" id="chk-step-3">
                        <span class="check-icon">○</span> Stage 1 — Relevance screening
                    </div>
                    <div class="run-check-item" id="chk-step-4">
                        <span class="check-icon">○</span> Stage 2 — Candidate matching
                    </div>
                    <div class="run-check-item" id="chk-step-5">
                        <span class="check-icon">○</span> Update application queue
                    </div>
                </div>

                <!-- Live Status Callout -->
                <div class="run-status-callout" id="run-live-callout">
                    Current: Initializing pipeline environment...
                </div>

                <!-- Informative Multi-Stage Detail Cards -->
                <div class="run-details-scrollable">
                    <!-- 1. Collection -->
                    <div class="stage-detail-box" id="detail-box-collect">
                        <div class="stage-detail-title">
                            <span>1. Multi-Source Collection</span>
                            <span class="badge-sub-count" id="stat-collect-total">Waiting...</span>
                        </div>
                        <div class="stage-source-chips" id="detail-collect-chips">
                            <span class="source-chip" id="chip-cloudflare">Cloudflare: pending</span>
                            <span class="source-chip" id="chip-datadog">Datadog: pending</span>
                            <span class="source-chip" id="chip-elastic">Elastic: pending</span>
                            <span class="source-chip" id="chip-others">Other sources: pending</span>
                        </div>
                    </div>

                    <!-- 2. Deduplication -->
                    <div class="stage-detail-box" id="detail-box-dedupe">
                        <div class="stage-detail-title">
                            <span>2. Deduplication & Capped Lookback</span>
                            <span class="badge-sub-count" id="stat-dedupe-result">Pending</span>
                        </div>
                        <div class="stage-dedupe-lines" id="detail-dedupe-lines">
                            <div class="dedupe-line" id="line-dedupe-collected">○ Ingested jobs: —</div>
                            <div class="dedupe-line" id="line-dedupe-dupes">○ Duplicates identified: —</div>
                            <div class="dedupe-line highlight" id="line-dedupe-unique">→ Net new unique jobs: —</div>
                        </div>
                    </div>

                    <!-- 3. Stage 1 Relevance -->
                    <div class="stage-detail-box" id="detail-box-stage1">
                        <div class="stage-detail-title">
                            <span>3. Stage 1 — Relevance Screening</span>
                            <span class="badge-sub-count" id="stat-stage1-progress">Pending</span>
                        </div>
                        <div class="mini-progress-track">
                            <div class="mini-progress-fill" id="fill-stage1" style="width: 0%;"></div>
                        </div>
                        <div class="stage-counts-row">
                            <div class="count-badge green" id="stat-stage1-passed">Send to Stage 2: —</div>
                            <div class="count-badge red" id="stat-stage1-rejected">Rejected: —</div>
                        </div>
                    </div>

                    <!-- 4. Stage 2 Matching -->
                    <div class="stage-detail-box" id="detail-box-stage2">
                        <div class="stage-detail-title">
                            <span>4. Stage 2 — Candidate Matching</span>
                            <span class="badge-sub-count" id="stat-stage2-progress">Pending</span>
                        </div>
                        <div class="mini-progress-track">
                            <div class="mini-progress-fill" id="fill-stage2" style="width: 0%;"></div>
                        </div>
                        <div class="stage-counts-row">
                            <div class="count-badge green" id="stat-stage2-strong">Strong matches: —</div>
                            <div class="count-badge amber" id="stat-stage2-borderline">Borderline: —</div>
                        </div>
                    </div>

                    <!-- 5. Final Update -->
                    <div class="stage-detail-box" id="detail-box-final">
                        <div class="stage-detail-title">
                            <span>5. Final Updates</span>
                            <span class="badge-sub-count" id="stat-final-status">Pending</span>
                        </div>
                        <div class="final-check-list" id="final-updates-list">
                            <div class="final-item" id="fitem-db">○ Job database updated</div>
                            <div class="final-item" id="fitem-queue">○ Application queue updated</div>
                            <div class="final-item" id="fitem-market">○ Market intelligence updated</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- STATE B: COMPLETION VIEW -->
            <div id="pipe-run-complete-view" style="display: none;">
                <div class="complete-header">
                    <div class="complete-celebration-badge">🎉</div>
                    <div>
                        <h2 class="complete-title">PIPELINE COMPLETED</h2>
                        <p class="complete-subtitle" id="complete-subtitle">92 new jobs processed</p>
                    </div>
                </div>

                <!-- Summary Metrics Table -->
                <div class="complete-metrics-wrap">
                    <table class="complete-summary-table">
                        <tbody>
                            <tr>
                                <td>Collected</td>
                                <td class="metric-num" id="comp-metric-collected">109</td>
                            </tr>
                            <tr>
                                <td>Duplicates</td>
                                <td class="metric-num text-amber" id="comp-metric-dupes">17</td>
                            </tr>
                            <tr>
                                <td>New Jobs Processed</td>
                                <td class="metric-num text-blue" id="comp-metric-new">92</td>
                            </tr>
                            <tr>
                                <td>Stage 2 Evaluated</td>
                                <td class="metric-num" id="comp-metric-stage2">41</td>
                            </tr>
                            <tr class="highlight-row">
                                <td>Shortlisted (Actionable)</td>
                                <td class="metric-num text-green" id="comp-metric-shortlist">18</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- New Opportunities By Domain -->
                <div class="complete-domain-section">
                    <div class="domain-sec-title">NEW OPPORTUNITIES BY TRACK</div>
                    <div class="domain-pills-grid" id="comp-domains-grid">
                        <div class="domain-pill-card">
                            <span class="domain-name">Cybersecurity</span>
                            <span class="domain-val">9</span>
                        </div>
                        <div class="domain-pill-card">
                            <span class="domain-name">Telecom AI</span>
                            <span class="domain-val">5</span>
                        </div>
                        <div class="domain-pill-card">
                            <span class="domain-name">Applied AI</span>
                            <span class="domain-val">3</span>
                        </div>
                        <div class="domain-pill-card">
                            <span class="domain-name">SRE / Cloud</span>
                            <span class="domain-val">1</span>
                        </div>
                    </div>
                </div>

                <!-- Queue Impact Banner -->
                <div class="queue-impact-card" id="comp-queue-banner">
                    <span class="impact-icon">📥</span>
                    <div>
                        <div class="impact-title" id="comp-queue-title">Application queue: 20 → 24</div>
                        <div class="impact-sub">New high-priority jobs with generated cover letters ready in Action Queue.</div>
                    </div>
                </div>

                <!-- Modal Actions -->
                <div class="complete-actions-bar">
                    <button class="btn-view-new-jobs" onclick="viewNewJobsAndClose()">
                        View New Jobs ➔
                    </button>
                    <button class="btn-close-runner" onclick="closePipelineRunModal()">
                        Close
                    </button>
                </div>
            </div>

        </div>
    </div>

    <!-- Toast Notification -->
    <div class="toast" id="toast">Notification message</div>

    <!-- Client-Side State & Logic -->
    <script>
        // Data Payloads
        const ALL_PIPELINE_JOBS = {pipeline_jobs_json};
        const ALL_DB_JOBS = {db_jobs_json};

        // Pipeline Table State
        let filteredPipelineJobs = [...ALL_PIPELINE_JOBS];
        let pipeCurrentPage = 1;
        let pipePageSize = 25;
        let activeStageFilter = 'all_active';

        // DB Table State
        let filteredDbJobs = [...ALL_DB_JOBS];
        let dbCurrentPage = 1;
        let dbPageSize = 25;

        // Current Active Modal Job
        let currentModalJobId = null;

        // Navigation Tabs
        function switchNavTab(tabName) {{
            document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

            const btn = document.getElementById('tab-btn-' + tabName);
            const content = document.getElementById('tab-' + tabName);
            if (btn) btn.classList.add('active');
            if (content) content.style.display = 'block';

            if (tabName === 'pipeline') {{
                renderPipelineTable();
            }} else if (tabName === 'database') {{
                renderDatabaseTable();
            }}
        }}

        // Accordion Toggle
        function toggleAccordion(id) {{
            const body = document.getElementById(id);
            const icon = document.getElementById('icon-' + id);
            if (body.classList.contains('open')) {{
                body.classList.remove('open');
                if (icon) icon.innerText = '▼';
            }} else {{
                body.classList.add('open');
                if (icon) icon.innerText = '▲';
            }}
        }}

        // Copy Cover Letter
        function copyLetter(jobId) {{
            const textarea = document.getElementById('textarea-letter-' + jobId);
            if (textarea) {{
                textarea.select();
                navigator.clipboard.writeText(textarea.value);
                showToast('✓ Tailored cover letter copied to clipboard!');
            }}
        }}

        function updateJobStatus(jobId, newStatus) {{
            if (newStatus === 'applied') {{
                return markAsApplied(jobId, '', '');
            }}
            return changePipelineStage(jobId, newStatus);
        }}

        // Action Queue: Mark as Applied
        async function markAsApplied(jobId, company, title) {{
            const card = document.getElementById('card-' + jobId);
            const btn = document.getElementById('btn-applied-' + jobId);
            if (btn) {{
                btn.disabled = true;
                btn.innerText = 'Applying...';
            }}

            // Animate card removal from Tab 1
            if (card) {{
                card.classList.add('vanishing');
                setTimeout(() => {{
                    if (card.parentNode) card.parentNode.removeChild(card);
                    decrementActionQueueCount();
                }}, 350);
            }}

            const todayStr = new Date().toISOString().split('T')[0];

            // Add to pipeline data locally
            const existingPipeIndex = ALL_PIPELINE_JOBS.findIndex(j => j.id === jobId);
            if (existingPipeIndex >= 0) {{
                ALL_PIPELINE_JOBS[existingPipeIndex].stage = 'applied';
                ALL_PIPELINE_JOBS[existingPipeIndex].applied_date = todayStr;
            }} else {{
                // Find in DB
                const dbJob = ALL_DB_JOBS.find(j => j.id === jobId) || {{}};
                ALL_PIPELINE_JOBS.unshift({{
                    id: jobId,
                    company: company || dbJob.company || 'Company',
                    title: title || dbJob.title || 'Role',
                    location: dbJob.location || 'Europe',
                    track: dbJob.track || 'telecom_ai',
                    priority: dbJob.priority || 'high',
                    score: dbJob.score || 85.0,
                    stage: 'applied',
                    applied_date: todayStr,
                    url: dbJob.url || '#',
                    cv: 'General_CV',
                    letter: '',
                    notes: '',
                }});
            }}

            // Update in DB records
            const dbJobRef = ALL_DB_JOBS.find(j => j.id === jobId);
            if (dbJobRef) dbJobRef.status = 'applied';

            try {{
                const res = await fetch(`/api/applications/${{jobId}}/status`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ status: 'applied', applied_date: todayStr }})
                }});

                if (res.ok) {{
                    const data = await res.json();
                    showToast(`✓ Job #${{jobId}} (${{company}}) marked as APPLIED and entered Pipeline!`);
                    updateStageCountersFromSummary(data.summary);
                }} else {{
                    throw new Error('API server not running');
                }}
            }} catch (err) {{
                localStorage.setItem(`app_status_${{jobId}}`, 'applied');
                showToast(`✓ Job #${{jobId}} (${{company}}) marked as APPLIED (Saved locally)!`);
                updateStageCountersLocally();
            }}

            filterPipelineTable();
            renderDatabaseTable();
        }}

        function decrementActionQueueCount() {{
            const topEl = document.getElementById('top-action-count');
            const badgeEl = document.getElementById('badge-applications-count');
            const pillEl = document.getElementById('action-queue-summary-pill');

            if (topEl) {{
                const cur = Math.max(0, parseInt(topEl.innerText, 10) - 1);
                topEl.innerText = cur;
                if (badgeEl) badgeEl.innerText = cur;
                if (pillEl) pillEl.innerText = `${{cur}} Prepared Applications Remaining`;
            }}
        }}

        // ========================================================
        // PIPELINE TABLE, STAGE FILTERS & PAGINATION
        // ========================================================
        function filterPipelineStage(stageKey, el) {{
            document.querySelectorAll('.stage-box').forEach(b => b.classList.remove('active'));
            if (el) el.classList.add('active');

            activeStageFilter = stageKey;
            const selectEl = document.getElementById('pipe-filter-stage');
            if (selectEl) selectEl.value = stageKey;

            filterPipelineTable();
        }}

        function filterPipelineTable() {{
            const search = (document.getElementById('pipe-search').value || '').toLowerCase().trim();
            const stage = (document.getElementById('pipe-filter-stage').value || activeStageFilter).toLowerCase();
            const company = (document.getElementById('pipe-filter-company').value || 'all').toLowerCase();
            const track = (document.getElementById('pipe-filter-track').value || 'all').toLowerCase();
            const priority = (document.getElementById('pipe-filter-priority').value || 'all').toLowerCase();

            filteredPipelineJobs = ALL_PIPELINE_JOBS.filter(j => {{
                if (search) {{
                    const fullText = (j.company + ' ' + j.title + ' ' + j.location + ' ' + j.track).toLowerCase();
                    if (!fullText.includes(search)) return false;
                }}
                if (stage === 'all_active') {{
                    if (['rejected', 'withdrawn'].includes(j.stage)) return false;
                }} else if (stage !== 'all') {{
                    if (j.stage !== stage) return false;
                }}
                if (company !== 'all' && j.company.toLowerCase() !== company) return false;
                if (track !== 'all' && (j.track || '').toLowerCase() !== track) return false;
                if (priority !== 'all' && (j.priority || '').toLowerCase() !== priority) return false;
                return true;
            }});

            pipeCurrentPage = 1;
            renderPipelineTable();
        }}

        function renderPipelineTable() {{
            const tbody = document.getElementById('pipe-table-body');
            const info = document.getElementById('pipe-pagination-info');
            const controls = document.getElementById('pipe-pagination-controls');
            if (!tbody) return;

            const total = filteredPipelineJobs.length;
            const totalPages = Math.max(1, Math.ceil(total / pipePageSize));
            const startIdx = (pipeCurrentPage - 1) * pipePageSize;
            const endIdx = Math.min(startIdx + pipePageSize, total);
            const pageItems = filteredPipelineJobs.slice(startIdx, endIdx);

            info.innerText = `Showing ${{total === 0 ? 0 : startIdx + 1}}–${{endIdx}} of ${{total}} applications`;

            let rowsHtml = '';
            for (const j of pageItems) {{
                const prioClass = j.priority === 'high' ? 'priority-high' : (j.priority === 'medium' ? 'priority-medium' : '');
                const prioLabel = (j.priority || 'medium').toUpperCase();
                const appliedDateStr = j.applied_date ? j.applied_date.replace(/T.*/, '') : 'Recently';

                // Next Action button
                let nextBtnHtml = '';
                if (j.stage === 'applied') {{
                    nextBtnHtml = `<button class="btn btn-primary-sm" onclick="advanceStageDirect(${{j.id}}, 'screening')">➔ Move to Screening</button>`;
                }} else if (j.stage === 'screening') {{
                    nextBtnHtml = `<button class="btn btn-primary-sm" onclick="advanceStageDirect(${{j.id}}, 'interview')">➔ Move to Interview</button>`;
                }} else if (j.stage === 'interview' || j.stage === 'interviewing') {{
                    nextBtnHtml = `<button class="btn btn-success-sm" onclick="advanceStageDirect(${{j.id}}, 'offered')">🎉 Offer Received</button>`;
                }} else if (j.stage === 'offered') {{
                    nextBtnHtml = `<span style="color:var(--accent-green); font-size:12px; font-weight:700;">🏆 Offer Received</span>`;
                }} else {{
                    nextBtnHtml = `<span style="color:var(--text-muted); font-size:12px;">—</span>`;
                }}

                rowsHtml += `
                <tr id="pipe-row-${{j.id}}">
                    <td><strong>#${{j.id}}</strong></td>
                    <td><strong>${{escapeHtml(j.company)}}</strong></td>
                    <td><a href="${{escapeHtml(j.url)}}" target="_blank" rel="noopener noreferrer" style="color:var(--text-primary); text-decoration:none; font-weight:600;">${{escapeHtml(j.title)}}</a></td>
                    <td><span style="color:var(--text-secondary);">${{escapeHtml(j.location)}}</span></td>
                    <td><span class="track-tag" style="font-size:11px;">${{escapeHtml(j.track)}}</span></td>
                    <td><span class="score-pill">${{parseFloat(j.score).toFixed(1)}}%</span></td>
                    <td><span class="badge ${{prioClass}}" style="font-size:10px;">${{prioLabel}}</span></td>
                    <td>
                        <span class="stage-pill stage-${{j.stage}}" id="pipe-stage-pill-${{j.id}}">${{j.stage.toUpperCase()}}</span>
                    </td>
                    <td><span style="color:var(--text-secondary); font-size:12px;">${{appliedDateStr}}</span></td>
                    <td>
                        <div class="pipe-table-actions">
                            ${{nextBtnHtml}}
                            <select class="stage-dropdown-mini" onchange="changePipelineStage(${{j.id}}, this.value)">
                                <option value="applied" ${{j.stage === 'applied' ? 'selected' : ''}}>Applied</option>
                                <option value="screening" ${{j.stage === 'screening' ? 'selected' : ''}}>Screening</option>
                                <option value="interview" ${{['interview', 'interviewing'].includes(j.stage) ? 'selected' : ''}}>Interview</option>
                                <option value="offered" ${{['offered', 'offer'].includes(j.stage) ? 'selected' : ''}}>Offered 🎉</option>
                                <option value="rejected" ${{j.stage === 'rejected' ? 'selected' : ''}}>Rejected</option>
                                <option value="withdrawn" ${{j.stage === 'withdrawn' ? 'selected' : ''}}>Withdrawn</option>
                            </select>
                        </div>
                    </td>
                    <td>
                        <button class="btn btn-secondary-sm" onclick="openDetailsModal(${{j.id}})">📝 Details</button>
                    </td>
                </tr>
                `;
            }}

            tbody.innerHTML = rowsHtml || '<tr><td colspan="11" style="text-align:center; padding:30px; color:var(--text-secondary);">No applications match the selected filter. Click [✓ Mark as Applied] on the Applications tab to add applications.</td></tr>';

            // Pagination Controls
            let pBtns = '';
            pBtns += `<button class="page-btn" onclick="changePipePage(${{pipeCurrentPage - 1}})" ${{pipeCurrentPage <= 1 ? 'disabled' : ''}}>« Prev</button>`;

            const maxVisible = 5;
            let startP = Math.max(1, pipeCurrentPage - 2);
            let endP = Math.min(totalPages, startP + maxVisible - 1);
            if (endP - startP < maxVisible - 1) {{
                startP = Math.max(1, endP - maxVisible + 1);
            }}

            for (let p = startP; p <= endP; p++) {{
                pBtns += `<button class="page-btn ${{p === pipeCurrentPage ? 'active' : ''}}" onclick="changePipePage(${{p}})">${{p}}</button>`;
            }}

            pBtns += `<button class="page-btn" onclick="changePipePage(${{pipeCurrentPage + 1}})" ${{pipeCurrentPage >= totalPages ? 'disabled' : ''}}>Next »</button>`;
            controls.innerHTML = pBtns;
        }}

        function changePipePage(newPage) {{
            const totalPages = Math.max(1, Math.ceil(filteredPipelineJobs.length / pipePageSize));
            if (newPage < 1 || newPage > totalPages) return;
            pipeCurrentPage = newPage;
            renderPipelineTable();
        }}

        function changePipePageSize(newSize) {{
            pipePageSize = parseInt(newSize, 10) || 25;
            pipeCurrentPage = 1;
            renderPipelineTable();
        }}

        function advanceStageDirect(jobId, newStage) {{
            changePipelineStage(jobId, newStage);
        }}

        async function changePipelineStage(jobId, newStage) {{
            const job = ALL_PIPELINE_JOBS.find(j => j.id === jobId);
            if (job) {{
                job.stage = newStage;
            }}

            // Update in DB records
            const dbJobRef = ALL_DB_JOBS.find(j => j.id === jobId);
            if (dbJobRef) dbJobRef.status = newStage;

            updateStageCountersLocally();
            renderPipelineTable();

            try {{
                const res = await fetch(`/api/applications/${{jobId}}/status`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ status: newStage }})
                }});
                if (res.ok) {{
                    const data = await res.json();
                    showToast(`✓ Job #${{jobId}} transitioned to ${{newStage.toUpperCase()}}!`);
                    if (data.summary) updateStageCountersFromSummary(data.summary);
                }}
            }} catch (err) {{
                localStorage.setItem(`app_status_${{jobId}}`, newStage);
                showToast(`✓ Job #${{jobId}} transitioned to ${{newStage.toUpperCase()}} (saved locally).`);
            }}
        }}

        function updateStageCountersLocally() {{
            let active = 0, applied = 0, screening = 0, interview = 0, offered = 0, rejected = 0, withdrawn = 0;
            ALL_PIPELINE_JOBS.forEach(j => {{
                const s = j.stage;
                if (s === 'applied') applied++;
                else if (s === 'screening') screening++;
                else if (['interview', 'interviewing'].includes(s)) interview++;
                else if (['offered', 'offer'].includes(s)) offered++;
                else if (s === 'rejected') rejected++;
                else if (s === 'withdrawn') withdrawn++;
            }});
            active = applied + screening + interview + offered;

            const cntActive = document.getElementById('cnt-pipe-active');
            const cntApplied = document.getElementById('cnt-pipe-applied');
            const cntScreening = document.getElementById('cnt-pipe-screening');
            const cntInterview = document.getElementById('cnt-pipe-interview');
            const cntOffered = document.getElementById('cnt-pipe-offered');
            const cntRejected = document.getElementById('cnt-pipe-rejected');
            const cntWithdrawn = document.getElementById('cnt-pipe-withdrawn');
            const topPipe = document.getElementById('top-pipeline-count');
            const badgePipe = document.getElementById('badge-pipeline-count');

            if (cntActive) cntActive.innerText = active;
            if (cntApplied) cntApplied.innerText = applied;
            if (cntScreening) cntScreening.innerText = screening;
            if (cntInterview) cntInterview.innerText = interview;
            if (cntOffered) cntOffered.innerText = offered;
            if (cntRejected) cntRejected.innerText = rejected;
            if (cntWithdrawn) cntWithdrawn.innerText = withdrawn;
            if (topPipe) topPipe.innerText = active;
            if (badgePipe) badgePipe.innerText = ALL_PIPELINE_JOBS.length;
        }}

        function updateStageCountersFromSummary(summary) {{
            if (!summary) return;
            const cntActive = document.getElementById('cnt-pipe-active');
            const cntApplied = document.getElementById('cnt-pipe-applied');
            const cntScreening = document.getElementById('cnt-pipe-screening');
            const cntInterview = document.getElementById('cnt-pipe-interview');
            const cntOffered = document.getElementById('cnt-pipe-offered');
            const cntRejected = document.getElementById('cnt-pipe-rejected');
            const cntWithdrawn = document.getElementById('cnt-pipe-withdrawn');
            const topPipe = document.getElementById('top-pipeline-count');
            const badgePipe = document.getElementById('badge-pipeline-count');

            const active = (summary.applied || 0) + (summary.screening || 0) + (summary.interview || 0) + (summary.offered || 0);
            if (cntActive) cntActive.innerText = summary.all_active || active;
            if (cntApplied) cntApplied.innerText = summary.applied || 0;
            if (cntScreening) cntScreening.innerText = summary.screening || 0;
            if (cntInterview) cntInterview.innerText = summary.interview || 0;
            if (cntOffered) cntOffered.innerText = summary.offered || 0;
            if (cntRejected) cntRejected.innerText = summary.rejected || 0;
            if (cntWithdrawn) cntWithdrawn.innerText = summary.withdrawn || 0;
            if (topPipe) topPipe.innerText = summary.all_active || active;
            if (badgePipe) badgePipe.innerText = summary.total_pipeline || ALL_PIPELINE_JOBS.length;
        }}

        // ========================================================
        // APPLICATION DETAILS & NOTES MODAL (Point 10)
        // ========================================================
        function openDetailsModal(jobId) {{
            const job = ALL_PIPELINE_JOBS.find(j => j.id === jobId);
            if (!job) return;
            currentModalJobId = jobId;

            document.getElementById('modal-title').innerText = `${{job.title}} — #${{job.id}}`;
            document.getElementById('modal-sub').innerText = `${{job.company}} • 📍 ${{job.location}} • Track: ${{job.track}} • Match: ${{parseFloat(job.score).toFixed(1)}}% • Stage: ${{job.stage.toUpperCase()}}`;
            document.getElementById('modal-notes-url').value = job.url || '#';
            document.getElementById('modal-letter-text').value = job.letter || 'No cover letter draft recorded.';

            // Parse notes
            let notesObj = {{}};
            try {{
                notesObj = JSON.parse(job.notes);
            }} catch (e) {{
                notesObj = {{ text: job.notes || '' }};
            }}

            document.getElementById('modal-notes-recruiter').value = notesObj.recruiter || '';
            document.getElementById('modal-notes-salary').value = notesObj.salary || '';
            document.getElementById('modal-notes-followup').value = notesObj.followup || '';
            document.getElementById('modal-notes-text').value = notesObj.text || '';

            // Build Timeline
            const appliedDate = job.applied_date ? job.applied_date.replace(/T.*/, '') : 'Recent';
            const stages = ['applied', 'screening', 'interview', 'offered'];
            const currentStage = job.stage;
            const isExit = ['rejected', 'withdrawn'].includes(currentStage);

            let timelineHtml = '';
            stages.forEach((st, idx) => {{
                let cls = '';
                const stIdx = stages.indexOf(currentStage);
                if (st === currentStage) cls = 'active';
                else if (!isExit && stIdx > idx) cls = 'passed';

                let dateSub = '';
                if (st === 'applied') dateSub = appliedDate;

                timelineHtml += `
                <div class="timeline-step ${{cls}}">
                    <div class="timeline-dot"></div>
                    <div class="timeline-label">${{st}}</div>
                    <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">${{dateSub}}</div>
                </div>
                `;
            }});

            if (isExit) {{
                timelineHtml += `
                <div class="timeline-step active">
                    <div class="timeline-dot" style="background:var(--accent-coral);"></div>
                    <div class="timeline-label" style="color:var(--accent-coral);">${{currentStage}}</div>
                </div>
                `;
            }}

            document.getElementById('modal-timeline').innerHTML = timelineHtml;
            document.getElementById('app-modal').classList.add('open');
        }}

        function closeModal() {{
            document.getElementById('app-modal').classList.remove('open');
            currentModalJobId = null;
        }}

        function closeModalOnOverlay(e) {{
            if (e.target.id === 'app-modal') {{
                closeModal();
            }}
        }}

        function copyModalLetter() {{
            const textarea = document.getElementById('modal-letter-text');
            if (textarea) {{
                textarea.select();
                navigator.clipboard.writeText(textarea.value);
                showToast('✓ Cover letter copied to clipboard!');
            }}
        }}

        async function saveModalNotes() {{
            if (!currentModalJobId) return;
            const btn = document.getElementById('modal-btn-save');
            btn.disabled = true;
            btn.innerText = 'Saving...';

            const notesPayload = {{
                recruiter: document.getElementById('modal-notes-recruiter').value.trim(),
                salary: document.getElementById('modal-notes-salary').value.trim(),
                followup: document.getElementById('modal-notes-followup').value,
                text: document.getElementById('modal-notes-text').value.trim(),
            }};
            const notesStr = JSON.stringify(notesPayload);

            // Update in local array
            const job = ALL_PIPELINE_JOBS.find(j => j.id === currentModalJobId);
            if (job) job.notes = notesStr;

            try {{
                const res = await fetch(`/api/applications/${{currentModalJobId}}/status`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ notes: notesStr }})
                }});

                if (res.ok) {{
                    showToast(`✓ Application notes for Job #${{currentModalJobId}} saved successfully!`);
                }} else {{
                    throw new Error('API server unavailable');
                }}
            }} catch (err) {{
                localStorage.setItem(`app_notes_${{currentModalJobId}}`, notesStr);
                showToast(`✓ Application notes saved locally for Job #${{currentModalJobId}}!`);
            }} finally {{
                btn.disabled = false;
                btn.innerText = '💾 Save Notes';
                closeModal();
            }}
        }}

        // ========================================================
        // TAB 3: COMPLETE JOB DATABASE ARCHIVE
        // ========================================================
        function filterDatabaseTable() {{
            const search = (document.getElementById('db-search').value || '').toLowerCase().trim();
            const status = document.getElementById('db-filter-status').value.toLowerCase();
            const company = document.getElementById('db-filter-company').value.toLowerCase();
            const track = document.getElementById('db-filter-track').value.toLowerCase();
            const priority = document.getElementById('db-filter-priority').value.toLowerCase();
            const source = document.getElementById('db-filter-source').value.toLowerCase();

            filteredDbJobs = ALL_DB_JOBS.filter(j => {{
                if (search) {{
                    const fullText = (j.company + ' ' + j.title + ' ' + j.location + ' ' + j.track).toLowerCase();
                    if (!fullText.includes(search)) return false;
                }}
                if (status !== 'all') {{
                    if (status === 'prepared' && j.status !== 'prepared') return false;
                    else if (status !== 'prepared' && j.status.toLowerCase() !== status) return false;
                }}
                if (company !== 'all' && j.company.toLowerCase() !== company) return false;
                if (track !== 'all' && (j.track || '').toLowerCase() !== track) return false;
                if (priority !== 'all' && (j.priority || '').toLowerCase() !== priority) return false;
                if (source !== 'all' && (j.source || '').toLowerCase() !== source) return false;
                return true;
            }});

            dbCurrentPage = 1;
            renderDatabaseTable();
        }}

        function renderDatabaseTable() {{
            const tbody = document.getElementById('db-table-body');
            const info = document.getElementById('db-pagination-info');
            const controls = document.getElementById('db-pagination-controls');
            if (!tbody) return;

            const total = filteredDbJobs.length;
            const totalPages = Math.max(1, Math.ceil(total / dbPageSize));
            const startIdx = (dbCurrentPage - 1) * dbPageSize;
            const endIdx = Math.min(startIdx + dbPageSize, total);
            const pageItems = filteredDbJobs.slice(startIdx, endIdx);

            info.innerText = `Showing ${{total === 0 ? 0 : startIdx + 1}}–${{endIdx}} of ${{total}} jobs`;

            let rowsHtml = '';
            for (const j of pageItems) {{
                const prioClass = j.priority === 'high' ? 'priority-high' : (j.priority === 'medium' ? 'priority-medium' : '');
                const prioLabel = (j.priority || 'none').toUpperCase();
                rowsHtml += `
                <tr>
                    <td><strong>#${{j.id}}</strong></td>
                    <td><strong>${{escapeHtml(j.company)}}</strong></td>
                    <td><a href="${{escapeHtml(j.url)}}" target="_blank" rel="noopener noreferrer" style="color:var(--text-primary); text-decoration:none; font-weight:600;">${{escapeHtml(j.title)}}</a></td>
                    <td><span style="color:var(--text-secondary);">${{escapeHtml(j.location)}}</span></td>
                    <td><span class="track-tag" style="font-size:11px;">${{escapeHtml(j.track)}}</span></td>
                    <td><span class="score-pill">${{parseFloat(j.score).toFixed(1)}}%</span></td>
                    <td>${{ prioClass ? `<span class="badge ${{prioClass}}" style="font-size:10px;">${{prioLabel}}</span>` : `<span style="color:var(--text-muted); font-size:11px;">NONE</span>` }}</td>
                    <td><span class="stage-pill stage-${{j.status}}" style="font-size:10px;">${{j.status.toUpperCase()}}</span></td>
                    <td><span style="font-size:11px;">${{j.freshness}}</span></td>
                    <td><a href="${{escapeHtml(j.url)}}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary-sm">Apply ↗</a></td>
                </tr>
                `;
            }}
            tbody.innerHTML = rowsHtml || '<tr><td colspan="10" style="text-align:center; padding:30px; color:var(--text-secondary);">No historical records match your filter criteria.</td></tr>';

            // Pagination Controls
            let pBtns = '';
            pBtns += `<button class="page-btn" onclick="changeDbPage(${{dbCurrentPage - 1}})" ${{dbCurrentPage <= 1 ? 'disabled' : ''}}>« Prev</button>`;

            const maxVisible = 5;
            let startP = Math.max(1, dbCurrentPage - 2);
            let endP = Math.min(totalPages, startP + maxVisible - 1);
            if (endP - startP < maxVisible - 1) {{
                startP = Math.max(1, endP - maxVisible + 1);
            }}

            for (let p = startP; p <= endP; p++) {{
                pBtns += `<button class="page-btn ${{p === dbCurrentPage ? 'active' : ''}}" onclick="changeDbPage(${{p}})">${{p}}</button>`;
            }}

            pBtns += `<button class="page-btn" onclick="changeDbPage(${{dbCurrentPage + 1}})" ${{dbCurrentPage >= totalPages ? 'disabled' : ''}}>Next »</button>`;
            controls.innerHTML = pBtns;
        }}

        function changeDbPage(newPage) {{
            const totalPages = Math.max(1, Math.ceil(filteredDbJobs.length / dbPageSize));
            if (newPage < 1 || newPage > totalPages) return;
            dbCurrentPage = newPage;
            renderDatabaseTable();
        }}

        function changeDbPageSize(newSize) {{
            dbPageSize = parseInt(newSize, 10) || 25;
            dbCurrentPage = 1;
            renderDatabaseTable();
        }}

        // General Utilities
        function filterActionJobs(filter, btn) {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');

            const cards = document.querySelectorAll('#action-jobs-container .job-card');
            cards.forEach(card => {{
                const priority = card.getAttribute('data-priority') || '';
                const track = card.getAttribute('data-track') || '';

                if (filter === 'all') {{
                    card.style.display = 'block';
                }} else if (filter === 'high' || filter === 'medium') {{
                    card.style.display = (priority === filter) ? 'block' : 'none';
                }} else if (filter === 'telecom ai') {{
                    card.style.display = track.includes('telecom') ? 'block' : 'none';
                }} else if (filter === 'network security') {{
                    card.style.display = track.includes('security') ? 'block' : 'none';
                }}
            }});
        }}

        function handleActionSearch() {{
            const term = document.getElementById('action-search-input').value.toLowerCase().trim();
            const cards = document.querySelectorAll('#action-jobs-container .job-card');
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

        function escapeHtml(text) {{
            if (!text) return '';
            const map = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }};
            return text.toString().replace(/[&<>"']/g, m => map[m]);
        }}

        // ==========================================
        // Temporary Pipeline Run Modal & Execution
        // ==========================================
        let pipelineRunEventSource = null;
        let isPipelineRunning = false;

        function openPipelineRunModal() {{
            if (isPipelineRunning) return;
            const modal = document.getElementById('pipeline-run-modal');
            if (!modal) return;

            // Reset modal views
            document.getElementById('pipe-run-progress-view').style.display = 'block';
            document.getElementById('pipe-run-complete-view').style.display = 'none';

            // Reset progress bars and labels
            document.getElementById('run-master-fill').style.width = '0%';
            document.getElementById('run-master-pct').innerText = '0%';
            document.getElementById('run-current-stage-title').innerText = 'Initializing autonomous pipeline...';
            document.getElementById('run-live-callout').innerText = 'Current: Connecting to European sources & LinkedIn...';

            // Reset checklist
            for (let i = 1; i <= 5; i++) {{
                const el = document.getElementById('chk-step-' + i);
                if (el) {{
                    el.className = 'run-check-item';
                    const icon = el.querySelector('.check-icon');
                    if (icon) icon.innerText = '○';
                }}
            }}

            // Reset detail boxes
            const statCol = document.getElementById('stat-collect-total');
            if (statCol) statCol.innerText = 'Waiting...';
            ['cloudflare', 'datadog', 'elastic', 'others'].forEach(k => {{
                const ch = document.getElementById('chip-' + k);
                if (ch) {{
                    ch.className = 'source-chip';
                    ch.innerText = (k === 'others' ? 'Other sources' : k.charAt(0).toUpperCase() + k.slice(1)) + ': pending';
                }}
            }});

            const statDedupe = document.getElementById('stat-dedupe-result');
            if (statDedupe) statDedupe.innerText = 'Pending';
            const lIng = document.getElementById('line-dedupe-collected');
            if (lIng) lIng.innerText = '○ Ingested jobs: —';
            const lDup = document.getElementById('line-dedupe-dupes');
            if (lDup) lDup.innerText = '○ Duplicates identified: —';
            const lUniq = document.getElementById('line-dedupe-unique');
            if (lUniq) lUniq.innerText = '→ Net new unique jobs: —';

            const fillS1 = document.getElementById('fill-stage1');
            if (fillS1) fillS1.style.width = '0%';
            const statS1P = document.getElementById('stat-stage1-progress');
            if (statS1P) statS1P.innerText = 'Pending';
            const statS1Pass = document.getElementById('stat-stage1-passed');
            if (statS1Pass) statS1Pass.innerText = 'Send to Stage 2: —';
            const statS1Rej = document.getElementById('stat-stage1-rejected');
            if (statS1Rej) statS1Rej.innerText = 'Rejected: —';

            const fillS2 = document.getElementById('fill-stage2');
            if (fillS2) fillS2.style.width = '0%';
            const statS2P = document.getElementById('stat-stage2-progress');
            if (statS2P) statS2P.innerText = 'Pending';
            const statS2Str = document.getElementById('stat-stage2-strong');
            if (statS2Str) statS2Str.innerText = 'Strong matches: —';
            const statS2Brd = document.getElementById('stat-stage2-borderline');
            if (statS2Brd) statS2Brd.innerText = 'Borderline: —';

            const statFin = document.getElementById('stat-final-status');
            if (statFin) statFin.innerText = 'Pending';
            ['db', 'queue', 'market'].forEach(k => {{
                const it = document.getElementById('fitem-' + k);
                if (it) {{
                    it.className = 'final-item';
                    if (k === 'db') it.innerText = '○ Job database updated';
                    if (k === 'queue') it.innerText = '○ Application queue updated';
                    if (k === 'market') it.innerText = '○ Market intelligence updated';
                }}
            }});

            modal.style.display = 'flex';
            startPipelineExecution();
        }}

        function closePipelineRunModal() {{
            const modal = document.getElementById('pipeline-run-modal');
            if (modal) modal.style.display = 'none';
            if (pipelineRunEventSource) {{
                pipelineRunEventSource.close();
                pipelineRunEventSource = null;
            }}
            isPipelineRunning = false;
        }}

        function viewNewJobsAndClose() {{
            closePipelineRunModal();
            switchNavTab('applications');
            showToast('✓ Viewing new opportunities in Action Queue (24 ready)');
        }}

        function handlePipelineStep(step) {{
            const fill = document.getElementById('run-master-fill');
            const pct = document.getElementById('run-master-pct');
            const title = document.getElementById('run-current-stage-title');
            const callout = document.getElementById('run-live-callout');

            if (fill && step.percent !== undefined) fill.style.width = step.percent + '%';
            if (pct && step.percent !== undefined) pct.innerText = step.percent + '%';
            if (callout && step.callout) callout.innerText = 'Current: ' + step.callout;

            const setStepActive = (num) => {{
                for (let i = 1; i <= 5; i++) {{
                    const it = document.getElementById('chk-step-' + i);
                    if (!it) continue;
                    const ic = it.querySelector('.check-icon');
                    if (i < num) {{
                        it.className = 'run-check-item done';
                        if (ic) ic.innerText = '✓';
                    }} else if (i === num) {{
                        it.className = 'run-check-item active';
                        if (ic) ic.innerText = '●';
                    }} else {{
                        it.className = 'run-check-item';
                        if (ic) ic.innerText = '○';
                    }}
                }}
            }};

            if (step.stage === 'init') {{
                setStepActive(1);
                if (title) title.innerText = 'Connecting to European sources & LinkedIn...';
            }} else if (step.stage === 'collect') {{
                setStepActive(1);
                if (title) title.innerText = '1. Multi-Source Collection';
                const d = step.data || {{}};
                const chipsContainer = document.getElementById('detail-collect-chips');
                if (chipsContainer && d.sources_summary && Object.keys(d.sources_summary).length > 0) {{
                    let html = '';
                    for (const [k, v] of Object.entries(d.sources_summary)) {{
                        const cleanName = k.replace('greenhouse:', '').replace('lever:', '').replace('ashby:', '').replace('linkedin:', 'LinkedIn ');
                        html += `<span class="source-chip done">✓ ${{escapeHtml(cleanName)}}: ${{v}} new</span> `;
                    }}
                    chipsContainer.innerHTML = html;
                }} else if (chipsContainer && d.source) {{
                    const chipId = 'chip-src-' + d.source.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
                    let chip = document.getElementById(chipId);
                    if (!chip) {{
                        chip = document.createElement('span');
                        chip.id = chipId;
                        chip.className = 'source-chip done';
                        chipsContainer.appendChild(chip);
                    }}
                    chip.innerText = `✓ ${{d.source}}: ${{d.saved || 0}} new`;
                }}
                const sTot = document.getElementById('stat-collect-total');
                if (sTot) sTot.innerText = (d.total !== undefined ? d.total : '...') + ' jobs collected';
            }} else if (step.stage === 'dedupe') {{
                setStepActive(2);
                if (title) title.innerText = '2. Deduplication & Capped Lookback';
                const d = step.data || {{}};
                const lIng = document.getElementById('line-dedupe-collected');
                if (lIng) lIng.innerText = `✓ ${{d.collected !== undefined ? d.collected : 0}} collected`;
                const lDup = document.getElementById('line-dedupe-dupes');
                if (lDup) lDup.innerText = `✓ ${{d.duplicates !== undefined ? d.duplicates : 0}} duplicates skipped`;
                const lUniq = document.getElementById('line-dedupe-unique');
                if (lUniq) lUniq.innerText = `→ ${{d.new_jobs !== undefined ? d.new_jobs : 0}} new unique jobs`;
                const sDed = document.getElementById('stat-dedupe-result');
                if (sDed) sDed.innerText = `${{d.new_jobs !== undefined ? d.new_jobs : 0}} new jobs`;
            }} else if (step.stage === 'stage1') {{
                setStepActive(3);
                if (title) title.innerText = '3. Stage 1 — Relevance screening';
                const d = step.data || {{}};
                const total = d.total || 0;
                const current = d.current || 0;
                const pct = total > 0 ? Math.round((current / total) * 100) : 100;
                const fillS1 = document.getElementById('fill-stage1');
                if (fillS1) fillS1.style.width = pct + '%';
                const s1P = document.getElementById('stat-stage1-progress');
                if (s1P) s1P.innerText = total > 0 ? `${{current}} / ${{total}}` : 'Up to date';
                const s1Pass = document.getElementById('stat-stage1-passed');
                if (s1Pass) s1Pass.innerText = `Send to Stage 2: ${{d.passed !== undefined ? d.passed : '—'}}`;
                const s1Rej = document.getElementById('stat-stage1-rejected');
                if (s1Rej) s1Rej.innerText = `Rejected: ${{d.rejected !== undefined ? d.rejected : '—'}}`;
            }} else if (step.stage === 'stage2') {{
                setStepActive(4);
                if (title) title.innerText = '4. Stage 2 — Candidate matching';
                const d = step.data || {{}};
                const total = d.total || 0;
                const current = d.current || 0;
                const pct = total > 0 ? Math.round((current / total) * 100) : 100;
                const fillS2 = document.getElementById('fill-stage2');
                if (fillS2) fillS2.style.width = pct + '%';
                const s2P = document.getElementById('stat-stage2-progress');
                if (s2P) s2P.innerText = total > 0 ? `${{current}} / ${{total}}` : 'Up to date';
                const s2Str = document.getElementById('stat-stage2-strong');
                if (s2Str) s2Str.innerText = `Strong matches: ${{d.strong !== undefined ? d.strong : '—'}}`;
                const s2Brd = document.getElementById('stat-stage2-borderline');
                if (s2Brd) s2Brd.innerText = `Borderline: ${{d.borderline !== undefined ? d.borderline : '—'}}`;
            }} else if (step.stage === 'final') {{
                setStepActive(5);
                if (title) title.innerText = '5. Final update';
                const d = step.data || {{}};
                const fDb = document.getElementById('fitem-db');
                if (fDb) {{ fDb.className = d.db ? 'final-item done' : 'final-item active'; fDb.innerText = (d.db ? '✓ ' : '● ') + 'Job database updated'; }}
                const fQ = document.getElementById('fitem-queue');
                if (fQ) {{ fQ.className = d.queue ? 'final-item done' : 'final-item'; fQ.innerText = (d.queue ? '✓ ' : '○ ') + 'Application queue updated'; }}
                const fM = document.getElementById('fitem-market');
                if (fM) {{ fM.className = d.market ? 'final-item done' : 'final-item'; fM.innerText = (d.market ? '✓ ' : '○ ') + 'Market intelligence updated'; }}
                const statFin = document.getElementById('stat-final-status');
                if (statFin) statFin.innerText = (d.db && d.queue && d.market) ? 'Updated' : 'Processing...';
            }} else if (step.stage === 'complete') {{
                for (let i = 1; i <= 5; i++) {{
                    const it = document.getElementById('chk-step-' + i);
                    if (it) {{
                        it.className = 'run-check-item done';
                        const ic = it.querySelector('.check-icon');
                        if (ic) ic.innerText = '✓';
                    }}
                }}

                setTimeout(() => {{
                    document.getElementById('pipe-run-progress-view').style.display = 'none';
                    document.getElementById('pipe-run-complete-view').style.display = 'block';

                    // Update completion metrics
                    const s = step.summary || {{}};
                    const mCol = document.getElementById('comp-metric-collected');
                    if (mCol) mCol.innerText = s.collected !== undefined ? s.collected : 0;
                    const mDup = document.getElementById('comp-metric-dupes');
                    if (mDup) mDup.innerText = s.duplicates !== undefined ? s.duplicates : 0;
                    const mNew = document.getElementById('comp-metric-new');
                    if (mNew) mNew.innerText = s.new_jobs !== undefined ? s.new_jobs : 0;
                    const mS2 = document.getElementById('comp-metric-stage2');
                    if (mS2) mS2.innerText = (s.stage2_evaluated !== undefined ? s.stage2_evaluated : (s.stage2 !== undefined ? s.stage2 : 0));
                    const mShort = document.getElementById('comp-metric-shortlist');
                    if (mShort) mShort.innerText = s.shortlisted !== undefined ? s.shortlisted : 0;

                    const subtitle = document.getElementById('complete-subtitle');
                    if (subtitle) {{
                        if (s.new_jobs > 0) {{
                            subtitle.innerText = `${{s.new_jobs}} new jobs processed`;
                        }} else if (s.stage1_evaluated > 0) {{
                            subtitle.innerText = `${{s.stage1_evaluated}} queued jobs evaluated`;
                        }} else {{
                            subtitle.innerText = 'Database & sources are fully up to date';
                        }}
                    }}

                    // Render dynamic track breakdown pills
                    const domGrid = document.getElementById('comp-domains-grid');
                    if (domGrid && s.domains) {{
                        let domHtml = '';
                        for (const [dName, dCount] of Object.entries(s.domains)) {{
                            domHtml += `
                                <div class="domain-pill-card">
                                    <span class="domain-name">${{escapeHtml(dName)}}</span>
                                    <span class="domain-val">${{dCount}}</span>
                                </div>
                            `;
                        }}
                        if (domHtml) domGrid.innerHTML = domHtml;
                    }}

                    const qTitle = document.getElementById('comp-queue-title');
                    if (qTitle) qTitle.innerText = `Application queue: ${{s.queue_before !== undefined ? s.queue_before : 20}} → ${{s.queue_after !== undefined ? s.queue_after : 20}}`;

                    // Update Header
                    const hStatus = document.getElementById('header-status-text');
                    if (hStatus) hStatus.innerText = 'Up to date';

                    const hLastRun = document.getElementById('header-last-run');
                    if (hLastRun && step.last_run) {{
                        hLastRun.innerText = `Last run: ${{step.last_run}}`;
                    }}

                    // Update dashboard count badges
                    const topAction = document.getElementById('top-action-count');
                    if (topAction && s.queue_after !== undefined) topAction.innerText = s.queue_after;
                    const badgeAction = document.getElementById('badge-applications-count');
                    if (badgeAction && s.queue_after !== undefined) badgeAction.innerText = s.queue_after;

                    isPipelineRunning = false;
                    const toastMsg = s.new_jobs > 0 
                        ? `🎉 Pipeline completed! ${{s.new_jobs}} new jobs processed.`
                        : `✓ Pipeline completed! Database is fully up to date.`;
                    showToast(toastMsg);
                }}, 600);
            }} else if (step.stage === 'error') {{
                isPipelineRunning = false;
                if (title) title.innerText = '⚠️ Pipeline Execution Error';
                if (callout) callout.innerText = step.callout || 'An error occurred during execution.';
                showToast('❌ ' + (step.error || 'Pipeline execution failed.'));
            }}
        }}

        function startPipelineExecution() {{
            isPipelineRunning = true;
            if (window.location.protocol.startsWith('http')) {{
                try {{
                    const es = new EventSource('/api/pipeline/run-stream');
                    pipelineRunEventSource = es;
                    es.onmessage = function(e) {{
                        try {{
                            const step = JSON.parse(e.data);
                            handlePipelineStep(step);
                            if (step.stage === 'complete' || step.stage === 'error') {{
                                es.close();
                                pipelineRunEventSource = null;
                            }}
                        }} catch(err) {{
                            console.error('Error parsing SSE data:', err);
                        }}
                    }};
                    es.onerror = function() {{
                        es.close();
                        pipelineRunEventSource = null;
                        if (isPipelineRunning && document.getElementById('run-master-pct').innerText !== '100%') {{
                            handlePipelineStep({{
                                stage: 'error',
                                percent: 100,
                                callout: 'Connection to server interrupted. Please check server logs and retry.',
                                error: 'Connection lost'
                            }});
                        }}
                    }};
                    return;
                }} catch(err) {{
                    console.warn('EventSource failed:', err);
                }}
            }}
            handlePipelineStep({{
                stage: 'error',
                percent: 100,
                callout: 'Server not reachable via HTTP.',
                error: 'HTTP required'
            }});
        }}


        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3500);
        }}

        // Initial setup on DOM ready
        window.addEventListener('DOMContentLoaded', () => {{
            renderPipelineTable();
            renderDatabaseTable();
            document.querySelectorAll('#action-jobs-container .job-card').forEach(card => {{
                const jid = card.id.replace('card-', '');
                if (localStorage.getItem(`app_status_${{jid}}`) === 'applied') {{
                    card.style.display = 'none';
                }}
            }});
        }});
    </script>
</body>
</html>
"""
    return html_content


def generate_daily_reports(db_path: Path = DB_PATH, reports_dir: Path = REPORTS_DIR) -> Dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.date.today().isoformat()

    conn = sqlite3.connect(db_path)
    stats = get_pipeline_statistics(conn)
    action_jobs = get_actionable_jobs(conn)
    pipeline_jobs = get_pipeline_jobs(conn)
    all_db_jobs = get_all_database_jobs(conn)
    conn.close()

    app_repo = ApplicationRepository(str(db_path))
    pipeline_summary = app_repo.get_pipeline_summary()
    app_repo.close()

    market_analyzer = MarketAnalyzer(db_path)
    market_report = market_analyzer.get_market_intelligence_report()
    market_analyzer.close()

    md_content = generate_markdown_report(today_str, stats, action_jobs, pipeline_jobs, pipeline_summary, market_report)
    md_file = reports_dir / f"daily_digest_{today_str}.md"
    md_file.write_text(md_content, encoding="utf-8")

    html_content = generate_html_report(today_str, stats, action_jobs, pipeline_jobs, all_db_jobs, pipeline_summary, market_report)
    html_file = reports_dir / f"daily_digest_{today_str}.html"
    html_file.write_text(html_content, encoding="utf-8")

    latest_html = reports_dir / "latest_report.html"
    latest_html.write_text(html_content, encoding="utf-8")

    return {
        "md_path": md_file,
        "html_path": html_file,
        "latest_html": latest_html,
        "action_jobs_count": len(action_jobs),
        "pipeline_jobs_count": len(pipeline_jobs),
        "all_db_jobs_count": len(all_db_jobs),
    }


if __name__ == "__main__":
    result = generate_daily_reports()
    print("==================================================")
    print("DAILY DIGEST & PIPELINE GENERATED SUCCESSFULLY")
    print(f"Action Queue (Prepared): {result['action_jobs_count']}")
    print(f"Pipeline Active:         {result['pipeline_jobs_count']}")
    print(f"Database Total:          {result['all_db_jobs_count']}")
    print(f"Markdown Report:         {result['md_path']}")
    print(f"HTML Report:             {result['html_path']}")
    print(f"Latest Link:             {result['latest_html']}")
    print("==================================================")
