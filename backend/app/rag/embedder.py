# Import OpenAI client
from openai import OpenAI

# Import application settings
from app.config import settings
from app.constants import DEFAULT_EMBEDDING_MODEL
from app.services.usage.ai_usage import tracked_ai_call


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
        text: str,
        *,
        user_id: str | None = None,
        document_id: str | None = None,
        activity: str = "embedding",
    ) -> list[float]:

        # Request embedding from OpenAI
        response = tracked_ai_call(
            lambda: self.client.embeddings.create(model=DEFAULT_EMBEDDING_MODEL, input=text),
            activity=activity, model=DEFAULT_EMBEDDING_MODEL,
            user_id=user_id, document_id=document_id,
        )
        # Return embedding vector
        return response.data[0].embedding
