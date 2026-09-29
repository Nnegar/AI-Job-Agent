import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    OpenAI,
    RateLimitError,
)

from analyzer.llm.base import LLMAnalyzer
from analyzer.llm.config import LLM_CONFIG
from analyzer.llm.stage1_runtime import (
    Stage1DailyLimitReached,
    Stage1JobRequestLimitReached,
    Stage1NoAvailableModels,
    Stage1ConsecutiveRateLimitReached,
    get_stage1_runtime,
)
from analyzer.llm.stage2_runtime import (
    Stage2DailyLimitReached,
    Stage2JobRequestLimitReached,
    Stage2NoAvailableModels,
    Stage2ConsecutiveRateLimitReached,
    get_stage2_runtime,
)
from analyzer.prompts.cover_letter_prompt import build_cover_letter_prompt
from analyzer.prompts.job_analysis_prompt import JOB_ANALYSIS_PROMPT


load_dotenv()


class OpenRouterClient(LLMAnalyzer):
    """
    Single OpenRouter client for the project.

    Stage 1:
        generate_json(..., stage="stage1")
        - free models only
        - hard max requests per job
        - no duplicate model attempt within one job
        - last successful model first
        - persistent RPM/daily counters
        - persistent per-model cooldowns

    Stage 2:
        analyze_job(...)
        generate_cover_letter(...)
        - uses the paid/cheap stage2_models configured in config.py
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set."
            )

        self.client = OpenAI(
            base_url=self.BASE_URL,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/",
                "X-Title": "AI Job Agent",
            },
        )

    # =========================================================
    # Stage 1 JSON
    # =========================================================

    def generate_json(
        self,
        *,
        prompt=None,
        messages=None,
        schema,
        schema_name=None,
        stage="stage1",
        max_requests=None,
    ):
        """
        Generate one JSON object.

        `prompt` is the primary interface used by Stage 1.
        `messages` is also accepted so future callers can use the
        normal OpenAI chat format.

        IMPORTANT:
        This method never retries the same configured model for the
        same job. Every loop iteration consumes at most one actual
        OpenRouter request.
        """

        if prompt is not None and messages is not None:
            raise ValueError(
                "Provide either 'prompt' or 'messages', not both."
            )

        if prompt is None and messages is None:
            raise ValueError(
                "generate_json requires 'prompt' or 'messages'."
            )

        if messages is None:
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]

        if stage == "stage1":
            if schema_name is None:
                schema_name = "job_intelligence"

            model_configs = LLM_CONFIG["stage1_models"]
            runtime = get_stage1_runtime()

            configured_limit = int(
                LLM_CONFIG["stage1_max_requests_per_job"]
            )

            if max_requests is None:
                max_requests = configured_limit

            max_requests = min(
                int(max_requests),
                configured_limit,
                len(model_configs),
            )

            if max_requests <= 0:
                raise ValueError(
                    "Stage 1 max_requests must be greater than zero."
                )

            return self._generate_stage1_json(
                messages=messages,
                schema=schema,
                schema_name=schema_name,
                model_configs=model_configs,
                runtime=runtime,
                max_requests=max_requests,
            )

        if stage == "stage2":
            if schema_name is None:
                schema_name = "candidate_job_analysis"

            model_configs = LLM_CONFIG["stage2_models"]
            runtime = get_stage2_runtime()

            configured_limit = int(
                LLM_CONFIG.get("stage2_max_requests_per_job", 3)
            )

            if max_requests is None:
                max_requests = configured_limit

            max_requests = min(
                int(max_requests),
                configured_limit,
                len(model_configs),
            )

            if max_requests <= 0:
                raise ValueError(
                    "Stage 2 max_requests must be greater than zero."
                )

            return self._generate_stage2_json(
                messages=messages,
                schema=schema,
                schema_name=schema_name,
                model_configs=model_configs,
                runtime=runtime,
                max_requests=max_requests,
            )

        raise ValueError(
            f"Unsupported generation stage: {stage}"
        )



    @staticmethod
    def _is_rate_limit_error(error):
        """
        Return True only when the request failed because of
        rate limiting.
        """

        if isinstance(error, RateLimitError):
            return True

        if isinstance(error, APIStatusError):
            return error.status_code == 429

        error_text = str(error).lower()

        return (
            "429" in error_text
            or "rate limit" in error_text
            or "rate-limited" in error_text
        )


    def _generate_stage1_json(
        self,
        *,
        messages,
        schema,
        schema_name="job_intelligence",
        model_configs,
        runtime,
        max_requests,
    ):
        attempted_models = set()
        attempts = 0
        consecutive_rate_limits = 0

        while attempts < max_requests:
            available = runtime.ordered_models(
                model_configs
            )

            # Never attempt the same model twice for this job.
            available = [
                config
                for config in available
                if self._model_name(config)
                not in attempted_models
            ]

            if not available:
                if attempts == 0:
                    raise Stage1NoAvailableModels(
                        "No Stage 1 model is currently available."
                    )

                raise Stage1JobRequestLimitReached(
                    "No additional Stage 1 model is available "
                    "for this job."
                )

            model_config = available[0]
            model_name = self._model_name(model_config)

            attempted_models.add(model_name)
            attempts += 1

            print(
                f"Trying model: {model_name} "
                f"(job attempt {attempts}/{max_requests})"
            )

            try:
                runtime.before_request(
                    model_name=model_name,
                    job_attempt=attempts,
                    job_limit=max_requests,
                )

                result = self._request_json(
                    model_config=model_config,
                    messages=messages,
                    schema=schema,
                    schema_name=schema_name,
                )

                runtime.mark_success(model_name)

                print(
                    f"Successful model: {model_name}"
                )

                return result, model_name

            except Stage1DailyLimitReached:
                raise

            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                APIStatusError,
                ValueError,
                json.JSONDecodeError,
            ) as error:

                runtime.mark_failure(
                    model_name,
                    error,
                )

                if self._is_rate_limit_error(error):

                    consecutive_rate_limits += 1

                    print(
                        "Consecutive Stage 1 rate limits: "
                        f"{consecutive_rate_limits}/"
                        f"{runtime.max_consecutive_rate_limits}"
                    )

                    if (
                        consecutive_rate_limits
                        >= runtime.max_consecutive_rate_limits
                    ):
                        raise Stage1ConsecutiveRateLimitReached(
                            "Stage 1 stopped this job after "
                            f"{consecutive_rate_limits} consecutive "
                            "rate-limited model responses."
                        ) from error

                else:
                    # The failures were not consecutive 429s anymore.
                    consecutive_rate_limits = 0

                print(
                    f"Model failed: {model_name} - {error}"
                )

                continue

            except Exception as error:
                runtime.mark_failure(
                    model_name,
                    error,
                )

                print(
                    f"Model failed: {model_name} - {error}"
                )

                continue

        raise Stage1JobRequestLimitReached(
            "Stage 1 exhausted the hard per-job request limit: "
            f"{attempts}/{max_requests}."
        )

    # =========================================================
    # Stage 2 JSON generation with dedicated Stage2Runtime
    # =========================================================

    def _generate_stage2_json(
        self,
        *,
        messages,
        schema,
        schema_name="candidate_job_analysis",
        model_configs,
        runtime,
        max_requests,
    ):
        attempted_models = set()
        attempts = 0
        consecutive_rate_limits = 0

        while attempts < max_requests:
            available = runtime.ordered_models(
                model_configs
            )

            # Never attempt the same model twice for this job.
            available = [
                config
                for config in available
                if self._model_name(config)
                not in attempted_models
            ]

            if not available:
                if attempts == 0:
                    raise Stage2NoAvailableModels(
                        "No Stage 2 model is currently available."
                    )

                raise Stage2JobRequestLimitReached(
                    "No additional Stage 2 model is available "
                    "for this job."
                )

            model_config = available[0]
            model_name = self._model_name(model_config)

            attempted_models.add(model_name)
            attempts += 1

            print(
                f"Trying Stage 2 model: {model_name} "
                f"(job attempt {attempts}/{max_requests})"
            )

            try:
                runtime.before_request(
                    model_name=model_name,
                    job_attempt=attempts,
                    job_limit=max_requests,
                )

                result = self._request_json(
                    model_config=model_config,
                    messages=messages,
                    schema=schema,
                    schema_name=schema_name,
                )

                runtime.mark_success(model_name)

                print(
                    f"Successful Stage 2 model: {model_name}"
                )

                return result, model_name

            except Stage2DailyLimitReached:
                raise

            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                APIStatusError,
                ValueError,
                json.JSONDecodeError,
            ) as error:

                runtime.mark_failure(
                    model_name,
                    error,
                )

                if self._is_rate_limit_error(error):

                    consecutive_rate_limits += 1

                    print(
                        "Consecutive Stage 2 rate limits: "
                        f"{consecutive_rate_limits}/"
                        f"{runtime.max_consecutive_rate_limits}"
                    )

                    if (
                        consecutive_rate_limits
                        >= runtime.max_consecutive_rate_limits
                    ):
                        raise Stage2ConsecutiveRateLimitReached(
                            "Stage 2 stopped this job after "
                            f"{consecutive_rate_limits} consecutive "
                            "rate-limited model responses."
                        ) from error

                else:
                    consecutive_rate_limits = 0

                print(
                    f"Stage 2 model failed: {model_name} - {error}"
                )

                continue

            except Exception as error:
                runtime.mark_failure(
                    model_name,
                    error,
                )

                print(
                    f"Stage 2 model failed: {model_name} - {error}"
                )

                continue

        raise Stage2JobRequestLimitReached(
            "Stage 2 exhausted the hard per-job request limit: "
            f"{attempts}/{max_requests}."
        )

    # =========================================================
    # Actual OpenRouter request
    # =========================================================

    def _request_json(
        self,
        *,
        model_config,
        messages,
        schema,
        schema_name="job_intelligence",
    ):
        model_name = self._model_name(model_config)
        output_mode = model_config.get(
            "structured_output",
            "prompt_only",
        )

        request_messages = list(messages)

        if output_mode == "prompt_only":
            request_messages = [
                {
                    "role": "system",
                    "content": (
                        "Return ONLY one valid JSON object. "
                        "Do not use Markdown fences. "
                        "Do not add explanations before or after "
                        "the JSON object."
                    ),
                },
                *request_messages,
            ]

        is_free_model = (
            model_name == "openrouter/free"
            or model_name.endswith(":free")
        )

        kwargs = {
            "model": model_name,
            "messages": request_messages,
            "temperature": LLM_CONFIG["temperature"],
            "max_tokens": (
                LLM_CONFIG["stage1_max_output_tokens"]
                if is_free_model
                else LLM_CONFIG.get("stage2_max_output_tokens", 2000)
            ),
        }

        # Native JSON enforcement where the selected model supports it.
        if output_mode == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }

            # OpenRouter-specific fields must be passed through
            # extra_body when using the OpenAI Python SDK.
            kwargs["extra_body"] = {
                "provider": {
                    "require_parameters": True,
                    "allow_fallbacks": True,
                }
            }

        elif output_mode == "json_object":
            kwargs["response_format"] = {
                "type": "json_object",
            }

            kwargs["extra_body"] = {
                "provider": {
                    "require_parameters": True,
                    "allow_fallbacks": True,
                }
            }

        response = self.client.chat.completions.create(
            **kwargs
        )

        if not response.choices:
            raise ValueError(
                "Model returned no choices."
            )

        message = response.choices[0].message
        content = message.content

        finish_reason = getattr(
            response.choices[0],
            "finish_reason",
            None,
        )

        if finish_reason == "length":
            raise ValueError(
                "Model output was truncated "
                "(finish_reason=length)."
            )

        if not content or not content.strip():
            raise ValueError(
                "Model returned empty content."
            )

        result = self._parse_json_object(
            content
        )

        self._validate_required_schema_fields(
            result,
            schema,
        )

        return result

    # =========================================================
    # Stage 2 text / candidate analysis compatibility
    # =========================================================

    def analyze_job(
        self,
        job,
        profile,
    ):
        prompt = JOB_ANALYSIS_PROMPT.format(
            profile=profile,
            job=job,
        )

        messages = [
            {
                "role": "user",
                "content": prompt,
            }
        ]

        # Stage 2 analyzers may already have their own prompt/schema.
        # Keep this legacy method simple and compatible.
        last_error = None

        for model_config in LLM_CONFIG["stage2_models"]:
            model_name = self._model_name(model_config)

            try:
                print(
                    f"Trying model: {model_name}"
                )

                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=LLM_CONFIG["temperature"],
                    max_tokens=1600,
                )

                if not response.choices:
                    raise ValueError(
                        "Model returned no choices."
                    )

                content = response.choices[0].message.content

                if not content or not content.strip():
                    raise ValueError(
                        "Model returned empty content."
                    )

                print(
                    f"Successful model: {model_name}"
                )

                return self._parse_json_object(
                    content
                )

            except Exception as error:
                last_error = error

                print(
                    f"Model failed: {model_name} - {error}"
                )

        raise RuntimeError(
            "All configured Stage 2 models failed."
        ) from last_error

    def generate_cover_letter(
        self,
        job,
        resume,
        personal_story,
        candidate_name,
    ):
        prompt = build_cover_letter_prompt(
            job=job,
            resume=resume,
            personal_story=personal_story,
            candidate_name=candidate_name,
        )

        last_error = None

        for model_config in LLM_CONFIG["stage2_models"]:
            model_name = self._model_name(model_config)

            try:
                print(
                    f"Trying model: {model_name}"
                )

                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    temperature=LLM_CONFIG["temperature"],
                    max_tokens=1600,
                )

                if not response.choices:
                    raise ValueError(
                        "Model returned no choices."
                    )

                content = response.choices[0].message.content

                if not content or not content.strip():
                    raise ValueError(
                        "Model returned empty content."
                    )

                print(
                    f"Successful model: {model_name}"
                )

                return content.strip()

            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                APIStatusError,
                ValueError,
            ) as error:
                last_error = error

                print(
                    f"Model failed: {model_name} - {error}"
                )

                continue

        raise RuntimeError(
            "All configured Stage 2 cover-letter models failed."
        ) from last_error

    # =========================================================
    # Helpers
    # =========================================================

    @staticmethod
    def _model_name(model_config):
        if isinstance(model_config, str):
            return model_config

        return model_config["name"]

    @staticmethod
    def _parse_json_object(content):
        """
        Parse JSON even when a prompt-only model wraps it in text
        or Markdown fences.
        """

        text = content.strip()

        # Remove common Markdown fences without relying on them.
        if text.startswith("```"):
            lines = text.splitlines()

            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

            if text.lower().startswith("json\n"):
                text = text[5:].lstrip()

        # First try the entire response.
        try:
            result = json.loads(text)

            if not isinstance(result, dict):
                raise ValueError(
                    "Model returned JSON that is not an object."
                )

            return result

        except json.JSONDecodeError:
            pass

        # Then find the first JSON object in surrounding text.
        decoder = json.JSONDecoder()

        for index, character in enumerate(text):
            if character != "{":
                continue

            try:
                result, _ = decoder.raw_decode(
                    text[index:]
                )

                if not isinstance(result, dict):
                    raise ValueError(
                        "Model returned JSON that is not an object."
                    )

                return result

            except json.JSONDecodeError:
                continue

        raise ValueError(
            "Invalid JSON returned by model."
        )

    @staticmethod
    def _validate_required_schema_fields(
        result,
        schema,
    ):
        """
        Small dependency-free validation layer for the fields that
        matter to this project.

        Native JSON Schema models are already constrained by
        response_format. Prompt-only models need this additional
        check before their result is accepted.
        """

        if not isinstance(result, dict):
            raise ValueError(
                "Model returned JSON that is not an object."
            )

        required = schema.get(
            "required",
            [],
        )

        for field in required:
            if field not in result:
                raise ValueError(
                    f"JSON is missing required field: {field}"
                )

        properties = schema.get(
            "properties",
            {},
        )

        for field, definition in properties.items():
            if field not in result:
                continue

            value = result[field]
            expected_type = definition.get("type")

            if expected_type == "integer":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                ):
                    raise ValueError(
                        f"Field '{field}' must be an integer."
                    )

                minimum = definition.get("minimum")
                maximum = definition.get("maximum")

                if minimum is not None and value < minimum:
                    raise ValueError(
                        f"Field '{field}' is below minimum."
                    )

                if maximum is not None and value > maximum:
                    raise ValueError(
                        f"Field '{field}' is above maximum."
                    )

            elif expected_type == "string":
                if not isinstance(value, str):
                    raise ValueError(
                        f"Field '{field}' must be a string."
                    )

                enum = definition.get("enum")
                if enum and value not in enum:
                    raise ValueError(
                        f"Field '{field}' has invalid value: "
                        f"{value!r}"
                    )

            elif expected_type == "array":
                if not isinstance(value, list):
                    raise ValueError(
                        f"Field '{field}' must be an array."
                    )

                item_definition = definition.get(
                    "items",
                    {},
                )

                item_type = item_definition.get("type")
                item_enum = item_definition.get("enum")

                for item in value:
                    if item_type == "string" and not isinstance(
                        item,
                        str,
                    ):
                        raise ValueError(
                            f"Items in '{field}' must be strings."
                        )

                    if (
                        item_enum
                        and item not in item_enum
                    ):
                        raise ValueError(
                            f"Invalid item in '{field}': "
                            f"{item!r}"
                        )

# Backward-compatible exports for old runner imports.
Stage1DailyLimitReached = Stage1DailyLimitReached
Stage1NoAvailableModels = Stage1NoAvailableModels
Stage1JobRequestLimitReached = Stage1JobRequestLimitReached
Stage2DailyLimitReached = Stage2DailyLimitReached
Stage2NoAvailableModels = Stage2NoAvailableModels
Stage2JobRequestLimitReached = Stage2JobRequestLimitReached

