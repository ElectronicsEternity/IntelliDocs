import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { IntelliDocsApi } from '../lib/api'
import { ChatPanel } from './ChatPanel'

describe('ChatPanel', () => {
  it('clears the current conversation and never reloads saved history', async () => {
    const api = { chat: vi.fn().mockResolvedValue({ conversation_id: 'old', answer: 'Old answer', sources: [] }) } as unknown as IntelliDocsApi
    const { unmount } = render(<ChatPanel api={api} />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'First question' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText('Old answer')
    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByText('Old answer')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'New question' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText('Old answer')
    expect(api.chat).toHaveBeenLastCalledWith('New question', undefined)
    unmount()
    render(<ChatPanel api={api} />)
    expect(screen.queryByText('Old answer')).not.toBeInTheDocument()
  })

  it('renders structured Markdown answers as headings and lists', async () => {
    const api = {
      chat: vi.fn().mockResolvedValue({
        conversation_id: 'conversation-1',
        answer: '## Daily rates\n\n- **Six days:** RM57.69\n- **Five days:** RM69.23',
        sources: [],
      }),
    } as unknown as IntelliDocsApi

    render(<ChatPanel api={api} />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'What are the daily rates?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByRole('heading', { name: 'Daily rates', level: 2 })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Six days:')).toBeInTheDocument()
  })

  it('renders table sources without internal cell coordinates', async () => {
    const api = {
      chat: vi.fn().mockResolvedValue({
        conversation_id: 'conversation-1',
        answer: 'RM1,200 per month.',
        sources: [{
          document_id: 'document-1',
          document_title: 'Minimum Wages Order 2022',
          page_number: 4,
          text: 'Row 1: columns 1-1: Area; columns 2-5: Minimum wage rate.',
          content_type: 'table',
          table: {
            table_number: 3,
            page_numbers: [4, 5],
            fields: [
              { value: 'Area', row_start: 1, row_end: 2, column_start: 1, column_end: 1 },
              { value: 'Minimum wage rate', row_start: 1, row_end: 1, column_start: 2, column_end: 5 },
            ],
          },
        }],
      }),
    } as unknown as IntelliDocsApi

    render(<ChatPanel api={api} />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'What is the rate?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    fireEvent.click(await screen.findByText('1 source'))

    expect(screen.getByRole('table', { name: 'Table 3 from Minimum Wages Order 2022' })).toBeInTheDocument()
    expect(screen.getByText('Minimum wage rate')).toHaveAttribute('colspan', '4')
    expect(screen.queryByText(/columns 1-1/)).not.toBeInTheDocument()
  })
})
