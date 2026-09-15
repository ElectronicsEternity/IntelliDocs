import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Session } from '@supabase/supabase-js'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, useAuth } from './AuthProvider'

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  updateUser: vi.fn(),
  signOut: vi.fn(),
}))

vi.mock('../lib/supabase', () => ({ supabase: { auth } }))

const session = { access_token: 'fresh-access-token' } as Session

function Harness() {
  const { session: currentSession, signIn, signOut } = useAuth()
  return (
    <>
      <span>{currentSession?.access_token ?? 'no-session'}</span>
      <button onClick={() => void signIn('person@example.com', 'password123')}>Sign in</button>
      <button onClick={() => void signOut()}>Sign out</button>
    </>
  )
}

describe('AuthProvider session handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    auth.signOut.mockResolvedValue({ error: null })
  })

  it('installs the returned sign-in session without waiting for an auth event', async () => {
    auth.getSession.mockResolvedValue({ data: { session: null }, error: null })
    auth.signInWithPassword.mockResolvedValue({ data: { session }, error: null })
    render(<AuthProvider><Harness /></AuthProvider>)

    await waitFor(() => expect(screen.getByText('no-session')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('fresh-access-token')).toBeInTheDocument())
  })

  it('clears a revoked session as soon as sign-out completes', async () => {
    auth.getSession.mockResolvedValue({ data: { session }, error: null })
    render(<AuthProvider><Harness /></AuthProvider>)

    await waitFor(() => expect(screen.getByText('fresh-access-token')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(screen.getByText('no-session')).toBeInTheDocument())
  })
})
