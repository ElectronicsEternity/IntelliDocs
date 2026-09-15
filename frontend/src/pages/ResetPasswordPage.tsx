import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'

export function ResetPasswordPage() {
  const { loading, session, signOut, updatePassword } = useAuth()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirmation) {
      setError('The passwords do not match.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await updatePassword(password)
      await signOut()
      setComplete(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update your password. Please request a new link.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-intro">
        <Link className="brand brand-light" to="/auth" aria-label="IntelliDocs sign in"><span className="brand-mark">I</span>IntelliDocs</Link>
        <div><p className="eyebrow">Secure recovery</p><h1>Choose a new password.</h1><p className="auth-lead">Use a password that is difficult to guess and unique to IntelliDocs.</p></div>
        <p className="auth-footnote">Your documents remain private</p>
      </section>
      <section className="auth-form-panel">
        <div className="auth-card">
          <p className="eyebrow">Account security</p>
          {loading ? <div className="inline-loader"><div className="loader" /><p>Verifying your recovery link…</p></div> : complete ? (
            <><h2>Password updated</h2><p className="muted">Your password has been changed. You can now sign in with the new password.</p><Link className="primary-button link-button full-width" to="/auth">Continue to sign in</Link></>
          ) : !session ? (
            <><h2>Link expired or invalid</h2><p className="muted">This recovery link cannot be used. Request a new password-reset email and try again.</p><Link className="primary-button link-button full-width" to="/forgot-password">Request a new link</Link></>
          ) : (
            <>
              <h2>Set a new password</h2>
              <p className="muted">Enter and confirm your new password.</p>
              <form onSubmit={handleSubmit}>
                <label>New password<span className="password-field"><input autoComplete="new-password" minLength={6} onChange={(event) => setPassword(event.target.value)} required type={showPassword ? 'text' : 'password'} value={password} /><button aria-label={showPassword ? 'Hide passwords' : 'Show passwords'} aria-pressed={showPassword} className="password-toggle" onClick={() => setShowPassword((visible) => !visible)} type="button"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 12s3.5-5.5 9-5.5 9 5.5 9 5.5-3.5 5.5-9 5.5S3 12 3 12z"/><circle cx="12" cy="12" r="2.5"/></svg></button></span></label>
                <label>Confirm new password<input autoComplete="new-password" minLength={6} onChange={(event) => setConfirmation(event.target.value)} required type={showPassword ? 'text' : 'password'} value={confirmation} /></label>
                {error && <p className="notice notice-error">{error}</p>}
                <button className="primary-button full-width" disabled={submitting} type="submit">{submitting ? 'Updating…' : 'Update password'}</button>
              </form>
            </>
          )}
        </div>
      </section>
    </main>
  )
}
