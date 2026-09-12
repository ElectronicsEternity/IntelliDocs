from pathlib import Path, PurePosixPath
import re

from supabase import Client, create_client

from app.config import settings


class SupabaseDocumentStorage:
    def __init__(self, client: Client | None = None) -> None:
        if client is None:
            if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError("Supabase Storage is not configured.")
            client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
        self.client = client
        self.bucket = settings.SUPABASE_STORAGE_BUCKET

    @staticmethod
    def build_path(user_id: str, document_id: str, filename: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
        if not safe_name:
            safe_name = "document.pdf"
        return str(
            PurePosixPath("users", user_id, "documents", document_id, safe_name)
        )

    def upload(self, path: str, content: bytes) -> None:
        self.client.storage.from_(self.bucket).upload(
            path=path,
            file=content,
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )

    def download(self, path: str) -> bytes:
        return self.client.storage.from_(self.bucket).download(path)

    def delete(self, path: str) -> None:
        self.client.storage.from_(self.bucket).remove([path])
