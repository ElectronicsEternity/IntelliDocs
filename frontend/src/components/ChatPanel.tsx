import { useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { IntelliDocsApi } from "../lib/api";
import type { ChatSource } from "../types/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: ChatSource[];
};

type Props = { api: IntelliDocsApi };

function SourceContent({ source }: { source: ChatSource }) {
  if (source.content_type !== "table" || !source.table) return <p>{source.text}</p>;

  const rows = new Map<number, typeof source.table.fields>();
  for (const field of source.table.fields) {
    const fields = rows.get(field.row_start) ?? [];
    fields.push(field);
    rows.set(field.row_start, fields);
  }

  return (
    <div className="source-table">
      <p className="source-table-meta">
        Table {source.table.table_number}
        {source.table.page_numbers.length > 0 ? ` · pages ${source.table.page_numbers.join(", ")}` : ""}
      </p>
      <div className="source-table-scroll">
        <table aria-label={`Table ${source.table.table_number} from ${source.document_title ?? "document"}`}>
          <tbody>
            {[...rows.entries()].sort(([a], [b]) => a - b).map(([row, fields]) => (
              <tr key={row}>
                {fields.sort((a, b) => a.column_start - b.column_start).map((field, index) => (
                  <td
                    colSpan={field.column_end - field.column_start + 1}
                    key={`${field.column_start}-${index}`}
                    rowSpan={field.row_end - field.row_start + 1}
                  >
                    {field.value || " "}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ChatPanel({ api }: Props) {
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuestion = question.trim();
    if (!nextQuestion || submitting) return;

    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: nextQuestion }]);
    setQuestion("");
    setSubmitting(true);
    setError("");

    try {
      const response = await api.chat(nextQuestion, conversationId);
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", text: response.answer, sources: response.sources },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to answer that question.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="chat-section" aria-labelledby="chat-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Source-backed assistant</p>
          <h2 id="chat-heading">Ask IntelliDocs</h2>
          <p className="muted">Get focused answers from your processed documents.</p>
        </div>
        {messages.length > 0 && (
          <button className="secondary-button" onClick={() => { setMessages([]); setConversationId(undefined); }}>
            New conversation
          </button>
        )}
      </div>

      <div className="chat-shell">
        <div className="messages" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-state chat-empty">
              <span className="empty-icon">✦</span>
              <h3>What would you like to know?</h3>
              <p>Try asking for a summary, a key obligation, or a fact from your processed files.</p>
            </div>
          ) : messages.map((message) => (
            <article className={`message message-${message.role}`} key={message.id}>
              <span className="message-label">{message.role === "user" ? "You" : "IntelliDocs"}</span>
              {message.role === "assistant" ? (
                <div className="message-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
                </div>
              ) : <p>{message.text}</p>}
              {message.sources && message.sources.length > 0 && (
                <details className="sources">
                  <summary>{message.sources.length} source{message.sources.length === 1 ? "" : "s"}</summary>
                  {message.sources.map((source, index) => (
                    <blockquote key={`${source.document_id}-${source.page_number ?? "unknown"}-${index}`}>
                      <strong>{source.document_title ?? "Document"}{source.page_number ? ` · page ${source.page_number}` : ""}</strong>
                      <SourceContent source={source} />
                    </blockquote>
                  ))}
                </details>
              )}
            </article>
          ))}
          {submitting && <div className="message message-assistant typing">IntelliDocs is reviewing your documents…</div>}
        </div>

        {error && <p className="notice notice-error">{error}</p>}
        <form className="question-form" onSubmit={submitQuestion}>
          <label className="sr-only" htmlFor="question">Ask a question</label>
          <textarea
            id="question"
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Ask a question about your documents…"
            rows={2}
            value={question}
          />
          <button className="primary-button" disabled={!question.trim() || submitting} type="submit">Ask</button>
        </form>
      </div>
    </section>
  );
}
