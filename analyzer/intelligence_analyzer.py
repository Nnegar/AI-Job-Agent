from analyzer.scorer import JobScorer
from analyzer.cv_selector import CVSelector
from analyzer.career_decision import CareerDecision
from analyzer.llm.openrouter_client import OpenRouterClient



class JobIntelligenceAnalyzer:


    def __init__(self):

        self.scorer = JobScorer()

        self.cv_selector = CVSelector()

        self.decision = CareerDecision()

        self.llm = OpenRouterClient()



    def analyze(
        self,
        job,
        profile
    ):


        text = (

            job["title"]

            + " "

            + job["description"]

        )


        # 1. Rule-based technical analysis

        score_result = self.scorer.score(job)



        # 2. Resume selection

        cv_result = self.cv_selector.select(text)



        # 3. LLM career analysis

        llm_result = self.llm.analyze_job(

            text,

            profile

        )



        technical_score = min(score_result["total_score"] *3,100)



        career_score = self.decision.calculate(

            technical_score,

            llm_result["ai_resilience_score"],

            llm_result["career_growth_score"],

            50,

            50

        )



        return {

            "title": job["title"],


            "technical_score":
                technical_score,


            "ai_resilience_score":
                llm_result["ai_resilience_score"],


            "career_growth_score":
                llm_result["career_growth_score"],


            "career_score":
                career_score,


            "category":
                cv_result["category"],


            "recommended_cv":
                cv_result["recommended_cv"],


            "missing_skills":
                llm_result["missing_skills"],


            "strengths":
                llm_result["strengths"],


            "concerns":
                llm_result["concerns"],


            "reasoning":
                llm_result["reasoning"]

        }