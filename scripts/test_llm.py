from analyzer.llm.openrouter_client import OpenRouterClient


job = """
AI Network Engineer.

Responsibilities:
- 5G RAN optimization
- machine learning models
- Python automation
- network analytics
"""


profile = """
Telecommunications engineer with:
- MSc in Telecommunication Engineering
- 5G network analysis experience
- Python skills
- QA experience
- Moving toward AI engineering and automation roles
"""


client = OpenRouterClient()


result = client.analyze_job(
    job,
    profile
)


print(result)
