import yaml


class JobScorer:


    def __init__(self):

        with open("profile/scoring.yaml") as file:
            self.config = yaml.safe_load(file)



    def score(self, job):

        text = (
            job["title"] +
            " " +
            job["description"]
        ).lower()


        result = {}

        total = 0


        for group, data in self.config["skill_groups"].items():

            matched = []

            for keyword in data["keywords"]:

                if keyword.lower() in text:
                    matched.append(keyword)


            group_score = min(
                len(matched) * 5,
                data["weight"]
            )


            result[group] = {
                "score": group_score,
                "matched": matched
            }


            total += group_score


        result["total_score"] = min(total,100)

        return result