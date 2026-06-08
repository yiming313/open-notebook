# Open Notebook API - Quick Reference for CLI Clients

## Quick Start: Build Your CLI Client

### 1. Authentication
All requests need `Authorization: Bearer {password}` header:
```bash
# Default password (change in production): open-notebook-change-me
Authorization: Bearer open-notebook-change-me
```

### 2. Core Workflow: Chat with Notebook

```python
# 1. Create notebook
POST /api/notebooks
{"name": "My Research", "description": "..."}
→ Returns: {"id": "notebook:xyz"}

# 2. Add sources
POST /api/sources/json
{
  "notebook_id": "notebook:xyz",
  "type": "text",  # or "link", "upload"
  "content": "...",
  "title": "Source Title",
  "embed": true  # Enable vector search
}
→ Returns: {"id": "source:abc"}

# 3. Create chat session
POST /api/chat/sessions
{"notebook_id": "notebook:xyz", "title": "My Session"}
→ Returns: {"id": "chat_session:conv123"}

# 4. Build context (optional - get sources as context)
POST /api/chat/context
{
  "notebook_id": "notebook:xyz",
  "context_config": {
    "sources": {"source:abc": "full content"},
    "notes": {}
  }
}
→ Returns: {"context": {...}, "token_count": 2500, ...}

# 5. Execute chat
POST /api/chat/execute
{
  "session_id": "chat_session:conv123",
  "message": "What is this about?",
  "context": {"sources": [...], "notes": [...]}
}
→ Returns: {"messages": [{"type": "human", ...}, {"type": "ai", ...}]}
```

### 3. Search & Ask Workflow

```python
# Simple vector search
POST /api/search
{
  "query": "your search term",
  "type": "vector",  # or "text"
  "limit": 10
}
→ Returns: {"results": [...], "total_count": 42, "search_type": "vector"}

# Ask with answer synthesis (non-streaming)
POST /api/search/ask/simple
{
  "question": "What are the key findings?",
  "strategy_model": "model:gpt4",
  "answer_model": "model:claude3",
  "final_answer_model": "model:gpt4"
}
→ Returns: {"answer": "...", "question": "..."}

# Ask with streaming response
POST /api/search/ask
# Same request, but use EventSource or similar for SSE response
```

---

## API Endpoints Cheat Sheet

### Notebooks
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/notebooks` | List all notebooks |
| POST | `/api/notebooks` | Create notebook |
| GET | `/api/notebooks/{id}` | Get notebook |
| PUT | `/api/notebooks/{id}` | Update notebook |
| DELETE | `/api/notebooks/{id}` | Delete notebook |

### Chat Sessions (Notebook-level)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/chat/sessions?notebook_id={id}` | List sessions for notebook |
| POST | `/api/chat/sessions` | Create session |
| GET | `/api/chat/sessions/{id}` | Get session with messages |
| PUT | `/api/chat/sessions/{id}` | Update session |
| DELETE | `/api/chat/sessions/{id}` | Delete session |
| POST | `/api/chat/execute` | Send message and get response |
| POST | `/api/chat/context` | Build context from notebook |

### Chat Sessions (Source-level)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/sources/{source_id}/chat/sessions` | Create source chat |
| GET | `/api/sources/{source_id}/chat/sessions` | List source chats |
| POST | `/api/sources/{source_id}/chat/sessions/{session_id}/send` | Send message |

### Search & Ask
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/search` | Text/vector search |
| POST | `/api/search/ask` | Ask (streaming SSE) |
| POST | `/api/search/ask/simple` | Ask (non-streaming) |

### Sources
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/sources` | List all sources |
| POST | `/api/sources/json` | Create source |
| GET | `/api/sources/{id}` | Get source |
| PUT | `/api/sources/{id}` | Update source |
| DELETE | `/api/sources/{id}` | Delete source |
| GET | `/api/sources/{id}/status` | Get processing status |

### Models
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/models` | List models |
| POST | `/api/models` | Create/register model |
| GET | `/api/models/defaults` | Get default models |
| PUT | `/api/models/defaults` | Set default models |

---

## ID Format Reference

All IDs in Open Notebook follow the `table:id` format:

```
notebook:research-project-1
source:document-pdf-abc123
note:mynote-456
chat_session:conversation-789
model:gpt4-custom
insight:doc-summary-321
```

When calling endpoints, you can use:
- Full ID: `notebook:abc123`
- Short ID: `abc123` (API auto-prefixes)

---

## Important Patterns

### Model Override
Override the model for a specific chat session or message:

```python
# Session-level override (affects all messages in session)
PUT /api/chat/sessions/{session_id}
{"model_override": "model:claude3"}

# Per-message override (takes precedence)
POST /api/chat/execute
{
  "session_id": "...",
  "message": "...",
  "context": {...},
  "model_override": "model:claude3"  # This takes priority
}
```

### Context Building
Two levels of context detail:

```python
"context_config": {
  "sources": {
    "source:abc": "insights",        # Short summary
    "source:def": "full content"     # Complete text (expensive)
  },
  "notes": {
    "note:123": "full content"
  }
}
```

### Multi-Source Support
Sources can be added to multiple notebooks:

```python
# Create source for multiple notebooks
POST /api/sources/json
{
  "notebooks": ["notebook:xyz", "notebook:abc"],  # Multi-notebook support
  "type": "text",
  "content": "...",
  "embed": true
}
```

---

## Error Handling

All errors return JSON with a `detail` field:

```json
{
  "detail": "Notebook not found"
}
```

Common HTTP status codes:
- **401**: Missing/invalid authentication header
- **404**: Resource not found
- **422**: Validation error (bad request data)
- **500**: Server error

---

## Timeouts & Performance

- **Default timeout**: 300s (5 minutes) for LLM operations
- **Configure via**: `API_CLIENT_TIMEOUT` environment variable
- **For streaming**: May take longer; use appropriate client timeout

### Streaming Endpoints
These return Server-Sent Events (SSE) and don't complete quickly:
- `POST /api/search/ask` (ask with streaming)
- `POST /api/sources/{id}/chat/sessions/{sid}/send` (source chat)

Use an SSE client or event stream reader for these.

---

## Database & State Persistence

- **Chat messages**: Stored in SQLite (LangGraph checkpoints)
- **Location**: `{LANGGRAPH_CHECKPOINT_FILE}` env var
- **Thread ID format**: `chat_session:{session_id}`
- **Auto-cleanup**: Ephemeral chat sessions cleaned up after TTL

---

## Environment Variables

Key env vars for running the API:

```bash
# Server
API_HOST=127.0.0.1
API_PORT=5055
API_RELOAD=true  # Auto-reload on code change (dev only)

# Auth
OPEN_NOTEBOOK_PASSWORD=open-notebook-change-me

# Database
SURREAL_HOST=127.0.0.1
SURREAL_PORT=8000
SURREAL_USER=root
SURREAL_PASS=root

# Encryption (for API keys)
OPEN_NOTEBOOK_ENCRYPTION_KEY=your-secret-key

# CORS (for production)
CORS_ORIGINS=http://localhost:3000

# LangGraph
LANGGRAPH_CHECKPOINT_FILE=/data/sqlite-db/langgraph.db

# Optional: Client timeout
API_CLIENT_TIMEOUT=300.0  # seconds
```

---

## Example: Simple Python CLI Client

```python
import httpx
import json
from typing import Optional, Dict, Any

class NotebookClient:
    def __init__(self, base_url="http://localhost:5055", password="open-notebook-change-me"):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {password}"}
        self.client = httpx.Client(headers=self.headers, timeout=300)
    
    def create_notebook(self, name: str) -> Dict[str, Any]:
        resp = self.client.post(
            f"{self.base_url}/api/notebooks",
            json={"name": name, "description": ""}
        )
        return resp.json()
    
    def create_chat_session(self, notebook_id: str, title: str) -> Dict[str, Any]:
        resp = self.client.post(
            f"{self.base_url}/api/chat/sessions",
            json={"notebook_id": notebook_id, "title": title}
        )
        return resp.json()
    
    def chat(self, session_id: str, message: str, context: Dict = None) -> Dict[str, Any]:
        resp = self.client.post(
            f"{self.base_url}/api/chat/execute",
            json={
                "session_id": session_id,
                "message": message,
                "context": context or {"sources": [], "notes": []}
            }
        )
        return resp.json()
    
    def ask(self, question: str, models: Dict[str, str]) -> Dict[str, Any]:
        resp = self.client.post(
            f"{self.base_url}/api/search/ask/simple",
            json={
                "question": question,
                **models  # strategy_model, answer_model, final_answer_model
            }
        )
        return resp.json()

# Usage
client = NotebookClient()
notebook = client.create_notebook("My Research")
session = client.create_chat_session(notebook["id"], "Questions")
result = client.chat(session["id"], "What is this about?")
```

---

## Debugging Tips

1. **Check API docs**: `GET http://localhost:5055/docs` (Swagger UI)
2. **Check logs**: API logs to stdout with Loguru
3. **Use curl**: Test endpoints manually:
   ```bash
   curl -X POST http://localhost:5055/api/notebooks \
     -H "Authorization: Bearer open-notebook-change-me" \
     -H "Content-Type: application/json" \
     -d '{"name": "Test"}'
   ```
4. **Verify auth**: Always include `Authorization: Bearer {password}` header
5. **Check IDs**: Make sure you use full `table:id` format where needed

---

## Next Steps for Building Your CLI Client

1. Implement authentication header handling
2. Create notebook/source management commands
3. Implement chat session workflow (create → execute → retrieve)
4. Add search/ask functionality
5. Handle streaming responses for ask endpoint
6. Implement polling for async operations (source embedding status)

See the full documentation in `API_ARCHITECTURE.md` for detailed endpoint specifications.
