-- =====================================================
-- Jobs collected from job sources
-- =====================================================

CREATE TABLE IF NOT EXISTS jobs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source TEXT NOT NULL,

    source_job_id TEXT NOT NULL,

    company TEXT,

    title TEXT,

    location TEXT,

    url TEXT UNIQUE,

    description TEXT,

    requirements TEXT,

    posted_at TEXT,

    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source, source_job_id)
);



-- =====================================================
-- Stage 1 AI Job Intelligence Analysis
-- Understands the job itself, without candidate profile
-- =====================================================

CREATE TABLE IF NOT EXISTS job_ai_analysis (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id INTEGER NOT NULL,

    relevance_score INTEGER,

    career_tracks TEXT,

    role_category TEXT,

    seniority TEXT,

    location_assessment TEXT,

    summary TEXT,

    why_relevant TEXT,

    concerns TEXT,

    recommendation TEXT,

    model TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(job_id)
        REFERENCES jobs(id),

    UNIQUE(job_id)
);



-- =====================================================
-- Stage 2 Candidate Matching
-- Uses personal profile + CV
-- =====================================================

CREATE TABLE IF NOT EXISTS candidate_job_analysis (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id INTEGER NOT NULL,

    match_score INTEGER,

    recommended_cv TEXT,

    strengths TEXT,

    skill_gaps TEXT,

    apply_decision TEXT,

    reasoning TEXT,

    cover_letter TEXT,

    model TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(job_id)
        REFERENCES jobs(id),

    UNIQUE(job_id)
);



-- =====================================================
-- Application tracking
-- =====================================================

CREATE TABLE IF NOT EXISTS applications (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id INTEGER NOT NULL,

    status TEXT DEFAULT 'discovered',

    application_url TEXT,

    applied_date TIMESTAMP,

    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(job_id)
        REFERENCES jobs(id),

    UNIQUE(job_id)
);