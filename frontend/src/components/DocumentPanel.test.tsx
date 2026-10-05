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
  it('warns about supporting data and reprocessing charges before deleting', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const api = { listDocuments: vi.fn().mockResolvedValue([documentRecord]), deleteDocument: vi.fn().mockResolvedValue(undefined) } as unknown as IntelliDocsApi
    render(<DocumentPanel api={api} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('supporting extraction profiles'))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('incur AI usage charges'))
    expect(api.deleteDocument).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith('document-1'))
    confirm.mockRestore()
  })

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

  it('refreshes a stale card after processing fails', async () => {
    const failedRecord = {
      ...documentRecord,
      processing_status: 'failed',
      processing_error: 'Table linking failed.',
    } as DocumentRecord
    const api = {
      listDocuments: vi.fn()
        .mockResolvedValueOnce([documentRecord])
        .mockResolvedValueOnce([failedRecord]),
      processDocument: vi.fn().mockRejectedValue(new Error('Table linking failed.')),
    } as unknown as IntelliDocsApi

    render(<DocumentPanel api={api} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Process' }))

    expect(await screen.findByRole('button', { name: 'Retry processing' })).toBeInTheDocument()
    expect(screen.getAllByText('Table linking failed.')).toHaveLength(2)
    expect(api.listDocuments).toHaveBeenCalledTimes(2)
  })
})
