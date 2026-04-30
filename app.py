from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import stripe
import os
import hmac
import hashlib
import json

from dotenv import load_dotenv

from database import init_db, get_db, Tenant, User, UsageLog, ChatMessage
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin
)
from models import LoginRequest, MedicalRecord, SearchQuery, AskQuery
from rag import add_record_to_rag, query_rag, upload_pdf_to_rag, ask_rag
from billing import create_checkout_session, get_plan_limits

load_dotenv()

app = FastAPI(
    title="Medical SaaS AI API",
    version="1.6-production"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
LEMON_WEBHOOK_SECRET = os.getenv("LEMON_WEBHOOK_SECRET", "")

ACTION_ASK = "ask"
ACTION_FILE = "file"
ACTION_RECORD = "record"


# =========================
# Flexible Register Model
# يقبل clinic_name أو clinic
# =========================

class RegisterRequest(BaseModel):
    email: str
    password: str
    clinic_name: Optional[str] = None
    clinic: Optional[str] = None

    def get_clinic_name(self) -> Optional[str]:
        return self.clinic_name or self.clinic


# =========================
# Startup
# =========================

@app.on_event("startup")
def startup():
    init_db()


# =========================
# Helpers
# =========================

def log_usage(db: Session, tenant_id: int, user_id: int, action: str):
    usage = UsageLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def get_monthly_usage(db: Session, tenant_id: int, action: str):
    now = datetime.utcnow()
    start_month = datetime(now.year, now.month, 1)

    return db.query(UsageLog).filter(
        UsageLog.tenant_id == tenant_id,
        UsageLog.action == action,
        UsageLog.created_at >= start_month
    ).count()


def check_limit(db: Session, tenant: Tenant, action: str):
    limits = get_plan_limits(tenant.plan)

    if action == ACTION_ASK:
        used = get_monthly_usage(db, tenant.id, ACTION_ASK)
        if used >= limits["questions_per_month"]:
            raise HTTPException(
                status_code=402,
                detail="Monthly question limit reached"
            )

    if action == ACTION_FILE:
        used = get_monthly_usage(db, tenant.id, ACTION_FILE)
        if used >= limits["files_per_month"]:
            raise HTTPException(
                status_code=402,
                detail="Monthly file limit reached"
            )

    if action == ACTION_RECORD:
        used = get_monthly_usage(db, tenant.id, ACTION_RECORD)
        if used >= limits["manual_records_per_month"]:
            raise HTTPException(
                status_code=402,
                detail="Monthly manual record limit reached"
            )


def activate_tenant_pro(
    db: Session,
    tenant: Tenant,
    subscription_id: Optional[str] = None
):
    tenant.plan = "pro"
    tenant.subscription_status = "active"

    if subscription_id:
        tenant.stripe_subscription_id = f"lemon_{subscription_id}"

    db.commit()
    db.refresh(tenant)
    return tenant


def downgrade_tenant_free(db: Session, tenant: Tenant):
    tenant.plan = "free"
    tenant.subscription_status = "cancelled"
    db.commit()
    db.refresh(tenant)
    return tenant


def find_tenant_from_lemon_event(db: Session, event: dict):
    custom_data = event.get("meta", {}).get("custom_data", {}) or {}
    tenant_id = custom_data.get("tenant_id")

    data = event.get("data", {}) or {}
    attributes = data.get("attributes", {}) or {}

    user_email = (
        attributes.get("user_email")
        or attributes.get("email")
        or attributes.get("customer_email")
    )

    if tenant_id:
        try:
            tenant = db.query(Tenant).filter(
                Tenant.id == int(tenant_id)
            ).first()
            if tenant:
                return tenant
        except Exception:
            pass

    if user_email:
        user = db.query(User).filter(User.email == user_email).first()
        if user:
            return db.query(Tenant).filter(
                Tenant.id == user.tenant_id
            ).first()

    return None


# =========================
# Basic Routes
# =========================

@app.get("/")
def home():
    return {
        "message": "Medical SaaS AI API is running",
        "version": "1.6-production",
        "docs": "/docs"
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "database": {
            "connected": db_ok
        },
        "environment": os.getenv("ENVIRONMENT", "production")
    }


# =========================
# Auth Routes
# =========================

@app.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    clinic_name = payload.get_clinic_name()

    if not clinic_name:
        raise HTTPException(
            status_code=400,
            detail="Clinic name is required"
        )

    existing = db.query(User).filter(User.email == payload.email).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    tenant = Tenant(
        name=clinic_name,
        plan="free",
        subscription_status="free"
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="admin",
        tenant_id=tenant.id
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "user_id": user.id,
        "tenant_id": tenant.id,
        "role": user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "tenant_id": tenant.id,
        "email": user.email,
        "role": user.role,
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status
    }


@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    token = create_access_token({
        "user_id": user.id,
        "tenant_id": tenant.id,
        "role": user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "email": user.email,
        "role": user.role,
        "tenant_id": tenant.id,
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status
    }


@app.get("/me")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    return {
        "email": user.email,
        "role": user.role,
        "tenant_id": tenant.id,
        "clinic": tenant.name,
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status
    }


# =========================
# Dashboard
# =========================

@app.get("/dashboard")
def dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    return {
        "clinic": tenant.name,
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status,
        "usage": {
            "questions": get_monthly_usage(db, tenant.id, ACTION_ASK),
            "files": get_monthly_usage(db, tenant.id, ACTION_FILE),
            "manual_records": get_monthly_usage(db, tenant.id, ACTION_RECORD)
        },
        "limits": get_plan_limits(tenant.plan)
    }


# =========================
# Billing
# =========================

@app.post("/billing/create-checkout-session")
def billing_checkout(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    return create_checkout_session(user.email, tenant.id)


# =========================
# Lemon Squeezy Webhook
# =========================

@app.post("/lemon-webhook")
async def lemon_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    if not LEMON_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Lemon webhook secret is not configured"
        )

    raw_body = await request.body()
    signature = request.headers.get("X-Signature", "")

    expected_signature = hmac.new(
        LEMON_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid Lemon Squeezy signature"
        )

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload"
        )

    event_name = event.get("meta", {}).get("event_name")
    data = event.get("data", {}) or {}
    subscription_id = str(data.get("id", ""))

    tenant = find_tenant_from_lemon_event(db, event)

    activate_events = {
        "order_created",
        "order_paid",
        "subscription_created",
        "subscription_updated",
        "subscription_payment_success"
    }

    cancel_events = {
        "subscription_cancelled",
        "subscription_expired",
        "subscription_payment_failed"
    }

    if event_name in activate_events:
        if tenant:
            tenant = activate_tenant_pro(
                db=db,
                tenant=tenant,
                subscription_id=subscription_id
            )
            return {
                "received": True,
                "updated": True,
                "event_name": event_name,
                "tenant_id": tenant.id,
                "plan": tenant.plan,
                "subscription_status": tenant.subscription_status
            }

        return {
            "received": True,
            "updated": False,
            "reason": "tenant_not_found",
            "event_name": event_name
        }

    if event_name in cancel_events:
        if tenant:
            tenant = downgrade_tenant_free(db, tenant)
            return {
                "received": True,
                "updated": True,
                "event_name": event_name,
                "tenant_id": tenant.id,
                "plan": tenant.plan,
                "subscription_status": tenant.subscription_status
            }

        return {
            "received": True,
            "updated": False,
            "reason": "tenant_not_found",
            "event_name": event_name
        }

    return {
        "received": True,
        "updated": False,
        "event_name": event_name
    }


# =========================
# Admin Manual Upgrade
# =========================

@app.post("/admin/activate-pro")
def manual_activate_pro(
    target_email: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    target_user = db.query(User).filter(
        User.email == target_email
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    tenant = db.query(Tenant).filter(
        Tenant.id == target_user.tenant_id
    ).first()

    activate_tenant_pro(db, tenant, "manual")

    return {
        "status": "success",
        "email": target_email,
        "tenant_id": tenant.id,
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status
    }


# =========================
# Medical Records
# =========================

@app.post("/add-record")
def add_record(
    record: MedicalRecord,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    check_limit(db, tenant, ACTION_RECORD)

    department = add_record_to_rag(
        tenant_id=tenant.id,
        record_id=record.id,
        note=record.note,
        department=record.department,
        created_by=user.email
    )

    log_usage(db, tenant.id, user.id, ACTION_RECORD)

    return {
        "status": "success",
        "record_id": record.id,
        "detected_department": department,
        "usage": {
            "manual_records": get_monthly_usage(db, tenant.id, ACTION_RECORD)
        }
    }


@app.post("/search")
def search(
    query: SearchQuery,
    user: User = Depends(get_current_user)
):
    results = query_rag(
        tenant_id=user.tenant_id,
        query=query.query,
        n_results=query.n_results
    )

    return {
        "query": query.query,
        "ids": results.get("ids", [[]])[0],
        "results": results.get("documents", [[]])[0],
        "metadata": results.get("metadatas", [[]])[0],
        "distances": results.get("distances", [[]])[0]
    }


@app.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    check_limit(db, tenant, ACTION_FILE)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    content = await file.read()

    try:
        chunks_added = upload_pdf_to_rag(
            tenant_id=tenant.id,
            file=content,
            filename=file.filename,
            created_by=user.email
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    log_usage(db, tenant.id, user.id, ACTION_FILE)

    return {
        "status": "success",
        "filename": file.filename,
        "chunks_added": chunks_added,
        "usage": {
            "files": get_monthly_usage(db, tenant.id, ACTION_FILE)
        }
    }


@app.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    check_limit(db, tenant, ACTION_FILE)

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are allowed"
        )

    df = pd.read_csv(file.file)

    if "clinical_note" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain clinical_note column"
        )

    added_count = 0

    for i, row in df.iterrows():
        note = str(row["clinical_note"])

        if note.strip():
            department = "unknown"

            if "department" in df.columns and pd.notna(row["department"]):
                department = str(row["department"])

            add_record_to_rag(
                tenant_id=tenant.id,
                record_id=f"csv_{file.filename}_{i}",
                note=note,
                department=department,
                created_by=user.email
            )

            added_count += 1

    log_usage(db, tenant.id, user.id, ACTION_FILE)

    return {
        "status": "success",
        "records_added": added_count,
        "usage": {
            "files": get_monthly_usage(db, tenant.id, ACTION_FILE)
        }
    }


# =========================
# Ask AI
# =========================

@app.post("/ask")
def ask(
    payload: AskQuery,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(
        Tenant.id == user.tenant_id
    ).first()

    check_limit(db, tenant, ACTION_ASK)

    try:
        answer = ask_rag(
            tenant_id=tenant.id,
            question=payload.question,
            n_results=payload.n_results,
            chat_history=payload.chat_history
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    db.add(ChatMessage(
        tenant_id=tenant.id,
        user_id=user.id,
        role="user",
        content=payload.question
    ))

    db.add(ChatMessage(
        tenant_id=tenant.id,
        user_id=user.id,
        role="assistant",
        content=answer.get("answer", "")
    ))

    log_usage(db, tenant.id, user.id, ACTION_ASK)

    return {
        **answer,
        "usage": {
            "questions": get_monthly_usage(db, tenant.id, ACTION_ASK)
        }
    }