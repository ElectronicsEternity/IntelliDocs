export type ProcessingStatus = 'uploaded' | 'processing' | 'ready' | 'failed'

export interface DocumentRecord {
  id: string
  original_filename: string
  storage_path: string
  file_size: number
  page_count: number | null
  processing_status: ProcessingStatus
  processing_error: string | null
  created_at: string
  updated_at: string
}

export interface ChatSource {
  document_id: string
  document_title: string | null
  page_number: number | null
  text: string
  content_type: string
  table: {
    table_number: number
    page_numbers: number[]
    fields: Array<{
      value: string
      row_start: number
      row_end: number
      column_start: number
      column_end: number
    }>
  } | null
}

export interface ChatResponse {
  conversation_id: string
  answer: string
  sources: ChatSource[]
}
