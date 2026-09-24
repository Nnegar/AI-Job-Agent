class CareerDecision:


    def __init__(self):

        self.weights = {

            "technical": 0.20,

            "ai_resilience": 0.30,

            "career_growth": 0.30,

            "location": 0.15,

            "company": 0.05

        }



    def calculate(
        self,
        technical_score,
        ai_score,
        growth_score,
        location_score,
        company_score
    ):


        final_score = (

            technical_score * self.weights["technical"]

            +

            ai_score * self.weights["ai_resilience"]

            +

            growth_score * self.weights["career_growth"]

            +

            location_score * self.weights["location"]

            +

            company_score * self.weights["company"]

        )


        return round(final_score, 2)