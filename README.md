# OB Chatbot

Unified chatbot application with an embeddable JavaScript widget and a FastAPI backend powered by Snowflake Cortex agents.

## Architecture

- **Backend** (`app/`) -- FastAPI server that relays requests to the Snowflake Cortex Agent Object API (`PROFITABILITY_AGENT`) with server-managed threads and JWT-based brand isolation.
- **Frontend Widget** (`frontend/widget/`) -- Framework-agnostic TypeScript widget that embeds into any admin portal via a single script tag.
- **Shared Contracts** (`shared/`) -- SSE protocol documentation shared between frontend and backend.

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- Snowflake account with Cortex Agent access

### Backend

```bash
pip install -r requirements.txt

# Configure environment
cp .env.example .env   # or edit .env directly

# Run the server
uvicorn app.main:app --reload --port 8000
```

### Widget (Development)

```bash
cd frontend/widget
npm install
npm run dev
```

Opens a dev server with a simulated admin portal at `http://localhost:5173`.

### Widget (Production Build)

```bash
cd frontend/widget
npm run build
```

Produces `dist/chatbot-widget.iife.js` -- a single script to embed in the admin portal.

## Embedding in the Admin Portal

### 1. Load the widget script

```html
<script src="https://your-cdn.com/chatbot-widget.iife.js"></script>
```

### 2. Initialize with brand context

```javascript
ChatbotWidget.init({
  mountElement: '#chat-container',
  apiBaseUrl: 'https://your-api-domain.com',
  getAccessToken: () => yourAuthService.getToken(),

  brandPrimaryColor: '#2563EB',

  // Optional
  locale: 'en-US',
  theme: 'light',
  compact: false,
  suggestedPrompts: ['What was our revenue last month?'],
});
```

### Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `mountElement` | `string \| HTMLElement` | Yes | CSS selector or DOM element to mount into |
| `apiBaseUrl` | `string` | Yes | Backend API base URL |
| `getAccessToken` | `() => Promise<string>` | Yes | Returns a signed JWT with `brand` claim |
| `brandDisplayName` | `string` | No | Display name in header (default: "Assistant") |
| `brandPrimaryColor` | `string` | No | CSS color for brand theming |
| `locale` | `string` | No | Locale for timestamp formatting |
| `theme` | `'light' \| 'dark'` | No | Color theme |
| `compact` | `boolean` | No | Compact layout mode |
| `welcomeMessage` | `string` | No | Custom welcome heading |
| `suggestedPrompts` | `string[]` | No | Quick-start prompt chips |

## Security: Brand Guardrails

Brand isolation is enforced via signed JWT tokens:

1. The admin portal signs a JWT containing a `brand` claim.
2. The widget passes this JWT as a Bearer token on every `/chat` request.
3. The backend verifies the JWT signature and extracts the brand claim.
4. The brand context is prefixed into the agent prompt so that all data queries are filtered to the specific brand.

### JWT Configuration

Set these environment variables for JWT verification:

```
JWT_PUBLIC_KEY=<base64-encoded PEM public key>
JWT_ISSUER=<expected issuer>
JWT_AUDIENCE=chatbot
```

When `JWT_PUBLIC_KEY` is not set, the backend falls back to the request body `brand` field (development mode only).

## SSE Protocol

See [`shared/contracts.md`](shared/contracts.md) for the full specification.

| Event | Description |
|-------|-------------|
| `markdown` | Status/narration messages (tool usage, processing steps) |
| `text` | Answer content (streamed progressively as token deltas) |
| `thread` | Thread context for conversation continuity |
| `error` | Error message |
| `done` | End of stream sentinel |

## Docker

```bash
docker build -t ob-chatbot .
docker run -p 8000:8000 --env-file .env ob-chatbot
```

The Docker build includes the widget, served at `/widget/` on the same origin.

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SNOWFLAKE_ACCOUNT` | Yes | Snowflake account identifier |
| `SNOWFLAKE_PROJECT_USER` | Yes | Snowflake service user |
| `PRIVATE_USER_KEY` | Yes | Base64-encoded PEM private key |
| `JWT_PUBLIC_KEY` | No | Base64-encoded PEM public key for portal JWT verification |
| `JWT_ISSUER` | No | Expected JWT issuer |
| `JWT_AUDIENCE` | No | Expected JWT audience (default: `chatbot`) |
| `AGENT_PATH` | No | Cortex Agent Object endpoint path (default: see config.py) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (default: `*`) |
| `AGENT_TIMEOUT_SEC` | No | Cortex Agent request timeout in seconds (default: 300) |
| `MAX_CONCURRENCY` | No | Max concurrent agent requests (default: 8) |
| `RATE_LIMIT_RPM` | No | Requests per minute per client (default: 30) |

## Project Structure

```
app/                          Python backend
  api/routes/chat.py          Chat endpoint (SSE streaming)
  core/auth.py                JWT brand verification
  core/config.py              Environment settings
  core/security.py            Snowflake keypair auth
  middleware/rate_limit.py    Request rate limiting
  schemas/chat.py             Request/response models
  services/snowflake_api.py   Cortex Agent Object streaming + thread management
  services/snowflake_setup.py Snowflake keypair JWT caching
  sse/handler.py              Agent SSE → widget SSE translation
  sse/utility.py              SSE construction helper

frontend/widget/              Embeddable chat widget
  src/index.ts                SDK entrypoint (ChatbotWidget.init)
  src/widget.ts               Main widget class (Shadow DOM)
  src/stream-client.ts        POST-based SSE streaming client
  src/markdown.ts             Lightweight Markdown renderer
  src/styles/widget.css       Widget styles (brand-themeable)
  src/i18n/en.ts              English UI strings

shared/contracts.md           SSE protocol specification
tests/                        Backend test suite
```
