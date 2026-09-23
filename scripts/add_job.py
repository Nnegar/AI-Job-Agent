import sqlite3


connection = sqlite3.connect("database/jobs.db")

cursor = connection.cursor()


cursor.execute(
    """
    INSERT INTO jobs
    (
        title,
        company,
        country,
        city,
        url,
        source,
        description,
        date_found
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        "QA Automation Engineer",
        "Siemens",
        "Germany",
        "Munich",
        "https://example.com",
        "Company Website",
        "API testing and automation for industrial software",
        "2026-09-23"
    )
)


connection.commit()
connection.close()


print("Job added successfully")