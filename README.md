# OB Chatbot

Unified chatbot application with an embeddable JavaScript widget and a FastAPI backend powered by Snowflake Cortex agents.

## Architecture

- **Backend** (`app/`) -- FastAPI server that relays requests to the Snowflake Cortex Agent Object API (`PROFITABILITY_AGENT`), enforces a static Bearer API key, and manages Cortex threads server-side.
- **Frontend Widget** (`frontend/widget/`) -- Framework-agnostic TypeScript widget that mounts into any admin portal and streams answers over POST-based SSE.
- **Shared Contracts** (`shared/`) -- Protocol docs for the backend/widget event stream.

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- Snowflake account with Cortex Agent access

### Backend

```bash
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run the API locally
uvicorn app.main:app --reload --port 8000
```

At minimum, set these values in `.env` before starting the backend:

```env
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_PROJECT_USER=...
PRIVATE_USER_KEY=...
API_KEY=your-shared-widget-api-key
```

### Widget (Development)

```bash
cd frontend/widget
npm install
npm run dev
```

This opens a dev harness at `http://localhost:5173`. The harness initializes the widget against `http://localhost:8000`, so set your local `API_KEY` to match the sample token in `frontend/widget/index.html` or update that file to use your own dev key.

### Widget (Production Build)

```bash
cd frontend/widget
npm run build
```

This produces the embeddable assets in `frontend/widget/dist/`, including `chatbot-widget.iife.js`.

## Embedding the Widget

### Recommended production setup

In production, the Docker image serves both the API and the built widget from the same app container:

- API: `/chat`
- Health check: `/health`
- Widget assets: `/widget/`

That same-origin setup keeps deployment simple and avoids cross-origin widget/API calls.

### 1. Load the widget script

```html
<script src="https://chatbot.yourdomain.com/widget/chatbot-widget.iife.js"></script>
```

### 2. Initialize with API + brand context

```javascript
ChatbotWidget.init({
  mountElement: "#chat-container",
  apiBaseUrl: window.location.origin,
  getAccessToken: async () => window.__CHATBOT_API_KEY__,
  brand: "drmtlgy",

  brandDisplayName: "Drmtlgy",
  assistantName: "OB Analyst",
  brandPrimaryColor: "#2563EB",
  startOpen: true,

  // Optional
  locale: "en-US",
  theme: "light",
  compact: false,
  suggestedPrompts: [
    "What was our revenue last month?",
    "Show me top markets by AOV",
  ],
});
```

`getAccessToken()` is still the widget hook name, but it now returns the shared API key that the backend validates against `API_KEY`.

### Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `mountElement` | `string \| HTMLElement` | Yes | CSS selector or DOM element to mount into |
| `apiBaseUrl` | `string` | Yes | Backend base URL, for example `window.location.origin` in same-origin production |
| `getAccessToken` | `() => Promise<string>` | Yes | Returns the static Bearer token expected by the backend (`API_KEY`) |
| `brand` | `string` | Yes in practice | Brand code sent in the `/chat` request body |
| `brandDisplayName` | `string` | No | Friendly brand name used in the welcome copy |
| `assistantName` | `string` | No | Name shown in the widget header |
| `brandPrimaryColor` | `string` | No | CSS color for brand theming |
| `locale` | `string` | No | Locale for timestamp formatting |
| `theme` | `'light' \| 'dark'` | No | Color theme |
| `compact` | `boolean` | No | Compact layout mode |
| `startOpen` | `boolean` | No | Whether the widget starts expanded |
| `welcomeMessage` | `string` | No | Custom welcome heading |
| `suggestedPrompts` | `string[]` | No | Quick-start prompt chips |

## Authentication and Brand Context

Requests to `POST /chat` use two pieces of context:

1. The widget sends `Authorization: Bearer <API_KEY>`.
2. The widget sends the selected `brand` in the JSON body.
3. The backend rejects requests with a missing or invalid Bearer token.
4. The backend also requires `brand` and passes it into the Snowflake agent flow for brand-scoped responses.

Because the auth model is a shared static key, this setup is best suited to controlled/internal admin experiences. If the embedding surface changes or the key is exposed, rotate `API_KEY`.

## SSE Protocol

See [`shared/contracts.md`](shared/contracts.md) for the full specification.

| Event | Description |
|-------|-------------|
| `markdown` | Status/narration messages during processing |
| `text` | Answer content streamed progressively |
| `thread` | Thread context for conversation continuity |
| `error` | Error message |
| `done` | End-of-stream sentinel |

## Docker

```bash
docker build -t ob-chatbot .
docker run -p 8000:8000 --env-file .env ob-chatbot
```

The Docker image builds the widget and serves it from `/widget/` on the same origin as the API.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SNOWFLAKE_ACCOUNT` | Yes | Snowflake account identifier |
| `SNOWFLAKE_PROJECT_USER` | Yes | Snowflake service user |
| `PRIVATE_USER_KEY` | Yes | Base64-encoded PEM private key |
| `API_KEY` | Yes | Shared Bearer token required on every `/chat` request |
| `AGENT_PATH` | No | Cortex Agent Object endpoint path |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins; use `*` only for local development |
| `AGENT_TIMEOUT_SEC` | No | Cortex Agent request timeout in seconds (default: `300`) |
| `MAX_CONCURRENCY` | No | Max concurrent agent requests (default: `8`) |
| `RATE_LIMIT_RPM` | No | Requests per minute per client (default: `30`) |
| `LOG_LEVEL` | No | Application log level (default: `INFO`) |
| `LOG_FORMAT` | No | `text` or `json` log output (default: `text`) |

## Project Structure

```text
app/                          Python backend
  api/routes/chat.py          Chat endpoint (SSE streaming)
  core/auth.py                Static API key verification
  core/config.py              Environment settings
  core/security.py            Snowflake keypair auth
  middleware/rate_limit.py    Request rate limiting
  schemas/chat.py             Request/response models
  services/snowflake_api.py   Cortex Agent Object streaming + thread management
  services/snowflake_setup.py Snowflake keypair JWT caching
  sse/handler.py              Agent SSE -> widget SSE translation
  sse/utility.py              SSE construction helper

frontend/widget/              Embeddable chat widget
  src/index.ts                SDK entrypoint (`ChatbotWidget.init`)
  src/widget.ts               Main widget class (Shadow DOM UI)
  src/stream-client.ts        POST-based SSE streaming client
  src/markdown.ts             Lightweight Markdown renderer
  src/styles/widget.css       Widget styles
  src/i18n/en.ts              English UI strings

shared/contracts.md           SSE protocol specification
tests/                        Backend test suite
```
