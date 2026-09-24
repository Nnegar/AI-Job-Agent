from analyzer.intelligence_analyzer import JobIntelligenceAnalyzer


job = {

    "title":
    "AI Network Automation Engineer",


    "description":
    """
    Develop AI solutions for 5G RAN optimization.
    Use Python, machine learning and network analytics.
    """

}



profile = """

MSc Telecommunication Engineer.

Experience:
- 5G network analysis
- Python
- QA testing
- Cybersecurity projects

Career goal:
Move toward AI engineering,
automation and high-growth technical roles.

"""


analyzer = JobIntelligenceAnalyzer()


result = analyzer.analyze(

    job,

    profile

)


print(result)