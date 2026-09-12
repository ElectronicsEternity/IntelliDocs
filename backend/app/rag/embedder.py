# Import OpenAI client
from openai import OpenAI

# Import application settings
from app.config import settings


class Embedder:
    # Constructor
    def __init__(self):

        # Create OpenAI client
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )


    # Generate embedding from text
    def generate_embedding(
        self,
        text: str
    ) -> list[float]:

        # Request embedding from OpenAI
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        # Return embedding vector
        return response.data[0].embedding
