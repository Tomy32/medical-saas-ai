import os
import hmac
import hashlib
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from jose import jwt
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

# =========================
# CONFIG
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 240))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
LEMON_WEBHOOK_SECRET = os.getenv("LEMON_WEBHOOK_SECRET", "secret")

# =========================
# DB
# =========================
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)
    clinic = Column(String)

    plan = Column(String, default="free")
    subscription_status = Column(String, default="free")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# AUTH
# =========================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# =========================
# SCHEMAS
# =========================
class RegisterRequest(BaseModel):
    email: str
    password: str
    clinic: str


class LoginRequest(BaseModel):
    email: str
    password: str


# =========================
# APP
# =========================
app = FastAPI(title="Medical SaaS AI API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# ROUTES
# =========================
@app.get("/")
def home():
    return {"message": "Hello World!"}


@app.get("/health")
def health():
    return {"status": "ok", "environment": "production"}


# =========================
# REGISTER
# =========================
@app.post("/register")
def register(data: RegisterRequest, db=Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        email=data.email,
        password=data.password,
        clinic=data.clinic,
        plan="free",
        subscription_status="free",
    )

    db.add(user)
    db.commit()

    return {"message": "User created"}


# =========================
# LOGIN
# =========================
@app.post("/login")
def login(data: LoginRequest, db=Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or user.password != data.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.email})

    return {"access_token": token, "token_type": "bearer"}


# =========================
# ME
# =========================
@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "email": user.email,
        "clinic": user.clinic,
        "plan": user.plan,
        "subscription_status": user.subscription_status,
    }


# =========================
# DASHBOARD
# =========================
@app.get("/dashboard")
def dashboard(user: User = Depends(get_current_user)):
    limits = {
        "free": {"questions": 20, "files": 2, "records": 50},
        "pro": {"questions": 1000, "files": 100, "records": 5000},
    }

    plan_limits = limits.get(user.plan, limits["free"])

    return {
        "clinic": user.clinic,
        "plan": user.plan,
        "subscription_status": user.subscription_status,
        "limits": plan_limits,
    }


# =========================
# UPGRADE FUNCTION
# =========================
def upgrade_user_to_pro(email: str):
    db = SessionLocal()

    user = db.query(User).filter(User.email == email).first()

    if user:
        user.plan = "pro"
        user.subscription_status = "active"
        db.commit()

    db.close()


# =========================
# LEMON WEBHOOK
# =========================
@app.post("/lemon-webhook")
async def lemon_webhook(request: Request, x_signature: str = Header(None)):
    body = await request.body()

    digest = hmac.new(
        LEMON_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if x_signature != digest:
        return {"error": "Invalid signature"}

    data = await request.json()

    event = data.get("meta", {}).get("event_name")

    if event == "order_paid":
        email = data["data"]["attributes"]["user_email"]
        upgrade_user_to_pro(email)

    return {"status": "ok"}