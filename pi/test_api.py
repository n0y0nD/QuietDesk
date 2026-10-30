"""One quick call to the Meta Model API to check the key works."""
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
resp = client.responses.create(model="muse-spark-1.3", input="Say hello to QuietDesk in one short sentence.")
print("Model API OK:", resp.output_text)
