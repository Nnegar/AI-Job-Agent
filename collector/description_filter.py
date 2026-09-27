import re

from collector.description_extractor import clean_description


SIGNALS = {
    "networking": [
        r"(?:troubleshoot|diagnos\w*|monitor\w*|configur\w*|optimiz\w*|automat\w*|deploy\w*|design\w*).{0,110}(?:network|BGP|DNS|routing|firewall|WAN|RAN|5G|wireless|connectivity|DDoS)",
        r"(?:network|BGP|DNS|routing|firewall|WAN|RAN|5G|wireless|connectivity|DDoS).{0,110}(?:troubleshoot|diagnos\w*|monitor\w*|configur\w*|optimiz\w*|automat\w*|deploy\w*|design\w*)",
        r"\b(?:network automation|network monitoring|RAN optimization|IP backbone)\b",
    ],

    "quality_engineering": [
        r"\b(?:test automation|automated testing|regression testing|QA engineer|quality assurance|software testing|test strategy|test framework|test plan)\b",
        r"\b(?:write|develop|create|design|maintain|execute|automate).{0,70}(?:regression|integration|functional|performance|end.to.end) tests?\b",
    ],

    "cybersecurity": [
        r"\b(?:detect|investigat\w*|mitigat\w*|respond|triage|remediat\w*|assess|monitor).{0,110}(?:vulnerabilit\w*|threat|security incident|malware|intrusion|attack)",
        r"\b(?:vulnerabilit\w*|threat|security incident|malware|intrusion|attack).{0,110}(?:detect|investigat\w*|mitigat\w*|respond|triage|remediat\w*|assess|monitor)",
        r"\b(?:vulnerability management|penetration testing|incident response|threat detection|security testing)\b",
    ],

    "applied_ai": [
        r"\b(?:develop|build|design|train|evaluate|deploy|fine.tune|implement|optimiz\w*).{0,100}(?:machine.learning model|ML model|ML pipeline|LLM application|RAG pipeline|AI agent|predictive model)",
        r"\b(?:machine.learning model|ML model|ML pipeline|LLM application|RAG pipeline|AI agent|predictive model).{0,100}(?:develop|build|design|train|evaluate|deploy|fine.tune|implement|optimiz\w*)",
        r"\b(?:MLOps|model training|model deployment|ML pipeline|RAG pipeline)\b",
    ],

    "embedded_iot": [
        r"\b(?:firmware development|embedded system|signal processing|RF design|IoT device)\b",
        r"\b(?:design|develop|debug|test|integrat\w*).{0,100}(?:firmware|microcontroller|embedded device|RF circuit)",
    ],
}


SIGNALS = {
    category: [re.compile(pattern, re.I) for pattern in patterns]
    for category, patterns in SIGNALS.items()
}


FOOTER = re.compile(
    r"^(?:benefits(?: and growth)?|compensation|equity|"
    r"equal opportunity|privacy notice)\s*:?$",
    re.I,
)


def analyze_description(description):
    lines = clean_description(description or "").splitlines()

    evidence = {}

    for line in lines:

        if FOOTER.match(line.strip()):
            break

        for category, patterns in SIGNALS.items():

            if any(pattern.search(line) for pattern in patterns):

                evidence.setdefault(category, [])

                if len(evidence[category]) < 2:

                    if line not in evidence[category]:
                        evidence[category].append(
                            line[:250]
                        )

    return evidence
