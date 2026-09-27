import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import engine, Base
from app.api.auth import router as auth_router
from app.api.assignments import router as assignments_router
from app.api.sessions import router as sessions_router
from app.api.exam import router as exam_router
from app.api.telemetry import router as telemetry_router
from app.api.classroom import router as classroom_router
from app.api.dashboard import router as dashboard_router
from app.api.similarity import router as similarity_router

from sqlalchemy import text

# Create SQLite tables on startup
Base.metadata.create_all(bind=engine)

# Backwards-compatible schema upgrades for existing SQLite databases
def upgrade_schema():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE students_in_session ADD COLUMN risk_score INTEGER DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE flags ADD COLUMN severity VARCHAR(20) DEFAULT 'medium'"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE flags ADD COLUMN notes TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE students_in_session ADD COLUMN extra_time_seconds INTEGER DEFAULT 0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS code_snapshots (
                    id INTEGER PRIMARY KEY,
                    student_session_id INTEGER NOT NULL REFERENCES students_in_session(id),
                    code TEXT NOT NULL,
                    lines_count INTEGER NOT NULL DEFAULT 0,
                    chars_count INTEGER NOT NULL DEFAULT 0,
                    is_paste_event BOOLEAN NOT NULL DEFAULT 0,
                    ts DATETIME NOT NULL
                )
            """))
            conn.commit()
        except Exception:
            pass

upgrade_schema()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="LAN-based, locked-down coding exam platform for college labs",
    version="1.0.0",
)

# Allow LAN access from student kiosks and teacher browser dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers under /api
app.include_router(auth_router, prefix="/api")
app.include_router(assignments_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(exam_router, prefix="/api")
app.include_router(classroom_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(similarity_router, prefix="/api")
app.include_router(telemetry_router)

# Mount Static UI Directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STUDENT_DIR = os.path.join(BASE_DIR, "client-student", "src")
TEACHER_DIR = os.path.join(BASE_DIR, "client-teacher")

if os.path.exists(STUDENT_DIR):
    app.mount("/student", StaticFiles(directory=STUDENT_DIR, html=True), name="student")

if os.path.exists(TEACHER_DIR):
    app.mount("/dashboard", StaticFiles(directory=TEACHER_DIR, html=True), name="dashboard")

@app.get("/")
def read_root():
    return {
        "name": settings.PROJECT_NAME,
        "status": "online",
        "version": "1.0.0",
        "docs_url": "/docs",
        "student_portal": "/student",
        "teacher_dashboard": "/dashboard"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/api/system/info")
def system_info():
    """Returns local LAN IPs and portal URLs for lab projection."""
    import socket
    hostname = socket.gethostname()
    local_ips = []
    try:
        addrs = socket.getaddrinfo(hostname, None)
        for item in addrs:
            ip = item[4][0]
            if ":" not in ip and not ip.startswith("127."):
                if ip not in local_ips:
                    local_ips.append(ip)
    except Exception:
        pass

    primary_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
    except Exception:
        if local_ips:
            primary_ip = local_ips[0]

    return {
        "status": "online",
        "hostname": hostname,
        "primary_lan_ip": primary_ip,
        "all_ips": local_ips,
        "student_portal_url": f"http://{primary_ip}:8000/student",
        "teacher_dashboard_url": f"http://{primary_ip}:8000/dashboard"
    }
