import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'

export function ForgotPasswordPage() {
  const { requestPasswordReset } = useAuth()
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await requestPasswordReset(email.trim())
      setSent(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to send the reset email. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-intro">
        <Link className="brand brand-light" to="/auth" aria-label="IntelliDocs sign in"><span className="brand-mark">I</span>IntelliDocs</Link>
        <div><p className="eyebrow">Account recovery</p><h1>Get back to your documents.</h1><p className="auth-lead">We’ll send a secure recovery link to your registered email address.</p></div>
        <p className="auth-footnote">Private workspace · Secure recovery</p>
      </section>
      <section className="auth-form-panel">
        <div className="auth-card">
          <p className="eyebrow">Password recovery</p>
          <h2>{sent ? 'Check your email' : 'Reset your password'}</h2>
          {sent ? (
            <>
              <p className="muted">If an account exists for <strong>{email}</strong>, a password-reset link has been sent. Check your inbox and spam folder.</p>
              <Link className="secondary-button link-button full-width" to="/auth">Back to sign in</Link>
            </>
          ) : (
            <form onSubmit={handleSubmit}>
              <p className="muted">Enter the email address associated with your IntelliDocs account.</p>
              <label>Email address<input autoComplete="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" required type="email" value={email} /></label>
              {error && <p className="notice notice-error">{error}</p>}
              <button className="primary-button full-width" disabled={submitting} type="submit">{submitting ? 'Sending…' : 'Send reset link'}</button>
              <Link className="auth-back-link" to="/auth">← Back to sign in</Link>
            </form>
          )}
        </div>
      </section>
    </main>
  )
}
