from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class RegisterRequest(BaseModel):
    email: str
    password: str
    clinic_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class MedicalRecord(BaseModel):
    id: str = Field(..., min_length=1)
    note: str = Field(..., min_length=1)
    department: Optional[str] = None


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1)
    n_results: int = Field(default=3, ge=1, le=20)


class AskQuery(BaseModel):
    question: str = Field(..., min_length=1)
    n_results: int = Field(default=3, ge=1, le=10)
    chat_history: Optional[List[Dict]] = None