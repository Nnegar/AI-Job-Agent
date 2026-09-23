from analyzer.matcher import JobMatcher


class RuleBasedMatcher(JobMatcher):

    def analyze(self, job, profile):

        text = (
            job["title"] +
            " " +
            job["description"]
        ).lower()


        score = 0
        matched = []


        keywords = []

        for role in profile["target_roles"]["tier_1"].values():
            keywords.extend(
                role.get("keywords", [])
            )


        for keyword in keywords:

            if keyword.lower() in text:
                score += 5
                matched.append(keyword)


        return {
            "score": min(score, 100),
            "matched_keywords": matched
        }