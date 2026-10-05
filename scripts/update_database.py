import sqlite3


connection = sqlite3.connect("database/jobs.db")

cursor = connection.cursor()


new_columns = [
    ("category", "TEXT"),
    ("match_score", "INTEGER"),
    ("recommended_cv", "TEXT"),
    ("recommendation", "TEXT"),
    ("status", "TEXT")
]


for column, datatype in new_columns:
    cursor.execute(
        f"""
        ALTER TABLE jobs
        ADD COLUMN {column} {datatype}
        """
    )


connection.commit()
connection.close()


print("Database updated")