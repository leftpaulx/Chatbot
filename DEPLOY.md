# Deployment Guide — OB Chatbot

Single-EC2 deployment using Docker Compose with Nginx reverse proxy and TLS.

---

## Prerequisites

- An AWS account with EC2 access.
- A domain name (or subdomain) you can point to the EC2 instance.
- Your `.env` values ready (Snowflake credentials, JWT keys, etc.). See `.env.example`.

---

## 1. Launch an EC2 Instance

### Recommended specs

| Setting | Value |
|---------|-------|
| Instance type | **t3.medium** (2 vCPU, 4 GB RAM) |
| AMI | Ubuntu 22.04 LTS or Amazon Linux 2023 |
| Storage | 20 GB gp3 (minimum) |
| Key pair | Create or select an existing SSH key pair |

### Security Group rules

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| SSH | TCP | 22 | **Your IP only** | Remote access |
| HTTP | TCP | 80 | 0.0.0.0/0 | Redirect to HTTPS + ACME challenges |
| HTTPS | TCP | 443 | 0.0.0.0/0 | Application traffic |
| All traffic | All | All | **Outbound** | Snowflake API access |

### Elastic IP

1. Go to **EC2 > Elastic IPs > Allocate Elastic IP address**.
2. Associate it with your instance.
3. Note the IP -- you'll need it for DNS.

---

## 2. DNS Configuration

Create an **A record** pointing your domain (e.g., `chatbot.yourdomain.com`) to the Elastic IP.

If using Route 53, create a hosted zone and add the record there. If using an external registrar, add the A record in their DNS panel. DNS propagation can take up to 24 hours, but usually resolves within minutes.

---

## 3. Server Provisioning

SSH into your instance:

```bash
ssh -i your-key.pem ubuntu@<ELASTIC_IP>
```

### 3.1 Install Docker

```bash
# Update packages
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group (avoids needing sudo for docker commands)
sudo usermod -aG docker $USER

# Apply group change (or log out and back in)
newgrp docker

# Verify
docker --version
docker compose version
```

### 3.2 Clone the Repository

```bash
cd ~
git clone <YOUR_REPO_URL> chatbot
cd chatbot
```

### 3.3 Configure Environment

```bash
cp .env.example .env
nano .env   # fill in all required values
```

Required values you must set:
- `SNOWFLAKE_ACCOUNT` -- your Snowflake account identifier
- `SNOWFLAKE_PROJECT_USER` -- the service user
- `PRIVATE_USER_KEY` -- base64-encoded PEM private key (single line, no headers)
- `ALLOWED_ORIGINS` -- the origin(s) where the widget will be embedded
- `JWT_PUBLIC_KEY` -- base64-encoded PEM public key from the admin portal (required for production auth)

---

## 4. TLS Certificate Setup

### Option A: Let's Encrypt (recommended for production)

First, create the directory structure and get an initial certificate:

```bash
# Create certbot directories
mkdir -p certbot/conf certbot/www

# Get the initial certificate using standalone mode (before nginx starts)
sudo docker run --rm -p 80:80 \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/certbot/www:/var/www/certbot \
  certbot/certbot certonly \
    --standalone \
    -d chatbot.yourdomain.com \
    --email you@yourdomain.com \
    --agree-tos \
    --no-eff-email
```

The nginx config expects certs at `/etc/letsencrypt/live/default/`. Create a symlink:

```bash
sudo ln -s chatbot.yourdomain.com certbot/conf/live/default
```

### Option B: Self-signed (quick testing only)

```bash
mkdir -p certbot/conf/live/default

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certbot/conf/live/default/privkey.pem \
  -out certbot/conf/live/default/fullchain.pem \
  -subj "/CN=localhost"
```

### Option C: HTTP only (earliest testing)

If you just want to test without TLS at all, use the dev compose file:

```bash
docker compose -f docker-compose.dev.yml up -d --build
# App available at http://<ELASTIC_IP>:8000
```

Skip to section 6 for verification.

---

## 5. Start the Application

```bash
# Build and start all services
docker compose up -d --build

# Verify all containers are running
docker compose ps
```

You should see:
- `app` -- healthy
- `nginx` -- running

To also enable automatic TLS renewal:

```bash
docker compose --profile tls up -d
```

---

## 6. Verify

```bash
# Health check
curl -k https://chatbot.yourdomain.com/health

# Expected response:
# {"status":"ok","jwt_cached":true}

# Test the widget is served
curl -k https://chatbot.yourdomain.com/widget/
```

---

## 7. Day-to-Day Operations

### View logs

```bash
# Application logs (real-time)
docker compose logs -f app

# Nginx access/error logs
docker compose logs -f nginx

# Last 100 lines from the app
docker compose logs --tail 100 app
```

### Update the application

```bash
cd ~/chatbot
git pull
docker compose up -d --build
```

Docker Compose rebuilds only what changed. The widget is rebuilt inside the Docker build stage automatically.

### Restart

```bash
docker compose restart app          # restart just the app
docker compose restart              # restart everything
```

### Stop

```bash
docker compose down                 # stop and remove containers
docker compose down -v              # also remove volumes
```

### Check resource usage

```bash
docker stats                        # live CPU/memory per container
df -h                               # disk space
```

---

## 8. Updating the .env

If you change environment variables:

```bash
nano .env
docker compose up -d                # recreates containers with new env
```

---

## 9. TLS Certificate Renewal

If using Let's Encrypt with the `tls` profile, the certbot container auto-renews every 12 hours. To manually trigger renewal:

```bash
docker compose --profile tls run --rm certbot renew
docker compose restart nginx
```

---

## 10. Troubleshooting

### App won't start

```bash
docker compose logs app             # check for Python/config errors
docker compose exec app env         # verify env vars are loaded
```

### 502 Bad Gateway from Nginx

The app container isn't healthy yet. Wait for the health check to pass:

```bash
docker compose ps                   # check health status
docker compose logs app             # check for startup errors
```

### SSE streaming not working

Verify Nginx is not buffering:
- The `/chat` location block in `nginx/nginx.conf` has `proxy_buffering off`.
- `proxy_read_timeout` should be >= `AGENT_TIMEOUT_SEC` (default 300s).

### Can't connect to Snowflake

- Verify the Security Group allows all outbound traffic.
- Check `SNOWFLAKE_ACCOUNT` format -- should be like `xy12345.us-east-1`.
- Check `PRIVATE_USER_KEY` is properly base64-encoded.

---

## 11. Migration to Managed AWS

When the eng team is ready for a more robust deployment, here's the migration path. The stateless container architecture maps directly to managed services:

| Current (EC2) | Target (Managed AWS) |
|---------------|---------------------|
| Docker Compose on EC2 | **ECS Fargate** or **EKS** (no servers to manage) |
| Nginx on EC2 | **Application Load Balancer** (ALB) with ACM certificate |
| `.env` file on disk | **AWS Secrets Manager** or **SSM Parameter Store** |
| `docker compose logs` | **CloudWatch Container Insights** or Datadog |
| Manual `git pull` + rebuild | **CI/CD** via GitHub Actions deploying to **ECR** + ECS |
| Single EC2 instance | **ECS Service auto-scaling** (min 2, scale on CPU) |
| Elastic IP | **Route 53 alias** to ALB |
| In-memory rate limiter | **AWS WAF** rate-based rules or **API Gateway** |
| Self-managed TLS | **ACM** (free, auto-renewing certs on ALB) |

### Key migration steps

1. **Push container image to ECR**: The same Dockerfile works -- just push to a private ECR repository instead of building on the EC2 instance.

2. **Create an ECS Fargate service**: Define a task definition referencing the ECR image, with environment variables from Secrets Manager. Set desired count to 2+ for availability.

3. **Replace Nginx with ALB**: Create an ALB with an HTTPS listener (ACM cert). The ALB target group points to the ECS service. ALB natively supports SSE (just set idle timeout >= 300s).

4. **CI/CD pipeline**: GitHub Actions workflow that builds, pushes to ECR, and updates the ECS service on every push to `main`.

5. **DNS**: Switch the A record (or Route 53 alias) from the Elastic IP to the ALB DNS name.

### What stays the same

- The Docker image (same Dockerfile, same `app/` code)
- The FastAPI application code
- The widget build process
- The SSE protocol and Snowflake integration
- The health check endpoint (ALB uses `/health` as its target group health check)
