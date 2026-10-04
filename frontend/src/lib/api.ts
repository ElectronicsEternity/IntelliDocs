import type { BillingStatus, ChatResponse, DocumentRecord, UsageSummary } from '../types/api'

interface ErrorPayload {
  detail?: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class IntelliDocsApi {
  constructor(
    private readonly getAccessToken: (forceRefresh?: boolean) => Promise<string | null>,
    private readonly baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000',
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await this.getAccessToken()
    if (!token) {
      throw new ApiError('Your session has expired. Please sign in again.', 401)
    }

    const send = (accessToken: string) => {
      const headers = new Headers(init.headers)
      headers.set('Authorization', `Bearer ${accessToken}`)
      if (init.body && !(init.body instanceof FormData)) {
        headers.set('Content-Type', 'application/json')
      }
      return fetch(`${this.baseUrl}${path}`, { ...init, headers })
    }

    let response = await send(token)
    if (response.status === 401) {
      const refreshedToken = await this.getAccessToken(true)
      if (refreshedToken) response = await send(refreshedToken)
    }
    if (!response.ok) {
      let message = `Request failed with status ${response.status}.`
      try {
        const payload = (await response.json()) as ErrorPayload
        if (payload.detail) message = payload.detail
      } catch {
        // Keep the safe status-based message when the response is not JSON.
      }
      throw new ApiError(message, response.status)
    }
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  async listDocuments(): Promise<DocumentRecord[]> {
    const response = await this.request<{ documents: DocumentRecord[] }>('/documents')
    return response.documents
  }

  getUsage(): Promise<UsageSummary> {
    return this.request('/usage')
  }

  getBilling(): Promise<BillingStatus> {
    return this.request('/billing/status')
  }

  startCheckout(): Promise<{ url: string }> {
    return this.request('/billing/checkout', { method: 'POST' })
  }

  startFpxCheckout(): Promise<{ url: string }> {
    return this.request('/billing/checkout/fpx', { method: 'POST' })
  }

  manageSubscription(): Promise<{ url: string }> {
    return this.request('/billing/portal', { method: 'POST' })
  }

  private notifyUsageChanged() {
    window.dispatchEvent(new Event('intellidocs:usage-updated'))
  }

  uploadDocument(file: File): Promise<DocumentRecord> {
    const form = new FormData()
    form.append('file', file)
    return this.request('/documents/upload', { method: 'POST', body: form })
  }

  async processDocument(documentId: string): Promise<DocumentRecord> {
    const result = await this.request<DocumentRecord>(`/documents/${documentId}/process`, { method: 'POST' })
    this.notifyUsageChanged()
    return result
  }

  deleteDocument(documentId: string): Promise<void> {
    return this.request(`/documents/${documentId}`, { method: 'DELETE' })
  }

  async chat(question: string, conversationId?: string): Promise<ChatResponse> {
    const result = await this.request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ question, conversation_id: conversationId || null }),
    })
    this.notifyUsageChanged()
    return result
  }
}
