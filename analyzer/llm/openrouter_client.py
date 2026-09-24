import os
import json

from dotenv import load_dotenv
from openai import OpenAI

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