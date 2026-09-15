import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthPage } from './AuthPage'

const { signIn, signUp } = vi.hoisted(() => ({
  signIn: vi.fn(),
  signUp: vi.fn(),
}))

vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({
    session: null,
    signIn,
    signUp,
  }),
}))

describe('AuthPage', () => {
  beforeEach(() => {
    signIn.mockReset()
    signUp.mockReset()
  })

  it('lets the user show and hide their password', () => {
    render(<MemoryRouter><AuthPage /></MemoryRouter>)
    const password = screen.getByLabelText('Password')

    expect(password).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(password).toHaveAttribute('type', 'password')
  })

  it('provides a password-recovery route', () => {
    render(<MemoryRouter><AuthPage /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/forgot-password')
  })

  it('uses a privacy-safe message after sign-up', async () => {
    signUp.mockResolvedValue({ needsEmailConfirmation: true })
    render(<MemoryRouter><AuthPage /></MemoryRouter>)

    fireEvent.click(screen.getAllByRole('button', { name: 'Create account' }).at(-1)!)
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'person@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Create account' }).at(-1)!)

    await waitFor(() => expect(signUp).toHaveBeenCalledWith('person@example.com', 'password123'))
    expect(screen.getByText('Sign-up request received. Check your email for next steps.')).toBeInTheDocument()
    expect(screen.queryByText(/Account created/)).not.toBeInTheDocument()
  })
})
