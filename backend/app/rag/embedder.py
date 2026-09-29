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
        # Keep the single-text API for query embeddings and existing callers.
        return self.generate_embeddings(
            [text],
            user_id=user_id,
            document_id=document_id,
            activity=activity,
        )[0]

    # Generate multiple embeddings in one provider request.
    def generate_embeddings(
        self,
        texts: list[str],
        *,
        user_id: str | None = None,
        document_id: str | None = None,
        activity: str = "embedding",
    ) -> list[list[float]]:
        if not texts:
            return []

        # OpenAI accepts an array of strings and returns results with indexes
        # that identify the corresponding input positions.
        response = tracked_ai_call(
            lambda: self.client.embeddings.create(
                model=DEFAULT_EMBEDDING_MODEL,
                input=texts,
            ),
            activity=activity,
            model=DEFAULT_EMBEDDING_MODEL,
            user_id=user_id,
            document_id=document_id,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(texts):
            raise RuntimeError(
                "Embedding response count did not match the input count."
            )
        return [item.embedding for item in ordered]
