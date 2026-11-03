# Website & API Uptime Monitor

Project 11 MVP, following the supplied project documentation.

## Phase 1 scope
- React + Vite + TypeScript + Tailwind CSS frontend
- FastAPI backend
- PostgreSQL through Docker Compose
- SQLAlchemy models and Alembic initial migration
- `/health/live` and `/health/ready` endpoints

Authentication, monitor CRUD, scheduled checks, alerts, charts and deployment are later phases.

## Windows 11 prerequisites
Install Docker Desktop (WSL 2 backend), Git for Windows, Node.js 22 LTS and Python 3.12.
Node and Python are optional for this Docker-based run, but useful for local development.

Verify in PowerShell:
```powershell
docker --version
docker compose version
git --version
```

## Start
From the repository root:
```powershell
Copy-Item apps/api/.env.example apps/api/.env
docker compose up --build
```

Open:
- Frontend: http://localhost:5173
- FastAPI docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health/live
- Readiness: http://localhost:8000/health/ready

The API container runs `alembic upgrade head` before starting FastAPI.

## Useful commands
```powershell
docker compose ps
docker compose logs -f
docker compose logs -f api
docker compose down
docker compose down -v
```
Warning: `docker compose down -v` deletes the local PostgreSQL volume and its data.

## Local database connection
Host `localhost`, port `5432`, database `uptime_monitor`, username `uptime_user`, password `uptime_password`.
Inside Docker, the API uses hostname `db`, not `localhost`.

## Push to a new GitHub repository
Create an empty GitHub repository named `uptime-monitor`. Then:
```powershell
git init
git add .
git commit -m "chore: initialize uptime monitor foundation"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/uptime-monitor.git
git push -u origin main
```
Replace `YOUR-USERNAME` with your GitHub username.

## Security note
Credentials are for local development only. Before hosted deployment, use strong secrets or a secret manager. Do not expose PostgreSQL publicly. User-configured monitor URLs must later have SSRF protection before checks are implemented.

## Database backup and restore

Create and validate a PostgreSQL backup:

`./scripts/backup-db.sh`

Backups are saved in `./backups/` by default. For a different secure location, set `BACKUP_DIR` before running the script.

Restore into an empty, non-primary database:

`./scripts/restore-db.sh ./backups/your-backup.dump uptime_monitor_restore_test --confirm`

The restore script validates the archive, checks that the target database is empty, and prevents restoring into the configured primary database.

**Security:** Backups may contain sensitive application data. Store them securely and do not commit or share them. The `backups/` directory and dump files are excluded by `.gitignore`.
