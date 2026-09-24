from analyzer.career_decision import CareerDecision


decision = CareerDecision()


score = decision.calculate(

    technical_score=80,

    ai_score=90,

    growth_score=85,

    location_score=100,

    company_score=80

)


print(score)