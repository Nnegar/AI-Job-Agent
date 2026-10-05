#!/usr/bin/env python3
"""
Daily Digest and Interactive Report Generator.
Generates:
1. reports/daily_digest_YYYY-MM-DD.html (Rich 4-tab interactive dashboard: Action Queue, Pipeline Tracker, Historical Database, Market Intelligence)
2. reports/daily_digest_YYYY-MM-DD.md (Clean markdown digest report)
3. reports/latest_report.html (Symlink/copy for convenient local opening)
"""

import datetime
import html
import json
import math
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    Returns jobs active in the application tracker (applied, screening, interview, offered, rejected, withdrawn).
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
    Returns full database inventory for Tab 3.
    """
    app_repo = ApplicationRepository()
    result = app_repo.get_database_jobs(limit=1000)
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
    lines.append(f"- **Active Pipeline**: {pipeline_summary.get('applied', 0)} Applied | "
                 f"{pipeline_summary.get('screening', 0)} Screening | "
                 f"{pipeline_summary.get('interview', 0)} Interview | "
                 f"{pipeline_summary.get('offered', 0)} Offers | "
                 f"{pipeline_summary.get('rejected', 0)} Rejected")
    lines.append(f"- **Market Monitored**: {stats['total_jobs']} European engineering opportunities evaluated\n")

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

    # 2. Generate Pipeline Cards HTML (Tab 2)
    pipeline_cards_html = []
    for pj in pipeline_jobs:
        jid = pj["id"]
        stage = pj["app_status"]
        applied_date_str = pj.get("applied_date") or "Recently"
        url = pj.get("url") or "#"
        score = pj.get("final_score") or pj.get("match_score") or 0
        letter_escaped = html.escape(pj.get("letter_text") or "No letter archived.")

        p_comp = pj.get("company") or "Unknown Company"
        p_title = pj.get("title") or "Technical Role"
        p_loc = pj.get("location") or "Europe / Remote"
        p_track = pj.get("primary_track") or "General"

        pipeline_card = f"""
        <div class="pipeline-card" id="pipe-card-{jid}" data-stage="{stage}" data-company="{html.escape(p_comp.lower())}">
            <div class="pipe-header">
                <div>
                    <span class="company-badge">{html.escape(p_comp)}</span>
                    <h4 class="pipe-title">{html.escape(p_title)}</h4>
                    <div class="pipe-sub">
                        <span>📍 {html.escape(p_loc)}</span> •
                        <span>Track: <strong>{html.escape(p_track)}</strong></span> •
                        <span class="score-pill">{score:.1f}% Match</span>
                    </div>
                </div>
                <div class="pipe-status-col">
                    <span class="stage-pill stage-{stage}" id="pipe-badge-{jid}">{stage.upper()}</span>
                    <span class="applied-date-sub">Applied: {applied_date_str}</span>
                </div>
            </div>

            <div class="pipe-actions-bar">
                <div class="pipe-stage-flow">
                    <label class="flow-label">Change Stage:</label>
                    <select class="stage-select" id="stage-select-{jid}" onchange="changePipelineStage({jid}, this.value)">
                        <option value="applied" {'selected' if stage=='applied' else ''}>Applied</option>
                        <option value="screening" {'selected' if stage=='screening' else ''}>Screening</option>
                        <option value="interview" {'selected' if stage in ('interview', 'interviewing') else ''}>Interview</option>
                        <option value="offered" {'selected' if stage in ('offered', 'offer') else ''}>Offered 🎉</option>
                        <option value="rejected" {'selected' if stage=='rejected' else ''}>Rejected</option>
                        <option value="withdrawn" {'selected' if stage=='withdrawn' else ''}>Withdrawn</option>
                    </select>
                </div>

                <div class="pipe-btn-group">
                    <a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary-sm">Site ↗</a>
                    <button class="btn btn-secondary-sm" onclick="toggleAccordion('pipe-letter-{jid}')">Cover Letter</button>
                    { '<button class="btn btn-primary-sm" onclick="advanceStage(' + str(jid) + ', \'screening\')">➔ Move to Screening</button>' if stage == 'applied' else '' }
                    { '<button class="btn btn-primary-sm" onclick="advanceStage(' + str(jid) + ', \'interview\')">➔ Move to Interview</button>' if stage == 'screening' else '' }
                    { '<button class="btn btn-success-sm" onclick="advanceStage(' + str(jid) + ', \'offered\')">🎉 Offer Received</button>' if stage in ('interview', 'interviewing') else '' }
                </div>
            </div>

            <div class="accordion-body" id="pipe-letter-{jid}">
                <textarea class="letter-textarea-compact" readonly>{letter_escaped}</textarea>
            </div>
        </div>
        """
        pipeline_cards_html.append(pipeline_card)

    # 3. Market Moving: Domain Momentum HTML (Tab 4)
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

    # 4. Your Skill Position Table HTML (Tab 4)
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

    # 5. High ROI Skills Cards HTML (Tab 4)
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

    # JSON database serialization for client-side search & pagination in Tab 3
    db_jobs_json = json.dumps(
        [
            {
                "id": j["id"],
                "company": j["company"],
                "title": j["title"],
                "location": j.get("location") or "Europe",
                "source": j.get("source", "greenhouse"),
                "track": j.get("primary_track", "general"),
                "priority": j.get("priority", "none"),
                "score": j.get("match_score", 0),
                "status": j.get("app_status", "discovered"),
                "freshness": j["freshness"]["badge"],
                "url": j.get("url") or "#",
            }
            for j in all_db_jobs
        ]
    )

    # Distinct filters for dropdowns
    companies = sorted(list(set(j["company"] for j in all_db_jobs if j.get("company"))))
    tracks = sorted(list(set(j.get("primary_track", "general") for j in all_db_jobs if j.get("primary_track"))))
    sources = sorted(list(set(j.get("source", "greenhouse") for j in all_db_jobs if j.get("source"))))

    company_options_html = "".join(f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in companies)
    track_options_html = "".join(f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in tracks)
    source_options_html = "".join(f'<option value="{html.escape(s)}">{html.escape(s)}</option>' for s in sources)

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
            max-width: 1280px;
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
        .status-pill-live {{
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.3);
            font-size: 12px;
            font-weight: 600;
            padding: 6px 12px;
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
        .stat-card.card-amber::before {{ background: var(--accent-amber); }}
        .stat-card.card-purple::before {{ background: var(--accent-purple); }}

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
            align-items: center;
            gap: 4px;
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
        .letter-textarea-compact {{
            width: 100%;
            height: 160px;
            background: #070c18;
            color: #e2e8f0;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px;
            font-family: var(--font-family);
            font-size: 12px;
            line-height: 1.5;
            resize: vertical;
        }}

        /* Pipeline (Tab 2) Styles */
        .pipeline-metrics-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 14px;
            margin-bottom: 24px;
        }}
        .pipe-metric-box {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 14px 16px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .pipe-metric-box:hover, .pipe-metric-box.active {{
            border-color: var(--accent-primary);
            background: var(--surface-hover);
        }}
        .pipe-metric-title {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-secondary);
            letter-spacing: 0.5px;
        }}
        .pipe-metric-val {{
            font-size: 26px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 4px;
        }}

        .pipeline-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 16px;
            transition: all 0.2s;
        }}
        .pipeline-card:hover {{
            border-color: #3b4d6b;
        }}
        .pipe-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            flex-wrap: wrap;
            margin-bottom: 12px;
        }}
        .pipe-title {{
            font-size: 17px;
            font-weight: 700;
            color: var(--text-primary);
            margin: 2px 0 4px 0;
        }}
        .pipe-sub {{
            font-size: 13px;
            color: var(--text-secondary);
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .score-pill {{
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border-radius: 4px;
            padding: 1px 6px;
            font-weight: 700;
            font-size: 11px;
        }}
        .pipe-status-col {{
            text-align: right;
        }}
        .stage-pill {{
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 0.5px;
            display: inline-block;
        }}
        .stage-applied {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .stage-screening {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
        .stage-interview, .stage-interviewing {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }}
        .stage-offered, .stage-offer {{ background: rgba(245, 158, 11, 0.2); color: #fde047; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .stage-rejected {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .stage-withdrawn {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }}

        .applied-date-sub {{
            display: block;
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        .pipe-actions-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface-color);
            padding: 10px 14px;
            border-radius: 8px;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .pipe-stage-flow {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .flow-label {{
            font-size: 12px;
            color: var(--text-secondary);
            font-weight: 600;
        }}
        .stage-select {{
            background: var(--bg-color);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }}
        .stage-select:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}
        .pipe-btn-group {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}

        /* Database (Tab 3) Styles */
        .db-controls-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 20px;
        }}
        .db-control-group label {{
            display: block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }}
        .db-select, .db-input {{
            width: 100%;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 7px 10px;
            color: var(--text-primary);
            font-size: 13px;
        }}
        .db-select:focus, .db-input:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}

        .db-table-wrap {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow-x: auto;
            margin-bottom: 16px;
        }}
        .db-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}
        .db-table th {{
            background: var(--surface-color);
            color: var(--text-secondary);
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-color);
        }}
        .db-table td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}
        .db-table tr:hover td {{
            background: var(--surface-hover);
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
            padding: 6px 12px;
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
                <h1>AI Job Agent — Daily Intelligence Report & Application Pipeline</h1>
                <p>Negar Najafi • MSc Telecommunications Engineering (Politecnico di Milano) • Milan, Italy • Europe Focus</p>
            </div>
            <div>
                <span class="status-pill-live">Pipeline Healthy & Up to Date</span>
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
                <span class="stat-value" id="top-pipeline-count">{pipeline_summary.get('applied', 0) + pipeline_summary.get('screening', 0) + pipeline_summary.get('interview', 0)}</span>
                <span class="stat-sub">{pipeline_summary.get('applied', 0)} Applied • {pipeline_summary.get('screening', 0)} Screening • {pipeline_summary.get('interview', 0)} Interview</span>
            </div>
            <div class="stat-card card-purple">
                <span class="stat-label">Historical Archive</span>
                <span class="stat-value">{stats['total_jobs']}</span>
                <span class="stat-sub">{stats['stage1_passed']} Qualified European Roles</span>
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
                🗄️ Database Archive
                <span class="tab-count-badge">{len(all_db_jobs)}</span>
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
                        Contains only jobs requiring your action. Clicking <strong>[✓ Mark as Applied]</strong> transitions the job into your active Application Pipeline.
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
                {"".join(action_cards_html) if action_cards_html else '<div class="empty-state">No jobs in action queue. Check historical database or run collection.</div>'}
            </div>
        </div>

        <!-- ======================================================== -->
        <!-- TAB 2: APPLICATION PIPELINE (TRACKER)                    -->
        <!-- ======================================================== -->
        <div id="tab-pipeline" class="tab-content" style="display: none;">
            <div class="section-intro-bar">
                <div>
                    <div class="section-intro-title">Application Pipeline Tracker</div>
                    <div class="section-intro-sub">
                        Track live candidate progression from initial submission to screening, interview, and offer.
                    </div>
                </div>
            </div>

            <!-- Pipeline Metric Boxes -->
            <div class="pipeline-metrics-row">
                <div class="pipe-metric-box active" onclick="filterPipelineStage('all', this)">
                    <div class="pipe-metric-title">ALL ACTIVE</div>
                    <div class="pipe-metric-val" id="metric-pipe-all">{len(pipeline_jobs)}</div>
                </div>
                <div class="pipe-metric-box" onclick="filterPipelineStage('applied', this)">
                    <div class="pipe-metric-title">APPLIED</div>
                    <div class="pipe-metric-val" id="metric-pipe-applied">{pipeline_summary.get('applied', 0)}</div>
                </div>
                <div class="pipe-metric-box" onclick="filterPipelineStage('screening', this)">
                    <div class="pipe-metric-title">SCREENING</div>
                    <div class="pipe-metric-val" id="metric-pipe-screening">{pipeline_summary.get('screening', 0)}</div>
                </div>
                <div class="pipe-metric-box" onclick="filterPipelineStage('interview', this)">
                    <div class="pipe-metric-title">INTERVIEW</div>
                    <div class="pipe-metric-val" id="metric-pipe-interview">{pipeline_summary.get('interview', 0)}</div>
                </div>
                <div class="pipe-metric-box" onclick="filterPipelineStage('offered', this)">
                    <div class="pipe-metric-title">OFFERS</div>
                    <div class="pipe-metric-val" id="metric-pipe-offered">{pipeline_summary.get('offered', 0)}</div>
                </div>
                <div class="pipe-metric-box" onclick="filterPipelineStage('rejected', this)">
                    <div class="pipe-metric-title">REJECTED</div>
                    <div class="pipe-metric-val" id="metric-pipe-rejected">{pipeline_summary.get('rejected', 0)}</div>
                </div>
            </div>

            <!-- Pipeline Cards Container -->
            <div id="pipeline-cards-container">
                {"".join(pipeline_cards_html) if pipeline_cards_html else '<div class="empty-state" style="text-align:center; padding:40px; color:var(--text-secondary);">No applications in tracker yet. Click [✓ Mark as Applied] on any job in the Applications tab to track it here.</div>'}
            </div>
        </div>

        <!-- ======================================================== -->
        <!-- TAB 3: COMPLETE HISTORICAL DATABASE                      -->
        <!-- ======================================================== -->
        <div id="tab-database" class="tab-content" style="display: none;">
            <div class="section-intro-bar">
                <div>
                    <div class="section-intro-title">Complete Historical Database ({len(all_db_jobs)} Jobs)</div>
                    <div class="section-intro-sub">
                        Archive of every ingested and evaluated opportunity across European sources. Cleanly paginated for high-volume growth.
                    </div>
                </div>
            </div>

            <!-- Filters Grid -->
            <div class="db-controls-grid">
                <div class="db-control-group">
                    <label>Search Keyword</label>
                    <input type="text" class="db-input" id="db-search" placeholder="Company, title, skill..." oninput="filterDatabase()">
                </div>
                <div class="db-control-group">
                    <label>Status</label>
                    <select class="db-select" id="db-filter-status" onchange="filterDatabase()">
                        <option value="all">All Statuses</option>
                        <option value="prepared">Prepared (Action Queue)</option>
                        <option value="applied">Applied</option>
                        <option value="screening">Screening</option>
                        <option value="interview">Interview</option>
                        <option value="offered">Offered</option>
                        <option value="rejected">Rejected</option>
                        <option value="discovered">Discovered</option>
                    </select>
                </div>
                <div class="db-control-group">
                    <label>Company</label>
                    <select class="db-select" id="db-filter-company" onchange="filterDatabase()">
                        <option value="all">All Companies</option>
                        {company_options_html}
                    </select>
                </div>
                <div class="db-control-group">
                    <label>Career Track</label>
                    <select class="db-select" id="db-filter-track" onchange="filterDatabase()">
                        <option value="all">All Tracks</option>
                        {track_options_html}
                    </select>
                </div>
                <div class="db-control-group">
                    <label>Priority</label>
                    <select class="db-select" id="db-filter-priority" onchange="filterDatabase()">
                        <option value="all">All Priorities</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                        <option value="none">None</option>
                    </select>
                </div>
                <div class="db-control-group">
                    <label>Source</label>
                    <select class="db-select" id="db-filter-source" onchange="filterDatabase()">
                        <option value="all">All Sources</option>
                        {source_options_html}
                    </select>
                </div>
            </div>

            <!-- Database Table -->
            <div class="db-table-wrap">
                <table class="db-table">
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

            <!-- Pagination Bar -->
            <div class="pagination-bar">
                <div class="pagination-info" id="db-pagination-info">Showing 1–25 of {len(all_db_jobs)}</div>
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
                        Domain momentum tracking across {stats['total_jobs']} European engineering job postings.
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

    <!-- Toast Notification -->
    <div class="toast" id="toast">Notification message</div>

    <!-- Client-Side State & Logic -->
    <script>
        // Ingest embedded database for fast, offline-capable search and pagination
        const ALL_DB_JOBS = {db_jobs_json};
        let filteredDbJobs = [...ALL_DB_JOBS];
        let dbCurrentPage = 1;
        const dbPageSize = 25;

        // Navigation Tabs
        function switchNavTab(tabName) {{
            document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

            document.getElementById('tab-btn-' + tabName).classList.add('active');
            document.getElementById('tab-' + tabName).style.display = 'block';

            if (tabName === 'database') {{
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

            try {{
                const res = await fetch(`/api/applications/${{jobId}}/status`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ status: 'applied' }})
                }});

                if (res.ok) {{
                    const data = await res.json();
                    showToast(`✓ Job #${{jobId}} (${{company}}) marked as APPLIED and moved to Pipeline!`);
                    updatePipelineCounters(data.summary);
                }} else {{
                    throw new Error('API server not running');
                }}
            }} catch (err) {{
                // Fallback for static HTML view
                localStorage.setItem(`app_status_${{jobId}}`, 'applied');
                showToast(`✓ Job #${{jobId}} (${{company}}) marked as APPLIED (Saved locally)!`);
                incrementLocalApplied();
            }}
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

        function updatePipelineCounters(summary) {{
            if (!summary) return;
            const appliedEl = document.getElementById('metric-pipe-applied');
            const screenEl = document.getElementById('metric-pipe-screening');
            const interviewEl = document.getElementById('metric-pipe-interview');
            const offerEl = document.getElementById('metric-pipe-offered');
            const rejectEl = document.getElementById('metric-pipe-rejected');
            const allEl = document.getElementById('metric-pipe-all');
            const topEl = document.getElementById('top-pipeline-count');
            const badgeEl = document.getElementById('badge-pipeline-count');

            if (appliedEl) appliedEl.innerText = summary.applied || 0;
            if (screenEl) screenEl.innerText = summary.screening || 0;
            if (interviewEl) interviewEl.innerText = summary.interview || 0;
            if (offerEl) offerEl.innerText = summary.offered || 0;
            if (rejectEl) rejectEl.innerText = summary.rejected || 0;
            if (allEl) allEl.innerText = summary.total_pipeline || 0;
            if (badgeEl) badgeEl.innerText = summary.total_pipeline || 0;
            if (topEl) topEl.innerText = (summary.applied || 0) + (summary.screening || 0) + (summary.interview || 0);
        }}

        function incrementLocalApplied() {{
            const appliedEl = document.getElementById('metric-pipe-applied');
            const allEl = document.getElementById('metric-pipe-all');
            const topEl = document.getElementById('top-pipeline-count');
            if (appliedEl) appliedEl.innerText = (parseInt(appliedEl.innerText, 10) || 0) + 1;
            if (allEl) allEl.innerText = (parseInt(allEl.innerText, 10) || 0) + 1;
            if (topEl) topEl.innerText = (parseInt(topEl.innerText, 10) || 0) + 1;
        }}

        // Pipeline Stage Transition
        async function changePipelineStage(jobId, newStage) {{
            const card = document.getElementById('pipe-card-' + jobId);
            const badge = document.getElementById('pipe-badge-' + jobId);
            if (badge) {{
                badge.className = `stage-pill stage-${{newStage}}`;
                badge.innerText = newStage.toUpperCase();
            }}
            if (card) card.setAttribute('data-stage', newStage);

            try {{
                const res = await fetch(`/api/applications/${{jobId}}/status`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ status: newStage }})
                }});
                if (res.ok) {{
                    const data = await res.json();
                    showToast(`✓ Job #${{jobId}} transitioned to ${{newStage.toUpperCase()}}!`);
                    updatePipelineCounters(data.summary);
                }}
            }} catch (err) {{
                localStorage.setItem(`app_status_${{jobId}}`, newStage);
                showToast(`✓ Job #${{jobId}} transitioned to ${{newStage.toUpperCase()}} (saved locally).`);
            }}
        }}

        function advanceStage(jobId, targetStage) {{
            const select = document.getElementById('stage-select-' + jobId);
            if (select) select.value = targetStage;
            changePipelineStage(jobId, targetStage);
        }}

        // Filter Action Queue
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

        // Filter Pipeline Stage
        function filterPipelineStage(stage, el) {{
            document.querySelectorAll('.pipe-metric-box').forEach(b => b.classList.remove('active'));
            if (el) el.classList.add('active');

            const cards = document.querySelectorAll('#pipeline-cards-container .pipeline-card');
            cards.forEach(card => {{
                const s = card.getAttribute('data-stage');
                if (stage === 'all') {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = (s === stage) ? 'block' : 'none';
                }}
            }});
        }}

        // Database Table Filtering & Pagination
        function filterDatabase() {{
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

        function escapeHtml(text) {{
            if (!text) return '';
            const map = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }};
            return text.toString().replace(/[&<>"']/g, m => map[m]);
        }}

        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3500);
        }}

        // Restore offline states if viewing without server
        window.addEventListener('DOMContentLoaded', () => {{
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
