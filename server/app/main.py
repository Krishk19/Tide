from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base

# Create tables if not present
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

@app.get("/")
def read_root():
    return {
        "name": settings.PROJECT_NAME,
        "status": "online",
        "version": "1.0.0",
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
