import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("Falta GEMINI_API_KEY en tu archivo .env")

client = genai.Client(api_key=api_key)

for modelo in client.models.list():
    acciones = modelo.supported_actions or []
    if "generateContent" in acciones:
        print(modelo.name.removeprefix("models/"))