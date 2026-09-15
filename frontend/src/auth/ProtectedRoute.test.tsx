import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProtectedRoute } from './ProtectedRoute'

const authState = vi.hoisted(() => ({ loading: false, session: null as object | null }))
vi.mock('./AuthProvider', () => ({ useAuth: () => authState }))

describe('ProtectedRoute', () => {
  beforeEach(() => { authState.loading = false; authState.session = null })

  it('redirects signed-out users to authentication', () => {
    render(<MemoryRouter initialEntries={['/']}><Routes><Route path="/auth" element={<p>Sign in page</p>} /><Route path="/" element={<ProtectedRoute><p>Private workspace</p></ProtectedRoute>} /></Routes></MemoryRouter>)
    expect(screen.getByText('Sign in page')).toBeInTheDocument()
  })

  it('shows the workspace to signed-in users', () => {
    authState.session = {}
    render(<MemoryRouter><ProtectedRoute><p>Private workspace</p></ProtectedRoute></MemoryRouter>)
    expect(screen.getByText('Private workspace')).toBeInTheDocument()
  })
})
