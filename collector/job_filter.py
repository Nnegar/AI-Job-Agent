import re


TITLE_KEYWORDS = [

    # Telecommunications
    "network engineer",
    "network automation",
    "network intelligence",
    "telecom",
    "wireless",
    "5g",
    "ran engineer",

    # Cybersecurity
    "cybersecurity",
    "security engineer",
    "security analyst",

    # Quality engineering
    "qa engineer",
    "quality engineer",
    "test engineer",
    "test automation",
    "sdet",

    # AI and data
    "machine learning",
    "ai engineer",
    "data engineer",
    "data scientist",

    # Embedded and IoT
    "embedded engineer",
    "iot engineer",
]


def is_relevant_title(title):
    title = title.lower()

    return any(
        re.search(
            rf"\b{re.escape(keyword)}\b",
            title
        )
        for keyword in TITLE_KEYWORDS
    )