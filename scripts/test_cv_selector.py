from analyzer.cv_selector import CVSelector


selector = CVSelector()


jobs = [

    "AI Network Engineer working on 5G RAN optimization",

    "QA Automation Engineer using API testing and Python",

    "Cybersecurity Engineer vulnerability analysis"

]


for job in jobs:

    result = selector.select(job)

    print(job)

    print(result)

    print()