import sqlite3


connection = sqlite3.connect("database/jobs.db")

cursor = connection.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS jobs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT,
    company TEXT,
    country TEXT,
    city TEXT,

    url TEXT,
    source TEXT,

    description TEXT,

    date_found TEXT

)
""")


connection.commit()
connection.close()

print("Database created successfully")