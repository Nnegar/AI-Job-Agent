import json
import zipfile

from analyzer.ai_job_filter import screen_job
from collector.hybrid_filter import filter_export


CAREER_SUMMARY = """
MSc Telecommunications Engineering from Politecnico di Milano.

Experience:
- Huawei IP Backbone team:
  IP networking, troubleshooting, network operations.

- Huawei Performance team:
  5G KPI analysis, performance monitoring,
  Python reporting and data processing.

- Thesis:
  5G network analysis using Python,
  machine learning techniques and clustering.

- Current experience:
  QA testing and cybersecurity platform testing.

Career interests:
- Network automation
- Telecom AI
- Cybersecurity
- QA automation
- Applied AI engineering

Do not assume:
- production ML engineering
- penetration testing experience
- advanced software engineering experience
"""


with zipfile.ZipFile(
    "reports/full_greenhouse_export.zip"
) as archive:

    data = json.loads(
        archive.read("all_jobs.json")
    )


candidates, _, _ = filter_export(data)
candidates = candidates[:5]

print(
    f"Sending {len(candidates)} jobs to AI"
)


for index, item in enumerate(candidates, 1):

    job = item["job"]

    print(
        f"\n[{index}/{len(candidates)}]"
        f" {item['company']} - {job['title']}"
    )


    result = screen_job(
        job,
        CAREER_SUMMARY
    )


    print(
        result["decision"],
        "|",
        result["role_category"]
    )

    print(
        result["reason"]
    )

