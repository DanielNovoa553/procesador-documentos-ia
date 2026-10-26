import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
modelo = os.getenv("GEMINI_MODEL")

if not api_key or not modelo:
    raise SystemExit("Falta GEMINI_API_KEY o GEMINI_MODEL en tu archivo .env")

client = genai.Client(api_key=api_key)

respuesta = client.models.generate_content(
    model=modelo,
    contents="Responde solo con la palabra: listo",
)

print("Respuesta de Gemini:", respuesta.text)