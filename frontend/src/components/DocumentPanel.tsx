import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { ApiError, type IntelliDocsApi } from "../lib/api";
import type { DocumentRecord } from "../types/api";

const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 401) return "Your session expired. Please sign in again.";
  return error instanceof Error ? error.message : "Something went wrong.";
}

type Props = { api: IntelliDocsApi };

export function DocumentPanel({ api }: Props) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function loadDocuments() {
    try {
      setError("");
      setDocuments(await api.listDocuments());
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDocuments();
  }, [api]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError("That file is larger than the 15 MB limit.");
      return;
    }

    try {
      setUploading(true);
      setError("");
      await api.uploadDocument(file);
      await loadDocuments();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setUploading(false);
    }
  }

  async function processDocument(id: string) {
    try {
      setBusyId(id);
      setError("");
      await api.processDocument(id);
      await loadDocuments();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  async function deleteDocument(document: DocumentRecord) {
    if (!window.confirm(`Delete “${document.original_filename}”? This cannot be undone.`)) return;
    try {
      setBusyId(document.id);
      setError("");
      await api.deleteDocument(document.id);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section aria-labelledby="documents-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Knowledge library</p>
          <h2 id="documents-heading">Documents</h2>
          <p className="muted">Upload and prepare PDFs before asking questions about them.</p>
        </div>
        <button className="primary-button" disabled={uploading} onClick={() => inputRef.current?.click()}>
          {uploading ? "Uploading…" : "+ Upload PDF"}
        </button>
        <input ref={inputRef} accept="application/pdf,.pdf" hidden onChange={handleUpload} type="file" />
      </div>

      {error && <p className="notice notice-error">{error}</p>}

      <div className="upload-note">
        <span className="upload-icon">↑</span>
        <div><strong>PDF files up to 15 MB</strong><p>Files stay private and are accessed through your signed-in account.</p></div>
      </div>

      {loading ? (
        <div className="empty-state"><div className="loader" /><p>Loading documents…</p></div>
      ) : documents.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">▤</span>
          <h3>Your library is empty</h3>
          <p>Upload your first PDF to begin building your knowledge base.</p>
          <button className="secondary-button" onClick={() => inputRef.current?.click()}>Choose a PDF</button>
        </div>
      ) : (
        <div className="document-grid">
          {documents.map((document) => (
            <article className="document-card" key={document.id}>
              <div className="document-card-top">
                <span className="file-icon">PDF</span>
                <span className={`status status-${document.processing_status}`}>{document.processing_status}</span>
              </div>
              <h3 title={document.original_filename}>{document.original_filename}</h3>
              <p className="document-meta">
                {formatBytes(document.file_size)} · {document.page_count ? `${document.page_count} pages · ` : ""}{formatDate(document.created_at)}
              </p>
              {document.processing_error && <p className="card-error">{document.processing_error}</p>}
              <div className="card-actions">
                {document.processing_status !== "ready" && (
                  <button
                    aria-busy={busyId === document.id || document.processing_status === "processing"}
                    className="secondary-button processing-button"
                    disabled={busyId === document.id || document.processing_status === "processing"}
                    onClick={() => void processDocument(document.id)}
                  >
                    {busyId === document.id || document.processing_status === "processing" ? (
                      <><span aria-hidden="true" className="button-spinner" />Processing…</>
                    ) : "Process"}
                  </button>
                )}
                <button className="text-button danger" disabled={busyId === document.id} onClick={() => void deleteDocument(document)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
