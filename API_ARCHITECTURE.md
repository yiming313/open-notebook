# Open Notebook API Architecture Report

## Executive Summary

Open Notebook is a privacy-first AI research assistant with:
- **Frontend**: React/Next.js at port 3000
- **API**: FastAPI backend at port 5055
- **Database**: SurrealDB at port 8000

The API uses **LangGraph** state machines to orchestrate chat, search/ask, and content processing workflows.

---

## 1. Chat API Endpoints (api/routers/chat.py)

### Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/chat/sessions` | List chat sessions for a notebook |
| POST | `/api/chat/sessions` | Create new chat session |
| GET | `/api/chat/sessions/{session_id}` | Get session with messages |
| PUT | `/api/chat/sessions/{session_id}` | Update session (title, model_override) |
| DELETE | `/api/chat/sessions/{session_id}` | Delete session and conversation history |
| POST | `/api/chat/execute` | Execute chat (send message, get AI response) |
| POST | `/api/chat/context` | Build context from notebook sources/notes |

### Detailed Request/Response Schemas

#### GET /api/chat/sessions
```json
Query Parameters:
  - notebook_id (required): string - Notebook ID
  - X-Client-ID (header, optional): string - Browser client identifier

Response (List[ChatSessionResponse]):
[
  {
    "id": "chat_session:abc123",
    "title": "Discussion about ML",
    "notebook_id": "notebook:xyz789",
    "created": "2026-01-15T10:30:00Z",
    "updated": "2026-01-15T11:45:00Z",
    "message_count": 12,
    "model_override": null
  }
]
```

#### POST /api/chat/sessions
```json
Request (CreateSessionRequest):
{
  "notebook_id": "notebook:xyz789",
  "title": "Optional Session Title",
  "model_override": "model:gpt4-optional"
}

Response (ChatSessionResponse):
{
  "id": "chat_session:new123",
  "title": "Optional Session Title",
  "notebook_id": "notebook:xyz789",
  "created": "2026-01-15T12:00:00Z",
  "updated": "2026-01-15T12:00:00Z",
  "message_count": 0,
  "model_override": "model:gpt4-optional"
}
```

#### GET /api/chat/sessions/{session_id}
```json
Query Parameters:
  - session_id (path): string - Session ID (with or without "chat_session:" prefix)
  - X-Client-ID (header, optional): string - Browser client identifier

Response (ChatSessionWithMessagesResponse):
{
  "id": "chat_session:abc123",
  "title": "Discussion about ML",
  "notebook_id": "notebook:xyz789",
  "created": "2026-01-15T10:30:00Z",
  "updated": "2026-01-15T11:45:00Z",
  "message_count": 3,
  "model_override": null,
  "messages": [
    {
      "id": "msg_0",
      "type": "human",
      "content": "What is machine learning?",
      "timestamp": null
    },
    {
      "id": "msg_1",
      "type": "ai",
      "content": "Machine learning is a subset of artificial intelligence...",
      "timestamp": null
    }
  ]
}
```

#### PUT /api/chat/sessions/{session_id}
```json
Request (UpdateSessionRequest):
{
  "title": "New Session Title",
  "model_override": "model:claude3"
}

Response (ChatSessionResponse):
{
  "id": "chat_session:abc123",
  "title": "New Session Title",
  "notebook_id": "notebook:xyz789",
  "created": "2026-01-15T10:30:00Z",
  "updated": "2026-01-15T13:00:00Z",
  "message_count": 3,
  "model_override": "model:claude3"
}
```

#### DELETE /api/chat/sessions/{session_id}
```json
Response (SuccessResponse):
{
  "success": true,
  "message": "Session deleted successfully"
}
```

#### POST /api/chat/execute
```json
Request (ExecuteChatRequest):
{
  "session_id": "chat_session:abc123",
  "message": "What are the key takeaways?",
  "context": {
    "sources": [
      {
        "id": "source:doc1",
        "title": "Research Paper",
        "content": "..."
      }
    ],
    "notes": [
      {
        "id": "note:123",
        "title": "My notes",
        "content": "..."
      }
    ]
  },
  "model_override": "model:claude3"
}

Response (ExecuteChatResponse):
{
  "session_id": "chat_session:abc123",
  "messages": [
    {
      "id": "msg_0",
      "type": "human",
      "content": "What are the key takeaways?",
      "timestamp": null
    },
    {
      "id": "msg_1",
      "type": "ai",
      "content": "Based on your sources, the key takeaways are...",
      "timestamp": null
    }
  ]
}
```

#### POST /api/chat/context
```json
Request (BuildContextRequest):
{
  "notebook_id": "notebook:xyz789",
  "context_config": {
    "sources": {
      "source:doc1": "insights",
      "source:doc2": "full content"
    },
    "notes": {
      "note:123": "full content"
    }
  }
}

Response (BuildContextResponse):
{
  "context": {
    "sources": [
      {
        "id": "source:doc1",
        "title": "Research Paper",
        "content_preview": "..."
      }
    ],
    "notes": [
      {
        "id": "note:123",
        "title": "My notes",
        "content": "..."
      }
    ]
  },
  "token_count": 2500,
  "char_count": 15000
}
```

---

## 2. Source Chat API Endpoints (api/routers/source_chat.py)

### Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/sources/{source_id}/chat/sessions` | Create chat session for a specific source |
| GET | `/api/sources/{source_id}/chat/sessions` | List chat sessions for a source |
| GET | `/api/sources/{source_id}/chat/sessions/{session_id}` | Get source chat session with messages |
| PUT | `/api/sources/{source_id}/chat/sessions/{session_id}` | Update source chat session |
| DELETE | `/api/sources/{source_id}/chat/sessions/{session_id}` | Delete source chat session |
| POST | `/api/sources/{source_id}/chat/sessions/{session_id}/send` | Send message in source chat |

### Key Request/Response Schemas

Similar to notebook chat, but:
- Sessions are bound to a specific `source_id`
- Response includes `context_indicators` showing which sources/insights were used
- Uses the source_chat.py LangGraph workflow

---

## 3. Search & Ask API Endpoints (api/routers/search.py)

### Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/search` | Text or vector search across notebook |
| POST | `/api/search/ask` | Multi-turn ask with streaming response |
| POST | `/api/search/ask/simple` | Ask with non-streaming response |

#### POST /api/search
```json
Request (SearchRequest):
{
  "query": "machine learning basics",
  "type": "vector",  // or "text"
  "limit": 100,
  "search_sources": true,
  "search_notes": true,
  "minimum_score": 0.2  // for vector search only
}

Response (SearchResponse):
{
  "results": [
    {
      "id": "source:doc1",
      "type": "source",
      "title": "ML Basics Paper",
      "content": "...",
      "score": 0.95
    }
  ],
  "total_count": 42,
  "search_type": "vector"
}
```

#### POST /api/search/ask (Streaming)
```json
Request (AskRequest):
{
  "question": "What are the main concepts?",
  "strategy_model": "model:claude3",
  "answer_model": "model:gpt4",
  "final_answer_model": "model:claude3"
}

Response (Server-Sent Events):
data: {"type":"strategy","reasoning":"...","searches":[{"term":"concept1","instructions":"..."}]}

data: {"type":"answer","content":"..."}

data: {"type":"final_answer","content":"..."}

data: {"type":"complete","final_answer":"..."}
```

#### POST /api/search/ask/simple (Non-streaming)
```json
Request (AskRequest):
{
  "question": "What are the main concepts?",
  "strategy_model": "model:claude3",
  "answer_model": "model:gpt4",
  "final_answer_model": "model:claude3"
}

Response (AskResponse):
{
  "answer": "The main concepts are...",
  "question": "What are the main concepts?"
}
```

---

## 4. LangGraph Workflows

### ask.py - Multi-Search Strategy Agent

**Purpose**: Given a question, generate search strategy → execute searches → synthesize answer

**State Definition**:
```python
class ThreadState(TypedDict):
    question: str
    strategy: Strategy  # with reasoning + list of Search terms
    answers: Annotated[list, operator.add]  # accumulated answers from searches
    final_answer: str
```

**Flow**:
1. **Entry**: `call_model_with_messages()` 
   - Receives question
   - Uses template "ask/entry" to prompt LLM
   - Returns Strategy with up to 5 searches

2. **Parallel**: `trigger_queries()` 
   - Creates Send nodes for each Search
   - Fans out to `provide_answer()` nodes

3. **Provide Answer**: `provide_answer()`
   - Takes one Search term + instructions
   - Calls `vector_search(term, 10, True, True)` → retrieves 10 results
   - Uses template "ask/query_process" to extract relevant answer
   - Returns answer string

4. **Synthesis**: `write_final_answer()`
   - Receives all answers
   - Uses template "ask/final_answer" 
   - Returns final_answer string

**Model Configuration**:
```python
config = {
    "configurable": {
        "strategy_model": "model:gpt4",      # Phase 1: create strategy
        "answer_model": "model:claude3",     # Phase 2: answer each search
        "final_answer_model": "model:gpt4"   # Phase 3: synthesize
    }
}
```

**Invocation**:
```python
result = await ask_graph.ainvoke(
    {"question": "What is quantum computing?"},
    config={"configurable": {...}}
)
# result["final_answer"] contains synthesized answer
```

---

### chat.py - Conversational Chat Agent

**Purpose**: Maintain conversation history + respond with context

**State Definition**:
```python
class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]  # LangChain Message objects
    notebook: Optional[Notebook]
    context: Optional[str]  # Pre-built context string or dict
    context_config: Optional[dict]
    model_override: Optional[str]
```

**Flow**:
1. **Node**: `call_model_with_messages()`
   - Builds system prompt from template "chat/system" using state
   - Adds all messages to payload
   - Calls LLM
   - Returns cleaned AI message to append to messages list

**Message History Persistence**:
- Uses `SqliteSaver` checkpoint storage
- Location: `LANGGRAPH_CHECKPOINT_FILE` env var (default: `/data/sqlite-db/langgraph.db`)
- Thread ID = `chat_session:{session_id}`

**Invocation**:
```python
result = chat_graph.invoke(
    {
        "messages": [HumanMessage(content="Hello")],
        "notebook": notebook_obj,
        "context": context_dict,
        "model_override": "model:claude3"
    },
    config=RunnableConfig(configurable={"thread_id": "chat_session:123"})
)
# result["messages"] contains all messages including new AI response
```

---

### source_chat.py - Source-Specific Chat

**Purpose**: Chat with a specific source, auto-inject source content/insights into context

**Features**:
- Automatically builds context from source content and insights
- Tracks which sources/insights were used via ContextBuilder
- Similar persistence to chat.py

---

## 5. Source & Notebook ID Formats

### ID Prefixes (SurrealDB RecordID format)

```
notebook:       notebook:research-project-1
source:         source:document-pdf-abc123
note:           note:mynote-456
chat_session:   chat_session:conv-789
model:          model:gpt4-custom
insight:        insight:doc-summary-321
```

### How to Query Specific Sources/Notebooks

**Get notebook and all its sources**:
```bash
GET /api/notebooks/{notebook_id}
GET /api/sources?notebook_id={notebook_id}
```

**Chat with specific source**:
```bash
POST /api/sources/{source_id}/chat/sessions
# Creates session bound to that source
```

**Search only specific source**:
```bash
POST /api/search
# response includes "id": "source:xxx" in results
# Filter client-side or use vector_search with source parameter
```

**Get source content**:
```bash
GET /api/sources/{source_id}
# Response includes:
{
  "id": "source:abc123",
  "title": "Research Paper",
  "full_text": "...",
  "embedded": true,
  "embedded_chunks": 45,
  "asset": {
    "file_path": "/uploads/paper.pdf",
    "url": null
  }
}
```

---

## 6. Service Layer Pattern (api/*.py)

### ChatService (api/chat_service.py)

Async HTTP client wrapping chat endpoints:

```python
class ChatService:
    async def get_sessions(notebook_id: str) -> List[Dict]
    async def create_session(notebook_id, title=None, model_override=None) -> Dict
    async def get_session(session_id: str) -> Dict
    async def update_session(session_id, title=None, model_override=None) -> Dict
    async def delete_session(session_id: str) -> Dict
    async def execute_chat(session_id, message, context, model_override=None) -> Dict
    async def build_context(notebook_id, context_config) -> Dict
```

### Notebook Service (api/notebook_service.py)

Business logic for notebook operations:
- CRUD operations
- Relationship management (sources, notes, sessions)

### Sources Service (api/sources_service.py)

Content ingestion pipeline:
- File/URL extraction (via content-core)
- Text extraction & chunking
- Embedding submission (fire-and-forget)
- Metadata storage

---

## 7. API Models (api/models.py)

### Chat-Related Models

```python
class SearchRequest(BaseModel):
    query: str
    type: Literal["text", "vector"]
    limit: int = 100
    search_sources: bool = True
    search_notes: bool = True
    minimum_score: float = 0.2

class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total_count: int
    search_type: str

class AskRequest(BaseModel):
    question: str
    strategy_model: str        # Model ID
    answer_model: str          # Model ID
    final_answer_model: str    # Model ID

class AskResponse(BaseModel):
    answer: str
    question: str
```

### Source Models

```python
class SourceCreate(BaseModel):
    notebook_id: Optional[str]           # Deprecated, use "notebooks"
    notebooks: Optional[List[str]]       # New: multi-notebook support
    type: str                            # "link", "upload", "text"
    url: Optional[str]
    file_path: Optional[str]
    content: Optional[str]
    title: Optional[str]
    transformations: Optional[List[str]]
    embed: bool = False
    delete_source: bool = False
    async_processing: bool = False

class SourceResponse(BaseModel):
    id: str
    title: Optional[str]
    topics: Optional[List[str]]
    asset: Optional[AssetModel]          # {file_path, url}
    full_text: Optional[str]
    embedded: bool
    embedded_chunks: int
    notebooks: Optional[List[str]]
    command_id: Optional[str]            # For async processing
    status: Optional[str]
    processing_info: Optional[Dict]
```

---

## 8. API Server Startup

### Configuration

**File**: `run_api.py`

**Environment Variables**:
```bash
API_HOST=127.0.0.1      # Default
API_PORT=5055           # Default
API_RELOAD=true         # Dev mode (auto-reload on code change)
OPEN_NOTEBOOK_PASSWORD=your-password-here  # Auth (default: "open-notebook-change-me")
CORS_ORIGINS=*          # Default: allow all; set to comma-separated URLs for prod
```

### Startup Sequence

1. Load `.env` via `dotenv.load_dotenv()`
2. Initialize FastAPI app with lifespan handler
3. **Lifespan startup** (async):
   - Check `OPEN_NOTEBOOK_ENCRYPTION_KEY` is set (warn if missing)
   - Run database migrations via `AsyncMigrationManager`
   - Migrate legacy podcast profiles
   - Start background chat session sweeper
4. Register routers:
   - chat, source_chat, search
   - notebooks, sources, notes
   - models, credentials, transformations
   - podcasts, insights, etc.
5. Add CORS middleware (before auth for error handling)
6. Add PasswordAuthMiddleware (excludes /health, /docs, /api/auth/status, /api/config)

### Authentication

**PasswordAuthMiddleware** (api/auth.py):
- Checks `Authorization: Bearer {password}` header
- Default password: `open-notebook-change-me` (set `OPEN_NOTEBOOK_PASSWORD`)
- Returns 401 if missing/incorrect
- Excluded paths: /, /health, /docs, /openapi.json, /redoc, /api/auth/status, /api/config

**For production**: Replace with OAuth/JWT (see CONFIGURATION.md)

### Running the Server

```bash
# Development
cd /Users/yimingsong/Code/open-notebook
API_HOST=0.0.0.0 API_PORT=5055 API_RELOAD=true uv run python run_api.py

# Production
API_HOST=0.0.0.0 API_PORT=5055 API_RELOAD=false python run_api.py
```

### API Documentation

Once running, Swagger UI available at: `http://localhost:5055/docs`

---

## 9. Frontend API Client Integration

### Python Client (api/client.py)

```python
class APIClient:
    def __init__(self, base_url="http://127.0.0.1:5055"):
        # Auto-reads OPEN_NOTEBOOK_PASSWORD for auth
        
    # Notebooks
    def get_notebooks() -> List[Dict]
    def create_notebook(name, description="") -> Dict
    def get_notebook(notebook_id) -> Dict
    
    # Search
    def search(query, search_type="text", limit=100) -> Dict
    def ask_simple(question, strategy_model, answer_model, final_answer_model) -> Dict
    
    # Chat (not yet in client, but endpoints exist)
    # Sources
    def get_sources(notebook_id=None) -> List[Dict]
    def create_source(notebook_id, source_type, ...) -> Dict
    def get_source(source_id) -> Dict
    
    # Models
    def get_models(model_type=None) -> List[Dict]
```

### JavaScript/TypeScript Frontend Client

Frontend at `frontend/` uses TanStack Query (React Query) with axios:
- Base URL: env.NEXT_PUBLIC_API_BASE_URL (default: http://localhost:5055)
- Auth: `Authorization: Bearer {password}` header added by interceptor

---

## 10. Example CLI Client Flow

### Step 1: Create a Notebook
```bash
curl -X POST http://localhost:5055/api/notebooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer open-notebook-change-me" \
  -d '{"name": "My Research", "description": "Quantum Computing"}'
# Returns: {"id": "notebook:abc123", "name": "My Research", ...}
```

### Step 2: Add a Source (Text)
```bash
curl -X POST http://localhost:5055/api/sources/json \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer open-notebook-change-me" \
  -d '{
    "notebook_id": "notebook:abc123",
    "type": "text",
    "content": "Quantum computing uses qubits...",
    "title": "Quantum Intro",
    "embed": true
  }'
# Returns: {"id": "source:doc123", ...}
```

### Step 3: Create Chat Session
```bash
curl -X POST http://localhost:5055/api/chat/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer open-notebook-change-me" \
  -d '{"notebook_id": "notebook:abc123", "title": "Questions"}'
# Returns: {"id": "chat_session:conv123", ...}
```

### Step 4: Build Context
```bash
curl -X POST http://localhost:5055/api/chat/context \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer open-notebook-change-me" \
  -d '{
    "notebook_id": "notebook:abc123",
    "context_config": {
      "sources": {"source:doc123": "full content"},
      "notes": {}
    }
  }'
# Returns: {"context": {...}, "token_count": 2500, "char_count": 15000}
```

### Step 5: Execute Chat
```bash
curl -X POST http://localhost:5055/api/chat/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer open-notebook-change-me" \
  -d '{
    "session_id": "chat_session:conv123",
    "message": "What is quantum computing?",
    "context": {"sources": [...], "notes": [...]},
    "model_override": "model:gpt4"
  }'
# Returns: {"session_id": "...", "messages": [...]}
```

### Step 6: Ask (Search + Synthesize)
```bash
curl -X POST http://localhost:5055/api/search/ask/simple \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer open-notebook-change-me" \
  -d '{
    "question": "What are the benefits of quantum computing?",
    "strategy_model": "model:gpt4",
    "answer_model": "model:claude3",
    "final_answer_model": "model:gpt4"
  }'
# Returns: {"answer": "...", "question": "..."}
```

---

## 11. Key Architecture Insights

### Async-First Design
- All database queries, graph invocations, and API calls use `async/await`
- FastAPI handles concurrent requests efficiently

### LangGraph State Machines
- **chat.py**: Maintains message history; one node calls LLM
- **ask.py**: Multi-step agent (strategy → parallel searches → synthesis)
- **source_chat.py**: Like chat but auto-injects source context

### Context Building Strategy
- **Short context**: Summaries/insights (small token cost)
- **Full context**: Complete source/note text (large token cost)
- Client specifies in `context_config` what to include

### Model Override Pattern
- Can override model at **session level** or **per-request level**
- Per-request takes precedence
- Passed via `RunnableConfig(configurable={"model_id": "..."})`

### Source ID Linking
- Sources can link to **multiple notebooks** (via `notebooks` list)
- Deletion cascades: notebook delete → orphans sources from that notebook
- Sources in multiple notebooks only deleted if explicitly choosing to delete

### Fire-and-Forget Patterns
- Embedding: `source.vectorize()` returns command_id (polling via `/api/sources/{id}/status`)
- Insights: `source.add_insight()` submits job, returns command_id
- Podcasts: `POST /api/podcasts` submits async job

---

## 12. Common Integration Points

### For a CLI Client

1. **Auth**: Pass `Authorization: Bearer {password}` header
2. **Notebook selection**: Use notebook_id to scope operations
3. **Chat**: Create session → build context → execute chat → poll for new messages
4. **Search**: POST /api/search with query
5. **Ask**: POST /api/search/ask/simple for non-streaming answer

### Timeout Considerations
- Default API timeout: 300s (5 min) for LLM operations
- Configurable via `API_CLIENT_TIMEOUT` env var
- Streaming endpoints (ask, source_chat) may take longer

### Error Handling
- All errors return JSON with `detail` field
- Status codes: 401 (auth), 404 (not found), 422 (validation), 500 (server)
- Custom exception hierarchy in `open_notebook.exceptions`

