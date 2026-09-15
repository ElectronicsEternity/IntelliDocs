import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { IntelliDocsApi } from '../lib/api'
import type { DocumentRecord } from '../types/api'
import { DocumentPanel } from './DocumentPanel'

const documentRecord: DocumentRecord = {
  id: 'document-1',
  original_filename: 'handbook.pdf',
  storage_path: 'users/user-1/documents/document-1/handbook.pdf',
  file_size: 1024,
  page_count: null,
  processing_status: 'uploaded',
  processing_error: null,
  created_at: '2026-09-15T00:00:00Z',
  updated_at: '2026-09-15T00:00:00Z',
}

describe('DocumentPanel', () => {
  it('shows an active spinner as soon as processing starts', async () => {
    const processDocument = vi.fn(() => new Promise<DocumentRecord>(() => {}))
    const api = {
      listDocuments: vi.fn().mockResolvedValue([documentRecord]),
      processDocument,
    } as unknown as IntelliDocsApi

    render(<DocumentPanel api={api} />)
    const processButton = await screen.findByRole('button', { name: 'Process' })
    fireEvent.click(processButton)

    await waitFor(() => expect(processDocument).toHaveBeenCalledWith('document-1'))
    expect(screen.getByRole('button', { name: 'Processing…' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Processing…' }).querySelector('.button-spinner')).not.toBeNull()
  })
})
