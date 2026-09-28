import json
import time
from pathlib import Path
from threading import Lock

from analyzer.llm.config import LLM_RUNTIME_CONFIG


class Stage1DailyLimitReached(RuntimeError):
    """The Stage 1 daily request safety limit has been reached."""


class Stage1NoAvailableModels(RuntimeError):
    """No configured Stage 1 model is currently available."""


class Stage1JobRequestLimitReached(RuntimeError):
    """The hard per-job Stage 1 request limit has been reached."""


class Stage1ConsecutiveRateLimitReached(RuntimeError):
    """
    The current job encountered too many consecutive
    rate-limited model responses.
    """


class Stage1Runtime:
    """
    Persistent runtime controller for Stage 1.

    Tracks:

    - daily request count
    - rolling 60-second request timestamps
    - preferred paid model
    - preferred free model
    - legacy last successful model
    - per-model cooldowns

    Model preference rules:

    1. Available paid models always come before free models.
    2. Preferred paid model comes before other paid models.
    3. Preferred free model comes before other free models.
    4. A successful free model NEVER becomes preferred over paid models.
    5. Cooldown models are excluded.

    Runtime state is persisted so restarting the script does not
    reset counters, preferences, or cooldowns.
    """

    def __init__(self):
        self.state_path = Path(
            LLM_RUNTIME_CONFIG["state_path"]
        )

        self.requests_per_minute = int(
            LLM_RUNTIME_CONFIG["requests_per_minute"]
        )

        self.daily_request_limit = int(
            LLM_RUNTIME_CONFIG["daily_request_limit"]
        )

        self.rate_limit_cooldown_seconds = int(
            LLM_RUNTIME_CONFIG["rate_limit_cooldown_seconds"]
        )

        self.max_consecutive_rate_limits = int(
            LLM_RUNTIME_CONFIG.get(
                "max_consecutive_rate_limits",
                2,
            )
        )

        self.temporary_error_cooldown_seconds = int(
            LLM_RUNTIME_CONFIG["temporary_error_cooldown_seconds"]
        )

        self.output_error_cooldown_seconds = int(
            LLM_RUNTIME_CONFIG["output_error_cooldown_seconds"]
        )

        self.unavailable_model_cooldown_seconds = int(
            LLM_RUNTIME_CONFIG["unavailable_model_cooldown_seconds"]
        )

        self._lock = Lock()
        self.state = self._load()

    # =========================================================
    # Date / state
    # =========================================================

    @staticmethod
    def _today():
        return time.strftime("%Y-%m-%d")

    @staticmethod
    def _is_free_model(model_name):
        """
        Identify free OpenRouter model slugs.

        Explicit free models normally end with ':free'.
        OpenRouter's dynamic free router is 'openrouter/free'.
        """

        if not model_name:
            return False

        return (
            model_name == "openrouter/free"
            or model_name.endswith(":free")
        )

    def _default_state(self):
        return {
            "date": self._today(),
            "daily_requests": 0,
            "request_timestamps": [],

            # Backward compatibility.
            "last_successful_model": None,

            # New explicit preferences.
            "last_successful_paid_model": None,
            "last_successful_free_model": None,

            "model_cooldowns": {},
        }

    def _load(self):
        try:
            data = json.loads(
                self.state_path.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(data, dict):
                raise ValueError(
                    "Runtime state must be a JSON object."
                )

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            ValueError,
        ):
            data = self._default_state()

        # -----------------------------------------------------
        # Reset only the daily counters when the date changes.
        # Preferences and cooldowns are intentionally preserved.
        # -----------------------------------------------------

        if data.get("date") != self._today():
            data["date"] = self._today()
            data["daily_requests"] = 0
            data["request_timestamps"] = []

        data.setdefault("daily_requests", 0)
        data.setdefault("request_timestamps", [])
        data.setdefault("last_successful_model", None)
        data.setdefault("last_successful_paid_model", None)
        data.setdefault("last_successful_free_model", None)
        data.setdefault("model_cooldowns", {})

        # -----------------------------------------------------
        # Backward compatibility / automatic migration.
        #
        # Older runtime files only had:
        #
        #     last_successful_model
        #
        # Convert that into the correct paid/free preference.
        # -----------------------------------------------------

        legacy_model = data.get("last_successful_model")

        if legacy_model:
            if self._is_free_model(legacy_model):
                if not data.get("last_successful_free_model"):
                    data["last_successful_free_model"] = legacy_model
            else:
                if not data.get("last_successful_paid_model"):
                    data["last_successful_paid_model"] = legacy_model

        return data

    def _save(self):
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )

        temp_path.write_text(
            json.dumps(
                self.state,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temp_path.replace(self.state_path)

    # =========================================================
    # Cleanup
    # =========================================================

    def _purge(self, now=None):
        if now is None:
            now = time.time()

        # Daily request counter resets at midnight.
        if self.state.get("date") != self._today():
            self.state["date"] = self._today()
            self.state["daily_requests"] = 0
            self.state["request_timestamps"] = []

        # Keep only requests from the last 60 seconds.
        self.state["request_timestamps"] = [
            timestamp
            for timestamp in self.state.get(
                "request_timestamps",
                [],
            )
            if now - timestamp < 60
        ]

        # Remove expired model cooldowns.
        self.state["model_cooldowns"] = {
            model: cooldown_until
            for model, cooldown_until in self.state.get(
                "model_cooldowns",
                {},
            ).items()
            if cooldown_until > now
        }

    # =========================================================
    # Request counters
    # =========================================================

    def before_request(
        self,
        model_name,
        job_attempt=None,
        job_limit=None,
    ):
        """
        Reserve exactly one real OpenRouter request.

        The daily counter is incremented BEFORE the API call
        because a failed request may still count against the
        provider quota.
        """

        while True:
            wait_seconds = 0

            with self._lock:
                now = time.time()
                self._purge(now)

                # -------------------------------------------------
                # Daily safety limit
                # -------------------------------------------------

                if (
                    self.state["daily_requests"]
                    >= self.daily_request_limit
                ):
                    raise Stage1DailyLimitReached(
                        "Stage 1 daily request safety limit reached: "
                        f"{self.state['daily_requests']}/"
                        f"{self.daily_request_limit}. "
                        "Stop the run and continue tomorrow."
                    )

                timestamps = self.state["request_timestamps"]

                # -------------------------------------------------
                # Rolling RPM limit
                # -------------------------------------------------

                if len(timestamps) >= self.requests_per_minute:
                    wait_seconds = max(
                        0.1,
                        60 - (now - timestamps[0]) + 0.1,
                    )

                    print(
                        "Stage 1 RPM limit reached: "
                        f"{len(timestamps)}/"
                        f"{self.requests_per_minute}. "
                        f"Waiting {wait_seconds:.1f}s..."
                    )

                else:
                    # -------------------------------------------------
                    # Reserve the request
                    # -------------------------------------------------

                    self.state["daily_requests"] += 1
                    self.state["request_timestamps"].append(now)

                    self._save()

                    job_text = ""

                    if (
                        job_attempt is not None
                        and job_limit is not None
                    ):
                        job_text = (
                            f" | job request "
                            f"{job_attempt}/{job_limit}"
                        )

                    print(
                        "Stage 1 request "
                        f"{self.state['daily_requests']}/"
                        f"{self.daily_request_limit} today | "
                        f"{len(self.state['request_timestamps'])}/"
                        f"{self.requests_per_minute} in last 60s"
                        f"{job_text}"
                    )

                    return

            time.sleep(wait_seconds)

    # =========================================================
    # Success / failure
    # =========================================================

    def mark_success(self, model_name):
        """
        Record a successful model.

        Paid and free preferences are stored separately.

        A successful paid model becomes the preferred paid model.
        A successful free model becomes the preferred free model.

        A free model can NEVER replace the preferred paid model.
        """

        with self._lock:
            self._purge()

            # Keep legacy field for compatibility.
            self.state["last_successful_model"] = model_name

            if self._is_free_model(model_name):
                self.state["last_successful_free_model"] = model_name
            else:
                self.state["last_successful_paid_model"] = model_name

            # Successful model no longer needs a cooldown.
            self.state["model_cooldowns"].pop(
                model_name,
                None,
            )

            self._save()

    def mark_failure(self, model_name, error):
        """
        Put a failing model on cooldown.

        The cooldown depends on the failure type.
        """

        error_text = str(error).lower()

        # ---------------------------------------------------------
        # Rate limit
        # ---------------------------------------------------------

        if (
            "429" in error_text
            or "rate limit" in error_text
            or "rate-limit" in error_text
        ):
            cooldown = self.rate_limit_cooldown_seconds
            reason = "rate-limited"

        # ---------------------------------------------------------
        # Model unavailable / unsupported
        # ---------------------------------------------------------

        elif (
            "403" in error_text
            or "404" in error_text
            or "unavailable" in error_text
            or "unsupported" in error_text
            or "response_format" in error_text
        ):
            cooldown = self.unavailable_model_cooldown_seconds
            reason = "unavailable/unsupported"

        # ---------------------------------------------------------
        # Invalid / truncated output
        # ---------------------------------------------------------

        elif (
            "invalid json" in error_text
            or "json" in error_text
            or "no choices" in error_text
            or "empty content" in error_text
            or "truncated" in error_text
            or "finish_reason=length" in error_text
            or "finish reason: length" in error_text
        ):
            cooldown = self.output_error_cooldown_seconds
            reason = "invalid/truncated output"

        # ---------------------------------------------------------
        # Other temporary error
        # ---------------------------------------------------------

        else:
            cooldown = self.temporary_error_cooldown_seconds
            reason = "temporary error"

        with self._lock:
            now = time.time()
            self._purge(now)

            cooldown_until = now + cooldown

            current = self.state[
                "model_cooldowns"
            ].get(
                model_name,
                0,
            )

            self.state[
                "model_cooldowns"
            ][model_name] = max(
                current,
                cooldown_until,
            )

            self._save()

        print(
            f"Cooling down {model_name} "
            f"for {cooldown}s ({reason})."
        )

    # =========================================================
    # Model ordering
    # =========================================================

    def ordered_models(self, models):
        """
        Return models in the correct Stage 1 priority order.

        Priority:

        1. Preferred paid model
        2. Other available paid models
        3. Preferred free model
        4. Other available free models

        Models currently on cooldown are excluded.

        This ordering is independent of the order in config.py.
        """

        with self._lock:
            self._purge()

            now = time.time()

            available_paid = []
            available_free = []

            for model_config in models:
                model_name = self._model_name(
                    model_config
                )

                cooldown_until = self.state[
                    "model_cooldowns"
                ].get(
                    model_name,
                    0,
                )

                if cooldown_until > now:
                    continue

                if self._is_free_model(model_name):
                    available_free.append(
                        model_config
                    )
                else:
                    available_paid.append(
                        model_config
                    )

            preferred_paid = self.state.get(
                "last_successful_paid_model"
            )

            preferred_free = self.state.get(
                "last_successful_free_model"
            )

            # -----------------------------------------------------
            # Backward compatibility:
            #
            # If the new fields somehow aren't populated but the
            # old field exists, use the old field appropriately.
            # -----------------------------------------------------

            legacy_preferred = self.state.get(
                "last_successful_model"
            )

            if legacy_preferred:
                if self._is_free_model(
                    legacy_preferred
                ):
                    if not preferred_free:
                        preferred_free = legacy_preferred
                else:
                    if not preferred_paid:
                        preferred_paid = legacy_preferred

            # -----------------------------------------------------
            # Preferred paid model
            # -----------------------------------------------------

            ordered_paid = self._put_preferred_first(
                available_paid,
                preferred_paid,
            )

            # -----------------------------------------------------
            # Preferred free model
            # -----------------------------------------------------

            ordered_free = self._put_preferred_first(
                available_free,
                preferred_free,
            )

            # -----------------------------------------------------
            # CRITICAL:
            #
            # Paid models ALWAYS come before free models.
            # -----------------------------------------------------

            return [
                *ordered_paid,
                *ordered_free,
            ]

    @staticmethod
    def _put_preferred_first(
        models,
        preferred_model,
    ):
        """
        Move the preferred model to the front if available.
        """

        if not preferred_model:
            return list(models)

        preferred_config = next(
            (
                config
                for config in models
                if Stage1Runtime._model_name(config)
                == preferred_model
            ),
            None,
        )

        if preferred_config is None:
            return list(models)

        remaining = [
            config
            for config in models
            if Stage1Runtime._model_name(config)
            != preferred_model
        ]

        return [
            preferred_config,
            *remaining,
        ]

    # =========================================================
    # Runtime information
    # =========================================================

    def seconds_until_next_model(self):
        with self._lock:
            self._purge()

            now = time.time()

            cooldowns = list(
                self.state[
                    "model_cooldowns"
                ].values()
            )

            if not cooldowns:
                return 0

            return max(
                0,
                min(cooldowns) - now,
            )

    def stats(self):
        with self._lock:
            self._purge()

            return {
                "date": self.state["date"],

                "daily_requests": self.state[
                    "daily_requests"
                ],

                "daily_limit": self.daily_request_limit,

                "requests_last_60s": len(
                    self.state[
                        "request_timestamps"
                    ]
                ),

                "rpm_limit": self.requests_per_minute,

                # Backward compatibility.
                "last_successful_model": self.state.get(
                    "last_successful_model"
                ),

                # New explicit preferences.
                "last_successful_paid_model": self.state.get(
                    "last_successful_paid_model"
                ),

                "last_successful_free_model": self.state.get(
                    "last_successful_free_model"
                ),

                "cooldowns": dict(
                    self.state[
                        "model_cooldowns"
                    ]
                ),
            }

    # =========================================================
    # Helpers
    # =========================================================

    @staticmethod
    def _model_name(model_config):
        if isinstance(model_config, str):
            return model_config

        return model_config["name"]


_STAGE1_RUNTIME = None


def get_stage1_runtime():
    global _STAGE1_RUNTIME

    if _STAGE1_RUNTIME is None:
        _STAGE1_RUNTIME = Stage1Runtime()

    return _STAGE1_RUNTIME