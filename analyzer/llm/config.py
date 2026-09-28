LLM_CONFIG = {
    "provider": "openrouter",

    # Common generation settings.
    "temperature": 0.2,

    # =========================================================
    # Stage 1
    # =========================================================
    #
    # Stage 1 is JOB-ONLY intelligence.
    # It uses free OpenRouter models.
    #
    # IMPORTANT:
    # - Each model is attempted at most once for a job.
    # - The last successful model is tried first on the next job.
    # - The client never retries the same model for the same job.
    # - stage1_max_requests_per_job is a HARD per-job cap.
    #

    "stage1_max_requests_per_job": 8,
    "stage1_max_requests_per_day": 950,
    "stage1_max_requests_per_minute": 18,
    "stage1_max_output_tokens": 2000,

    # If every configured model is temporarily cooling down,
    # wait this long at most before stopping the current run.
    "stage1_max_wait_for_models_seconds": 120,

    "stage1_models": [

        # =========================================================
        # PAID PRIMARY MODELS
        #
        # Used first for reliability.
        # Free models remain available as fallbacks.
        # =========================================================

        {
            "name": "google/gemma-4-31b-it",
            "structured_output": "json_schema",
        },

        {
            "name": "deepseek/deepseek-v4-flash-0731",
            "structured_output": "json_schema",
        },

        # =========================================================
        # FREE FALLBACK MODELS
        # =========================================================

        {
            "name": "qwen/qwen3.8-27b:free",
            "structured_output": "json_schema",
        },

        {
            "name": "stealth/space-bunny-alpha:free",
            "structured_output": "json_object",
        },

        {
            "name": "google/gemma-4-26b-a4b-it:free",
            "structured_output": "json_object",
        },

        {
            "name": "poolside/laguna-s-2.1:free",
            "structured_output": "json_object",
        },

        {
            "name": "qwen/qwen3-8b:free",
            "structured_output": "json_object",
        },

        {
            "name": "nvidia/nemotron-3-super-120b-a12b:free",
            "structured_output": "json_schema",
        },

        {
            "name": "cohere/north-mini-code:free",
            "structured_output": "json_object",
        },

        {
            "name": "inclusionai/ling-3.0-flash-fin:free",
            "structured_output": "json_object",
        },

        {
            "name": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "structured_output": "json_object",
        },

        {
            "name": "openrouter/free",
            "structured_output": "json_schema",
        },
    ],
    # =========================================================
    # Stage 2
    # =========================================================
    #
    # Candidate matching / CV selection / deeper analysis.
    # Paid but inexpensive compared with frontier models.
    #
    # Stage 2 is NOT used by Stage 1.
    #
    "stage2_models": [
        {
            "name": "openai/gpt-4.1-mini",
            "structured_output": "json_schema",
        },
        {
            "name": "openai/gpt-4.1-nano",
            "structured_output": "json_schema",
        },
        {
            "name": "google/gemini-3.7-flash",
            "structured_output": "json_schema",
        },
    ],
}


LLM_RUNTIME_CONFIG = {
    # Persistent runtime state.
    # Add runtime/stage1_runtime.json to .gitignore.
    "state_path": "runtime/stage1_runtime.json",

    # Keep a safety margin below OpenRouter's current
    # 20 requests/minute free-model limit.
    "requests_per_minute": 18,
    
    # Stop trying more models for the current job after
    # this many consecutive upstream 429 responses.
    "max_consecutive_rate_limits": 2,

    # Keep a safety margin below the 1,000/day ceiling.
    "daily_request_limit": 950,

    # Model-specific cooldowns.
    "rate_limit_cooldown_seconds": 90,
    "temporary_error_cooldown_seconds": 45,
    "output_error_cooldown_seconds": 120,
    "unavailable_model_cooldown_seconds": 3600,
}
