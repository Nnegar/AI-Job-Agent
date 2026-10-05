from analyzer.llm.openai_client import OpenAIClient


job = """
AI Network Engineer.
5G RAN optimization,
Python,
machine learning.
"""


profile = """
Telecommunication engineer with
5G experience moving toward AI.
"""


client = OpenAIClient()


result = client.analyze_job(
    job,
    profile
)


print(result)
