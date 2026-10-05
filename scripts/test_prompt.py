from analyzer.prompts.job_analysis_prompt import JOB_ANALYSIS_PROMPT


prompt = JOB_ANALYSIS_PROMPT.format(

    profile="Telecom engineer moving toward AI",

    job="""
    AI Network Engineer.
    Work on 5G optimization,
    Python and machine learning.
    """

)


print(prompt)