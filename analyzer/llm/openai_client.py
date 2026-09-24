import os
import json

from dotenv import load_dotenv
from openai import OpenAI

from analyzer.llm.base import LLMAnalyzer
from analyzer.prompts.job_analysis_prompt import JOB_ANALYSIS_PROMPT


load_dotenv()


class OpenAIClient(LLMAnalyzer):


    def __init__(self):

        self.client = OpenAI(
            api_key=os.getenv(
                "OPENAI_API_KEY"
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


        response = self.client.chat.completions.create(

            model="gpt-4.1-mini",

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0.2
        )


        content = response.choices[0].message.content

        return json.loads(content)
