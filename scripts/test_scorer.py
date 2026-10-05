from analyzer.scorer import JobScorer


job = {

    "title":
    "AI Network Automation Engineer",

    "description":
    """
    Working on 5G RAN optimization,
    machine learning models,
    Python automation and network analytics.
    """
}


scorer = JobScorer()

result = scorer.score(job)


print(result)