# Local answer debug capture

Enabled for current testing with `RAG_DEBUG_CAPTURE_ENABLED=true`. Set it to
`false` in the backend environment configuration and restart to stop capture.
`RAG_DEBUG_CAPTURE_DIRECTORY` optionally changes the output location.

The default location is the repository's `logs/rag_debug/YYYY-MM-DD/` folder.
Each question that reaches answer generation creates one timestamped UUID JSON
file. The request is saved before calling the model and the same file is updated
with its answer or error. A `pending` file can indicate interrupted processing or
failure to save the final result. Retrieval failures before answer generation
do not have an assembled answer prompt and are not captured by this feature.

Records include the exact API request (model, reasoning effort and messages),
prompt version, question, ordered chunks and their metadata, authenticated user
and conversation IDs, timestamps, answer, provider request/response IDs and
usage/cost snapshot. The cost uses the existing calculator; it is not an extra
charge or another database usage entry. Error records include error type, HTTP
status when available and stack locations. They omit credentials, headers,
exception messages and raw error response bodies.

Backend logs contain only the capture ID/path rather than full document text.
The entire `logs/` folder is Git-ignored and has no public download endpoint.
The files contain private document content and questions; restrict access to
the host/folder. Local capture currently has no automatic expiration. Private
production storage, configurable 7/14-day retention and automatic deletion are
deferred deployment work. Disable capture until those production controls exist.

If the initial save fails while capture is enabled, answer generation stops
before its paid model call (a query embedding may already have been generated).
If final saving fails after the call, the initial evidence remains available,
an error is logged, and the answer is not regenerated.
