import os
import json

from dotenv import load_dotenv
from openai import OpenAI
from openai import RateLimitError, APIConnectionError, APITimeoutError, APIStatusError

from analyzer.prompts.cover_letter_prompt import build_cover_letter_prompt
from analyzer.llm.base import LLMAnalyzer
from analyzer.llm.config import LLM_CONFIG
from analyzer.prompts.job_analysis_prompt import JOB_ANALYSIS_PROMPT


load_dotenv()


class OpenRouterClient(LLMAnalyzer):


    def __init__(self):

        self.client = OpenAI(

            base_url="https://openrouter.ai/api/v1",

            api_key=os.getenv(
                "OPENROUTER_API_KEY"
            )

        )



    def analyze_job(
        self,
        job,
        profile
    ):


        prompt = JOB_ANALYSIS_PROMPT.format(

            profile=profile,

            job=job

        )


        last_error = None


        for model in LLM_CONFIG["models"]:

            try:

                print(
                    f"Trying model: {model}"
                )


                response = self.client.chat.completions.create(

                    model=model,

                    messages=[

                        {
                            "role": "user",
                            "content": prompt
                        }

                    ],

                    temperature=LLM_CONFIG["temperature"]

                )


                content = response.choices[0].message.content


                print(
                    f"Successful model: {model}"
                )


                return json.loads(content)



            except Exception as error:


                last_error = error


                print(
                    f"Model failed: {model}"
                )


                continue



        raise last_error
    
    
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

        for model in LLM_CONFIG["models"]:

            try:

                print(f"Trying model: {model}")

                response = self.client.chat.completions.create(

                    model=model,

                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],

                    temperature=LLM_CONFIG["temperature"]

                )

                content = response.choices[0].message.content

                if not content or not content.strip():
                    raise ValueError("Model returned empty content")

                print(f"Successful model: {model}")

                return content.strip()

            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                ValueError
            ) as error:

                last_error = error

                print(f"Model failed: {model}")

            except APIStatusError as error:

                if error.status_code not in (500, 502, 503, 504):
                    raise

                last_error = error

                print(f"Model unavailable: {model}")

        raise RuntimeError(
            "All cover-letter models failed"
        ) from last_error