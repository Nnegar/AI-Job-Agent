import os
from dotenv import load_dotenv


load_dotenv()


key = os.getenv("OPENROUTER_API_KEY")


if key:
    print("API key loaded")
else:
    print("API key missing")