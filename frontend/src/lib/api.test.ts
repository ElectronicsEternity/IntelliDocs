import { afterEach, describe, expect, it, vi } from 'vitest'

import { IntelliDocsApi } from './api'

describe('IntelliDocsApi', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('adds the Supabase access token to API requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ documents: [] }), { headers: { 'Content-Type': 'application/json' }, status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = new IntelliDocsApi(async () => 'access-token', 'http://localhost:8000')
    await api.listDocuments()
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/documents', expect.any(Object))
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect((options.headers as Headers).get('Authorization')).toBe('Bearer access-token')
  })

  it('lets the browser set the multipart boundary for uploads', async () => {
    const record = { id: '1', original_filename: 'file.pdf', storage_path: '1/file.pdf', file_size: 3, page_count: null, processing_status: 'pending', processing_error: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(record), { headers: { 'Content-Type': 'application/json' }, status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = new IntelliDocsApi(async () => 'access-token', 'http://localhost:8000')
    await api.uploadDocument(new File(['pdf'], 'file.pdf', { type: 'application/pdf' }))
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.body).toBeInstanceOf(FormData)
    expect((options.headers as Headers).has('Content-Type')).toBe(false)
  })

  it('refreshes the session and retries once after an unauthorized response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ documents: [] }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }))
    const getAccessToken = vi.fn(async (forceRefresh = false) => forceRefresh ? 'fresh-token' : 'stale-token')
    vi.stubGlobal('fetch', fetchMock)
    const api = new IntelliDocsApi(getAccessToken, 'http://localhost:8000')

    await expect(api.listDocuments()).resolves.toEqual([])

    expect(getAccessToken).toHaveBeenCalledTimes(2)
    expect(getAccessToken).toHaveBeenLastCalledWith(true)
    const retryOptions = fetchMock.mock.calls[1][1] as RequestInit
    expect((retryOptions.headers as Headers).get('Authorization')).toBe('Bearer fresh-token')
  })

  it('loads the signed-in users usage summary', async () => {
    const payload = { plan_code: 'trial', plan_name: 'Trial', documents: { used: 1, limit: 25 } }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), {
      headers: { 'Content-Type': 'application/json' }, status: 200,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const api = new IntelliDocsApi(async () => 'access-token', 'http://localhost:8000')

    await expect(api.getUsage()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/usage', expect.any(Object))
  })
})
