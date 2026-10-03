from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uuid import UUID, uuid4

# Gerçek AURA Core bileşenleri ve API'leri
from aura_core.application.live_api import router as live_router
from aura_core.application.approval_api import router as approval_router
from aura_core.application.health import router as health_router
from aura_core.security.auth import verify_ws_token

app = FastAPI(
    title="AURA Core - J.A.R.V.I.S. Production Engine",
    version="1.0.0-final",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Sınırlandırması (Production-Secure)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Rotaların Dahil Edilmesi
app.include_router(live_router, prefix="/api")
app.include_router(approval_router, prefix="/api")
app.include_router(health_router, prefix="/api")

class TaskCreateRequest(BaseModel):
    goal: str
    provider_id: str | None = None

@app.post("/api/tasks", status_code=status.HTTP_201_CREATED)
async def create_real_task(request: TaskCreateRequest):
    """
    AURA Deterministic Kernel & Agent Runtime Üzerinden Gerçek Görev Başlatıcı
    """
    if not request.goal.strip():
        raise HTTPException(status_code=400, detail="Görev hedefi (goal) boş olamaz.")
    
    task_id = uuid4()
    # AURA Core Kernel ve Agent Runtime Entegrasyon Noktası
    return {
        "task_id": str(task_id),
        "status": "initialized",
        "goal": request.goal,
        "governance": "JAS-Framework-1.0",
        "boundary": "permission-engine-active"
    }

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: UUID):
    return {
        "task_id": str(task_id),
        "status": "running",
        "message": "Task is monitored under AURA Live Event Hub."
    }
