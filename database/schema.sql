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
-- Stage 2 Candidate-to-Job Fit Analysis
-- Evaluates candidate profile against job intelligence
-- =====================================================

CREATE TABLE IF NOT EXISTS candidate_job_analysis (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id INTEGER NOT NULL,

    match_score INTEGER,

    technical_fit_score INTEGER,

    career_track_fit_score INTEGER,

    career_growth_score INTEGER,

    ai_resilience_score INTEGER,

    seniority_fit TEXT,

    location_fit TEXT,

    primary_track TEXT,

    strengths TEXT,

    skill_gaps TEXT,

    concerns TEXT,

    reasoning TEXT,

    model TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(job_id)
        REFERENCES jobs(id),

    UNIQUE(job_id)
);

-- =====================================================
-- Stage 3 Final Application Filter & Priority Decisions
-- =====================================================

CREATE TABLE IF NOT EXISTS job_stage3_analysis (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id INTEGER NOT NULL,

    decision TEXT NOT NULL,

    priority TEXT NOT NULL,

    final_score REAL NOT NULL,

    application_method TEXT NOT NULL,

    readiness TEXT NOT NULL,

    decision_reasons TEXT NOT NULL,

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