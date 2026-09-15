import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { ForgotPasswordPage } from './ForgotPasswordPage'

const requestPasswordReset = vi.fn().mockResolvedValue(undefined)
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ requestPasswordReset }) }))

describe('ForgotPasswordPage', () => {
  it('requests a recovery email without revealing whether the account exists', async () => {
    render(<MemoryRouter><ForgotPasswordPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'user@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => expect(requestPasswordReset).toHaveBeenCalledWith('user@example.com'))
    expect(screen.getByRole('heading', { name: 'Check your email' })).toBeInTheDocument()
    expect(screen.getByText(/If an account exists/)).toBeInTheDocument()
  })
})
