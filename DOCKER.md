# Docker Setup Guide

This guide explains how to run the Bug Bounty Framework using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
- CLI tools installed on your host system:
  - `httpx`
  - `subfinder`
  - Other tools as needed (gau, waybackurls, etc.)

## Quick Start

1. **Copy environment file** (if not exists):
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file** with your settings:
   ```env
   POSTGRES_PASSWORD=your_secure_password
   # ... other settings
   ```

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

4. **Check logs**:
   ```bash
   docker-compose logs -f api
   ```

5. **Stop services**:
   ```bash
   docker-compose down
   ```

## Configuration

### Database Persistence

The PostgreSQL database data is stored in a Docker volume named `bb_postgres_data`. This ensures data persistence across container restarts.

To backup the database:
```bash
docker-compose exec postgres pg_dump -U postgres bbframework > backup.sql
```

To restore:
```bash
docker-compose exec -T postgres psql -U postgres bbframework < backup.sql
```

### Accessing Host Tools

The API container is configured to access CLI tools from your host system via bind mounts:

- `/usr/local/bin` → `/host/usr/local/bin` (read-only)
- `/usr/bin` → `/host/usr/bin` (read-only)

The application uses `TOOLS_PATH_PREFIX=/host` to locate these tools.

#### Custom Tool Locations

If your tools are installed in custom locations, you can:

1. **Add additional volumes** in `docker-compose.yml`:
   ```yaml
   volumes:
     - /usr/local/bin:/host/usr/local/bin:ro
     - /usr/bin:/host/usr/bin:ro
     - /opt/tools:/host/opt/tools:ro  # Custom location
     - /home/user/go/bin:/host/home/user/go/bin:ro  # Go tools
   ```

2. **Or use host network mode** (less isolated):
   ```yaml
   network_mode: host
   ```
   Then update `POSTGRES_HOST` to `localhost` in environment.

### Environment Variables

Key environment variables (see `.env.example`):

- `POSTGRES_PASSWORD` - Database password
- `TOOLS_PATH_PREFIX` - Path prefix for host tools (default: `/host`)
- `API_PORT` - API port (default: 8000)
- `LOG_LEVEL` - Logging level (default: INFO)

## Troubleshooting

### Tools Not Found

If tools are not found, check:

1. Tools are installed on host:
   ```bash
   which httpx
   which subfinder
   ```

2. Tools are in mounted directories:
   ```bash
   docker-compose exec api ls -la /host/usr/local/bin/ | grep httpx
   ```

3. Update `TOOLS_PATH_PREFIX` if tools are in different locations.

### Database Connection Issues

1. Check PostgreSQL is healthy:
   ```bash
   docker-compose ps postgres
   ```

2. Check logs:
   ```bash
   docker-compose logs postgres
   ```

3. Verify connection from API container:
   ```bash
   docker-compose exec api python -c "import asyncpg; print('OK')"
   ```

### Port Conflicts

If ports are already in use, change them in `.env`:
```env
API_PORT=8001
POSTGRES_PORT=5433
```

## Development

### Rebuild after code changes:
```bash
docker-compose build api
docker-compose up -d
```

### Run tests:
```bash
docker-compose exec api pytest
```

### Access API shell:
```bash
docker-compose exec api python
```

### View database:
```bash
docker-compose exec postgres psql -U postgres -d bbframework
```

## Production Considerations

1. **Change default passwords** in `.env`
2. **Use secrets** for sensitive data
3. **Set up proper backups** for database volume
4. **Configure reverse proxy** (nginx/traefik) for HTTPS
5. **Limit resource usage** with Docker resource limits
6. **Use Docker secrets** instead of environment variables for passwords

## Volume Management

### List volumes:
```bash
docker volume ls | grep bb
```

### Remove volume (⚠️ deletes database):
```bash
docker-compose down -v
```

### Backup volume:
```bash
docker run --rm -v bb_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

