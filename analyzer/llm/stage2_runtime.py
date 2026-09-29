import json
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from analyzer.llm.config import LLM_STAGE2_RUNTIME_CONFIG


class Stage2DailyLimitReached(RuntimeError):
    """The Stage 2 daily request safety limit has been reached."""


class Stage2NoAvailableModels(RuntimeError):
    """No configured Stage 2 model is currently available."""


class Stage2JobRequestLimitReached(RuntimeError):
    """The hard per-job Stage 2 request limit has been reached."""


class Stage2ConsecutiveRateLimitReached(RuntimeError):
    """The current job encountered too many consecutive rate limits."""


class Stage2Runtime:
    """
    Persistent runtime controller for Stage 2.

    Tracks:
    - daily request count
    - rolling 60-second request timestamps
    - preferred / last successful paid model
    - per-model cooldowns

    Runtime state is persisted to disk so restarts preserve state.
    """

    def __init__(self):
        self.state_path = Path(LLM_STAGE2_RUNTIME_CONFIG["state_path"])
        self.requests_per_minute = int(
            LLM_STAGE2_RUNTIME_CONFIG["requests_per_minute"]
        )
        self.daily_request_limit = int(
            LLM_STAGE2_RUNTIME_CONFIG["daily_request_limit"]
        )
        self.max_consecutive_rate_limits = int(
            LLM_STAGE2_RUNTIME_CONFIG.get("max_consecutive_rate_limits", 2)
        )
        self.rate_limit_cooldown_seconds = int(
            LLM_STAGE2_RUNTIME_CONFIG["rate_limit_cooldown_seconds"]
        )
        self.temporary_error_cooldown_seconds = int(
            LLM_STAGE2_RUNTIME_CONFIG["temporary_error_cooldown_seconds"]
        )
        self.output_error_cooldown_seconds = int(
            LLM_STAGE2_RUNTIME_CONFIG["output_error_cooldown_seconds"]
        )
        self.unavailable_model_cooldown_seconds = int(
            LLM_STAGE2_RUNTIME_CONFIG["unavailable_model_cooldown_seconds"]
        )

        self._lock = Lock()
        self.state = self._load()

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d")

    def _default_state(self) -> Dict[str, Any]:
        return {
            "date": self._today(),
            "daily_requests": 0,
            "request_timestamps": [],
            "last_successful_model": None,
            "model_cooldowns": {},
        }

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Runtime state must be a JSON object.")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            data = self._default_state()

        if data.get("date") != self._today():
            data["date"] = self._today()
            data["daily_requests"] = 0
            data["request_timestamps"] = []

        data.setdefault("daily_requests", 0)
        data.setdefault("request_timestamps", [])
        data.setdefault("last_successful_model", None)
        data.setdefault("model_cooldowns", {})
        return data

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )
        temp_path.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(self.state_path)

    def _purge(self, now: Optional[float] = None) -> None:
        if now is None:
            now = time.time()

        if self.state.get("date") != self._today():
            self.state["date"] = self._today()
            self.state["daily_requests"] = 0
            self.state["request_timestamps"] = []

        self.state["request_timestamps"] = [
            ts
            for ts in self.state.get("request_timestamps", [])
            if now - ts < 60
        ]

        self.state["model_cooldowns"] = {
            model: cd
            for model, cd in self.state.get("model_cooldowns", {}).items()
            if cd > now
        }

    def before_request(
        self,
        model_name: str,
        job_attempt: Optional[int] = None,
        job_limit: Optional[int] = None,
    ) -> None:
        """
        Reserve one request. Enforce daily and rolling RPM limits.
        """
        while True:
            wait_seconds = 0
            with self._lock:
                now = time.time()
                self._purge(now)

                if self.state["daily_requests"] >= self.daily_request_limit:
                    raise Stage2DailyLimitReached(
                        f"Stage 2 daily request limit reached: "
                        f"{self.state['daily_requests']}/{self.daily_request_limit}."
                    )

                timestamps = self.state["request_timestamps"]
                if len(timestamps) >= self.requests_per_minute:
                    wait_seconds = max(0.1, 60 - (now - timestamps[0]) + 0.1)
                    print(
                        f"Stage 2 RPM limit reached: {len(timestamps)}/{self.requests_per_minute}. "
                        f"Waiting {wait_seconds:.1f}s..."
                    )
                else:
                    self.state["daily_requests"] += 1
                    self.state["request_timestamps"].append(now)
                    self._save()

                    job_info = (
                        f" | job attempt {job_attempt}/{job_limit}"
                        if job_attempt and job_limit
                        else ""
                    )
                    print(
                        f"Stage 2 request {self.state['daily_requests']}/{self.daily_request_limit} today | "
                        f"{len(self.state['request_timestamps'])}/{self.requests_per_minute} in last 60s"
                        f"{job_info}"
                    )
                    return

            time.sleep(wait_seconds)

    def mark_success(self, model_name: str) -> None:
        with self._lock:
            self._purge()
            self.state["last_successful_model"] = model_name
            self.state["model_cooldowns"].pop(model_name, None)
            self._save()

    def mark_failure(self, model_name: str, error: Exception) -> None:
        error_text = str(error).lower()

        if (
            "429" in error_text
            or "rate limit" in error_text
            or "rate-limit" in error_text
        ):
            cooldown = self.rate_limit_cooldown_seconds
            reason = "rate-limited"
        elif (
            "403" in error_text
            or "404" in error_text
            or "unavailable" in error_text
            or "unsupported" in error_text
            or "response_format" in error_text
        ):
            cooldown = self.unavailable_model_cooldown_seconds
            reason = "unavailable/unsupported"
        elif (
            "invalid json" in error_text
            or "json" in error_text
            or "no choices" in error_text
            or "empty content" in error_text
            or "truncated" in error_text
            or "finish_reason=length" in error_text
        ):
            cooldown = self.output_error_cooldown_seconds
            reason = "invalid/truncated output"
        else:
            cooldown = self.temporary_error_cooldown_seconds
            reason = "temporary error"

        with self._lock:
            now = time.time()
            self._purge(now)
            cooldown_until = now + cooldown
            current = self.state["model_cooldowns"].get(model_name, 0)
            self.state["model_cooldowns"][model_name] = max(
                current, cooldown_until
            )
            self._save()

        print(f"Cooling down {model_name} for {cooldown}s ({reason}).")

    def ordered_models(self, models: List[Any]) -> List[Any]:
        """
        Return available models not on cooldown, with preferred model first.
        """
        with self._lock:
            self._purge()
            now = time.time()

            available = []
            for config in models:
                name = self._model_name(config)
                cooldown_until = self.state["model_cooldowns"].get(name, 0)
                if cooldown_until <= now:
                    available.append(config)

            preferred = self.state.get("last_successful_model")
            if not preferred:
                return available

            preferred_cfg = next(
                (c for c in available if self._model_name(c) == preferred), None
            )
            if not preferred_cfg:
                return available

            remaining = [
                c for c in available if self._model_name(c) != preferred
            ]
            return [preferred_cfg, *remaining]

    @staticmethod
    def _model_name(model_config: Any) -> str:
        if isinstance(model_config, str):
            return model_config
        return model_config["name"]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            self._purge()
            return {
                "date": self.state["date"],
                "daily_requests": self.state["daily_requests"],
                "daily_limit": self.daily_request_limit,
                "requests_last_60s": len(self.state["request_timestamps"]),
                "rpm_limit": self.requests_per_minute,
                "last_successful_model": self.state.get(
                    "last_successful_model"
                ),
                "cooldowns": dict(self.state["model_cooldowns"]),
            }


_STAGE2_RUNTIME = None


def get_stage2_runtime() -> Stage2Runtime:
    global _STAGE2_RUNTIME
    if _STAGE2_RUNTIME is None:
        _STAGE2_RUNTIME = Stage2Runtime()
    return _STAGE2_RUNTIME
