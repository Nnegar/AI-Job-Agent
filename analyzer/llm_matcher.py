from analyzer.matcher import JobMatcher


class LLMMatcher(JobMatcher):

    def analyze(self, job, profile):

        raise NotImplementedError(
            "LLM analysis not implemented yet"
        )