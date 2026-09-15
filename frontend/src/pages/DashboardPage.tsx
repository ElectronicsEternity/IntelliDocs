import { useMemo, useState } from 'react'

import { useAuth } from '../auth/AuthProvider'
import { ChatPanel } from '../components/ChatPanel'
import { DocumentPanel } from '../components/DocumentPanel'
import { IntelliDocsApi } from '../lib/api'
import { supabase } from '../lib/supabase'

type View = 'documents' | 'chat'

export function DashboardPage() {
  const { session, signOut } = useAuth()
  const [view, setView] = useState<View>('documents')
  const [signingOut, setSigningOut] = useState(false)
  const api = useMemo(
    () => new IntelliDocsApi(async (forceRefresh = false) => {
      const { data, error } = forceRefresh
        ? await supabase.auth.refreshSession()
        : await supabase.auth.getSession()
      if (error) return null
      return data.session?.access_token ?? null
    }, import.meta.env.VITE_API_URL ?? 'http://localhost:8000'),
    [],
  )
  const email = session?.user.email ?? 'Account'

  async function handleSignOut() {
    try {
      setSigningOut(true)
      await signOut()
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="/" aria-label="IntelliDocs home"><span className="brand-mark">I</span>IntelliDocs</a>
        <nav className="main-nav" aria-label="Workspace">
          <button className={view === 'documents' ? 'active' : ''} onClick={() => setView('documents')}>Documents</button>
          <button className={view === 'chat' ? 'active' : ''} onClick={() => setView('chat')}>Ask</button>
        </nav>
        <div className="account-menu">
          <span className="avatar" aria-hidden="true">{email.charAt(0).toUpperCase()}</span>
          <span className="account-email" title={email}>{email}</span>
          <button className="text-button" disabled={signingOut} onClick={() => void handleSignOut()}>{signingOut ? 'Signing out…' : 'Sign out'}</button>
        </div>
      </header>
      <main className="workspace">{view === 'documents' ? <DocumentPanel api={api} /> : <ChatPanel api={api} />}</main>
    </div>
  )
}
