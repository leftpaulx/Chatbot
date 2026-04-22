# Deployment Guide - OB Chatbot

This project now deploys as a **single application container**. The Docker image builds the widget, serves it from `/widget/`, and exposes the FastAPI API from the same process on port `8000`.

That means production only needs one app container:

- API: `/chat`
- Health check: `/health`
- Widget assets: `/widget/`

## Overview

The production flow is:

1. Provision a host or container platform.
2. Put the app's `.env` on that host.
3. Build the Docker image from this repo.
4. Run a single container that exposes port `8000`.
5. Terminate TLS outside the container if you need HTTPS.

## 1. Prerequisites

- A Linux host, VM, or container platform with Docker available
- Snowflake credentials ready in `.env`
- A shared `API_KEY` for the widget to send as `Authorization: Bearer <API_KEY>`
- Optional: a domain name if you want to expose the app publicly

If you are deploying on EC2, a `t3.medium` with 20 GB of storage is enough for a first production host.

## 2. Network and DNS

### If you are testing directly on the host

Open:

- `22/tcp` from your IP only for SSH
- `8000/tcp` from your IP or trusted office/VPN ranges

### If you are putting TLS in front of the app

Expose:

- `22/tcp` from your IP only for SSH
- `80/tcp` and `443/tcp` on the reverse proxy or load balancer
- `8000/tcp` only between that proxy/load balancer and the app host

Point your DNS record to the host or load balancer that fronts the container.

## 3. Install Docker

Example for Ubuntu:

```bash
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
```

## 4. Clone the Repository

```bash
cd ~
git clone <YOUR_REPO_URL> chatbot
cd chatbot
```

## 5. Configure Environment

```bash
cp .env.example .env
nano .env
```

Required production values:

- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_PROJECT_USER`
- `PRIVATE_USER_KEY`
- `API_KEY`

Common optional values:

- `ALLOWED_ORIGINS`
- `AGENT_PATH`
- `AGENT_TIMEOUT_SEC`
- `MAX_CONCURRENCY`
- `RATE_LIMIT_RPM`
- `LOG_LEVEL`
- `LOG_FORMAT`

For same-origin production, `ALLOWED_ORIGINS` can simply be your app domain, for example `https://chatbot.yourdomain.com`.

## 6. Build the Image

```bash
docker build -t ob-chatbot .
```

The Docker build does both of these steps for you:

- Builds the widget from `frontend/widget/`
- Copies the built assets into the Python runtime image so FastAPI can serve `/widget/`

## 7. Run the Container

```bash
docker run -d \
  --name ob-chatbot \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  ob-chatbot
```

At this point:

- `http://<host>:8000/health` should answer health checks
- `http://<host>:8000/widget/` should serve the built frontend
- `http://<host>:8000/chat` is the SSE chat endpoint

## 8. HTTPS / Reverse Proxy Options

The container itself only serves plain HTTP on port `8000`. For production HTTPS, terminate TLS outside the container.

Good options:

- AWS Application Load Balancer
- Nginx on the host
- Caddy on the host
- Cloudflare Tunnel or another edge proxy

The important part is that both of these paths route to the same container:

- `/chat`
- `/widget/`

Because the widget and API come from the same app container, the recommended production widget config is:

```javascript
ChatbotWidget.init({
  mountElement: "#chat-container",
  apiBaseUrl: window.location.origin,
  getAccessToken: async () => window.__CHATBOT_API_KEY__,
  brand: "your-brand-code",
});
```

## 9. Verify the Deployment

Run these checks on the host first:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/widget/
```

Expected health response:

```json
{"status":"ok","jwt_cached":true}
```

If you placed TLS in front, also verify through the public URL:

```bash
curl https://chatbot.yourdomain.com/health
curl https://chatbot.yourdomain.com/widget/
```

## 10. Day-to-Day Operations

### View logs

```bash
docker logs -f ob-chatbot
docker logs --tail 100 ob-chatbot
```

### Restart

```bash
docker restart ob-chatbot
```

### Stop

```bash
docker stop ob-chatbot
docker rm ob-chatbot
```

### Check resource usage

```bash
docker stats
df -h
```

## 11. Update the Application

```bash
cd ~/chatbot
git pull
docker build -t ob-chatbot .
docker stop ob-chatbot
docker rm ob-chatbot
docker run -d \
  --name ob-chatbot \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  ob-chatbot
```

The widget is rebuilt automatically during the Docker image build, so there is no separate frontend deploy step.

## 12. Update the Environment

If `.env` changes:

```bash
nano .env
docker stop ob-chatbot
docker rm ob-chatbot
docker run -d \
  --name ob-chatbot \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  ob-chatbot
```

## 13. Troubleshooting

### Container exits immediately

Check the logs:

```bash
docker logs ob-chatbot
```

The most common cause is a missing or malformed required environment variable.

### `/health` returns degraded

The container is up, but Snowflake auth or configuration failed. Re-check:

- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_PROJECT_USER`
- `PRIVATE_USER_KEY`

### Widget loads but chat calls return `401`

The widget is sending the wrong Bearer token. Make sure the value returned by `getAccessToken()` matches the server-side `API_KEY` exactly.

### Browser shows CORS errors

If the widget is served from the same origin as the API, use `apiBaseUrl: window.location.origin`.

If you intentionally run the widget from a different origin in development, add that origin to `ALLOWED_ORIGINS`.

### Widget route returns `404`

The image was likely not rebuilt after frontend changes. Rebuild the Docker image and restart the container:

```bash
docker build -t ob-chatbot .
docker restart ob-chatbot
```
