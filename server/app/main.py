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

# Create SQLite tables on startup
Base.metadata.create_all(bind=engine)

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
