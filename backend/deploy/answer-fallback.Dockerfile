# Scoped patch release: keep the existing deployed runtime unchanged.
# Build from a private context containing only this Dockerfile and generator.py.
FROM asia-southeast1-docker.pkg.dev/intellidocs-510804/intellidocs/backend@sha256:2f8d982a2414021ac49b22939ee2caf196c4abef25211c2c1fa587cc56a4130b
COPY --chown=10001:10001 generator.py /app/backend/app/rag/generator.py
RUN python -c "from app.rag.generator import ANSWER_PROMPT_VERSION; assert ANSWER_PROMPT_VERSION == 'language-aware-evidence-fallback-v4'"
