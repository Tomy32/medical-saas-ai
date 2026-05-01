from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
import os
import requests
import chromadb
from chromadb.utils import embedding_functions
from database import init_db, update_user_to_pending, approve_user, get_pending_users, get_user, register_user

app = FastAPI(title="Medical AI Pro API")

# الإعدادات
ADMIN_KEY = os.getenv("ADMIN_KEY", "MY_SECRET_ADMIN_123")
UPLOAD_DIR = "medical_db/receipts"
os.makedirs(UPLOAD_DIR, exist_ok=True)
init_db()

# إعداد ChromaDB
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
chroma_client = chromadb.PersistentClient(path="./medical_db/vector_db")
collection = chroma_client.get_or_create_collection(name="medical_records", embedding_function=embedding_fn)

@app.get("/health")
def health(): return {"status": "running"}

@app.get("/me")
def me(email: str):
    user = get_user(email)
    if not user: return {"plan": "free", "status": "none"}
    return {"email": user[0], "plan": user[1], "status": user[2]}

@app.post("/register")
def register(email: str = Form(...), password: str = Form(...)):
    if register_user(email, password): return {"status": "success"}
    return {"status": "error", "message": "User exists"}

# --- نظام الدفع اليدوي ---

@app.post("/upload-receipt")
async def upload_receipt(email: str = Form(...), file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, f"{email}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(await file.read())
    update_user_to_pending(email, f"{email}_{file.filename}")
    return {"status": "success"}

@app.get("/admin/pending")
def view_pending(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_KEY: raise HTTPException(status_code=403)
    return get_pending_users()

@app.post("/admin/approve")
def admin_approve(email: str, x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_KEY: raise HTTPException(status_code=403)
    approve_user(email)
    return {"status": "success"}

# --- محرك البحث والذكاء الاصطناعي ---

@app.post("/ask")
def ask_question(question: str = Form(...), email: str = Form(...)):
    user = get_user(email)
    # حماية: منع غير المشتركين من الأسئلة الكثيرة (مثال)
    if not user or user[1] == 'free':
        # منطق تحديد عدد الأسئلة...
        pass

    results = collection.query(query_texts=[question], n_results=3)
    context = "\n".join(results["documents"][0])
    
    prompt = f"Context: {context}\nQuestion: {question}\nAnswer as a medical assistant:"
    
    # الربط مع Ollama (بفرض تشغيله محلياً أو عبر Docker)
    res = requests.post("http://host.docker.internal:11434/api/generate", 
                        json={"model": "llama3.2", "prompt": prompt, "stream": False})
    return {"answer": res.json().get("response", "No response")}