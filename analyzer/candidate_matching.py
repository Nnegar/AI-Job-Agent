from analyzer.cv_selector import CVSelector
from analyzer.scorer import JobScorer
from analyzer.career_decision import CareerDecision


class CandidateMatcher:

    def __init__(self):
        self.cv_selector = CVSelector()
        self.scorer = JobScorer()
        self.decision = CareerDecision()


    def analyze(self, job, stage1_result):

        score_result = self.scorer.score(job)

        cv_result = self.cv_selector.select(
            job["title"] + " " + job["description"]
        )


        career_score = self.decision.calculate(
            technical_score=score_result["total_score"],
            ai_score=stage1_result.get("relevance_score", 0),
            growth_score=stage1_result.get("relevance_score", 0),
            location_score=50,
            company_score=50
        )


        return {
            "job_id": job["id"],
            "match_score": career_score,
            "recommended_cv": cv_result["recommended_cv"],
            "strengths": [],
            "skill_gaps": [],
            "apply_decision": (
                "apply"
                if career_score >= 70
                else "review"
            ),
            "reasoning": ""
        }

