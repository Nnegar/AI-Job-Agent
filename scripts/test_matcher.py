import yaml

from analyzer.rule_matcher import RuleBasedMatcher


with open("profile/career_profile.yaml") as file:
    profile = yaml.safe_load(file)


job = {
    "title": "5G Network Automation Engineer",
    "description": "Python automation for RAN optimization and network analytics"
}


matcher = RuleBasedMatcher()

result = matcher.analyze(
    job,
    profile
)


print(result)