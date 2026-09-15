import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

type Mode = "sign-in" | "sign-up";

export function AuthPage() {
  const { session, signIn, signUp } = useAuth();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  if (session) return <Navigate to="/" replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");

    try {
      if (mode === "sign-in") {
        await signIn(email.trim(), password);
      } else {
        const result = await signUp(email.trim(), password);
        if (result.needsEmailConfirmation) {
          setMessage(
            "Sign-up request received. Check your email for next steps.",
          );
          setMode("sign-in");
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-intro">
        <a className="brand brand-light" href="/" aria-label="IntelliDocs home">
          <span className="brand-mark">I</span>
          IntelliDocs
        </a>
        <div>
          <p className="eyebrow">Your knowledge, ready to answer</p>
          <h1>Turn documents into decisions.</h1>
          <p className="auth-lead">
            Upload trusted files, process their contents, and ask focused questions in one secure workspace.
          </p>
        </div>
        <p className="auth-footnote">PDF support · Private storage · Source-backed answers</p>
      </section>

      <section className="auth-form-panel">
        <div className="auth-card">
          <p className="eyebrow">Welcome</p>
          <h2>{mode === "sign-in" ? "Sign in to continue" : "Create your account"}</h2>
          <p className="muted">
            {mode === "sign-in" ? "Access your document workspace." : "Start building your private knowledge base."}
          </p>

          <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
            <button className={mode === "sign-in" ? "active" : ""} onClick={() => setMode("sign-in")} type="button">
              Sign in
            </button>
            <button className={mode === "sign-up" ? "active" : ""} onClick={() => setMode("sign-up")} type="button">
              Create account
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            <label>
              Email address
              <input
                autoComplete="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                required
                type="email"
                value={email}
              />
            </label>
            <label>
              Password
              <span className="password-field">
                <input
                  autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
                  minLength={6}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="At least 6 characters"
                  required
                  type={showPassword ? "text" : "password"}
                  value={password}
                />
                <button
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  className="password-toggle"
                  onClick={() => setShowPassword((visible) => !visible)}
                  title={showPassword ? "Hide password" : "Show password"}
                  type="button"
                >
                  {showPassword ? (
                    <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 3l18 18M10.6 10.7a2 2 0 002.7 2.7M9.9 4.2A10.8 10.8 0 0112 4c5.5 0 9 5.5 9 5.5a16 16 0 01-2.2 2.7M6.2 6.2C4.2 7.6 3 9.5 3 9.5S6.5 15 12 15c1 0 2-.2 2.8-.5"/></svg>
                  ) : (
                    <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 12s3.5-5.5 9-5.5 9 5.5 9 5.5-3.5 5.5-9 5.5S3 12 3 12z"/><circle cx="12" cy="12" r="2.5"/></svg>
                  )}
                </button>
              </span>
            </label>
            {mode === "sign-in" && (
              <div className="forgot-password-row">
                <Link to="/forgot-password">Forgot password?</Link>
              </div>
            )}
            {error && <p className="notice notice-error">{error}</p>}
            {message && <p className="notice notice-success">{message}</p>}
            <button className="primary-button full-width" disabled={submitting} type="submit">
              {submitting ? "Please wait…" : mode === "sign-in" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
