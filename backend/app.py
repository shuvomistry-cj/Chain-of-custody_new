from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import uvicorn
from .db import create_tables
from .api import auth, evidence, transfer, audit, analysis
from .core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    yield
    # Shutdown
    pass


app = FastAPI(
    title=settings.app_name,
    description="Chain of Custody Evidence Management System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
# CORS configuration: allow local Streamlit by default and optionally configure via env
# CORS_ORIGINS: comma-separated list of exact origins
# CORS_ORIGIN_REGEX: regex string for dynamic origins (e.g., ^https://.*\\.streamlit\\.app$)
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").strip()
allow_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
allow_origin_regex = os.getenv("CORS_ORIGIN_REGEX", r"^https://.*\\.streamlit\\.app$").strip()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex if allow_origin_regex else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(evidence.router, prefix="/evidence", tags=["Evidence"])
app.include_router(transfer.router, prefix="/transfer", tags=["Transfer"])
app.include_router(audit.router, prefix="/audit", tags=["Audit"])
app.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": f"Welcome to {settings.app_name}", "status": "running"}


@app.get("/healthz")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": settings.app_name}


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
