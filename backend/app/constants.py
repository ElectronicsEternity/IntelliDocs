# ============================================
# File Processing
# ============================================

# Number of bytes read at a time when hashing files
FILE_READ_CHUNK_SIZE = 4096


# ============================================
# Document Processing
# ============================================

# Default language assigned to newly uploaded documents
DEFAULT_LANGUAGE = "Unknown"

# Default jurisdiction
DEFAULT_JURISDICTION = "Malaysia"

# Default document type
DEFAULT_DOCUMENT_TYPE = "Act"

# Default publisher
DEFAULT_PUBLISHER = "Unknown"

# PDF parser selected by the main ingestion workflow.
# Use the permissively licensed pdfplumber adapter.
PDF_PARSER_PROVIDER = "pdfplumber"

# ============================================
# RAG Processing
# ============================================

# Maximum number of tokens per chunk
CHUNK_SIZE = 500

# Number of overlapping tokens between chunks
CHUNK_OVERLAP = 100

# ============================================
# AI Processing
# ============================================

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

# ============================================
# Document Indexing Status
# ============================================

DOCUMENT_STATUS_NEW = "NEW"
DOCUMENT_STATUS_PROFILED = "PROFILED"
DOCUMENT_STATUS_ANALYZED = "ANALYZED"
DOCUMENT_STATUS_CHUNKED = "CHUNKED"
DOCUMENT_STATUS_EMBEDDED = "EMBEDDED"
DOCUMENT_STATUS_INDEXED = "INDEXED"
DOCUMENT_STATUS_FAILED = "FAILED"

# ============================================
# Processing Logic Versions
# ============================================

# Increase only the version for changed logic.
CURRENT_PAGE_MAPPING_VERSION = 1
CURRENT_CHUNKING_VERSION = 2
CURRENT_EMBEDDING_VERSION = 2



# Maximum chunks returned by retrieval
TOP_K = 10

# Minimum similarity score required
# for a chunk to be considered relevant
SIMILARITY_THRESHOLD = 0.4

CHAT_MODEL = "gpt-5-mini"
DOCUMENT_PROFILER_MODEL = "gpt-5"
