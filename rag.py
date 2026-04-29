import os
import re
import uuid
import requests
import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./medical_db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

SYMPTOMS = [
    "cough", "fever", "chest pain", "headache", "weakness",
    "respiratory distress", "shortness of breath", "asthma",
    "bleeding", "seizure", "stroke", "hypertension",
    "high blood pressure", "dizziness", "fatigue", "nausea", "vomiting"
]

MEDICATIONS = [
    "aspirin", "paracetamol", "acetaminophen", "ibuprofen",
    "metformin", "insulin", "amoxicillin", "warfarin",
    "heparin", "atorvastatin", "lisinopril",
    "albuterol", "salbutamol"
]

DIAGNOSES = [
    "pneumonia", "asthma", "hypertension", "diabetes",
    "stroke", "myocardial infarction", "heart failure",
    "infection", "sepsis"
]

DEPARTMENT_MAP = {
    "Pulmonology": [
        "pulmonology", "cough", "respiratory", "asthma",
        "shortness of breath", "lung", "pneumonia",
        "respiratory distress"
    ],
    "Cardiology": [
        "cardiology", "chest pain", "heart", "hypertension",
        "blood pressure", "palpitation", "myocardial infarction"
    ],
    "Neurology": [
        "neurology", "seizure", "stroke", "brain",
        "headache", "weakness"
    ],
    "Emergency": [
        "emergency", "trauma", "accident", "bleeding",
        "severe pain"
    ],
    "ICU": [
        "icu", "critical", "ventilator", "shock",
        "intensive care", "sepsis"
    ]
}


def get_collection(tenant_id: int):
    return chroma_client.get_or_create_collection(
        name=f"medical_records_tenant_{tenant_id}",
        embedding_function=embedding_fn
    )


def clean_text(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_terms(text: str, terms: list[str]) -> list[str]:
    text_lower = text.lower()
    found = []

    for term in sorted(terms, key=len, reverse=True):
        if term.lower() in text_lower and term not in found:
            found.append(term)

    return found


def extract_department(text: str) -> str:
    text_lower = text.lower()

    for department, keywords in DEPARTMENT_MAP.items():
        if any(keyword in text_lower for keyword in keywords):
            return department

    return "unknown"


def detect_intent(question: str) -> str:
    q = question.lower()

    if any(k in q for k in ["summary", "summarize", "summarise", "brief", "overview"]):
        return "summary"

    if any(k in q for k in ["where", "which department", "which clinic", "refer", "referred", "department"]):
        return "department"

    if any(k in q for k in ["symptom", "symptoms", "signs", "complaints"]):
        return "symptoms"

    if any(k in q for k in ["medication", "medications", "medicine", "drug", "drugs", "treatment"]):
        return "medications"

    if any(k in q for k in ["diagnosis", "diagnoses", "condition", "disease"]):
        return "diagnosis"

    return "general"


def triage_level(text: str) -> str:
    text = text.lower()

    if any(k in text for k in [
        "respiratory distress", "seizure", "stroke",
        "shock", "ventilator", "sepsis", "critical"
    ]):
        return "HIGH"

    if any(k in text for k in [
        "chest pain", "hypertension", "high blood pressure",
        "shortness of breath"
    ]):
        return "MEDIUM"

    return "LOW"


def select_best_doc(question: str, docs: list[str], metas: list[dict]):
    q = clean_text(question)
    q_words = set(q.split())

    best_score = -1
    best_index = 0

    for i, doc in enumerate(docs):
        d = clean_text(doc)
        d_words = set(d.split())

        score = len(q_words.intersection(d_words)) * 2

        for term in SYMPTOMS + MEDICATIONS + DIAGNOSES:
            term_clean = clean_text(term)
            if term_clean in q and term_clean in d:
                score += 5

        meta = metas[i] if i < len(metas) else {}
        dept = str(meta.get("department", "")).lower()

        if dept and dept != "unknown" and dept in d:
            score += 2

        if score > best_score:
            best_score = score
            best_index = i

    return docs[best_index], metas[best_index] if best_index < len(metas) else {}, best_index


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150):
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        chunk = " ".join(words[start:start + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def add_record_to_rag(tenant_id: int, record_id: str, note: str, department: str, created_by: str):
    collection = get_collection(tenant_id)

    if not department or department.lower() == "unknown":
        department = extract_department(note)

    collection.upsert(
        ids=[record_id],
        documents=[clean_text(note)],
        metadatas=[{
            "department": department,
            "original_note": note,
            "source": "manual",
            "symptoms": ", ".join(find_terms(note, SYMPTOMS)),
            "medications": ", ".join(find_terms(note, MEDICATIONS)),
            "diagnoses": ", ".join(find_terms(note, DIAGNOSES)),
            "created_by": created_by
        }]
    )

    return department


def query_rag(tenant_id: int, query: str, n_results: int):
    collection = get_collection(tenant_id)
    return collection.query(
        query_texts=[clean_text(query)],
        n_results=n_results
    )


def upload_pdf_to_rag(tenant_id: int, file, filename: str, created_by: str):
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")

    with open(file_path, "wb") as f:
        f.write(file)

    reader = PdfReader(file_path)
    text = ""

    for page in reader.pages:
        text += "\n" + (page.extract_text() or "")

    if not text.strip():
        raise ValueError("No readable text found in PDF")

    collection = get_collection(tenant_id)
    chunks = chunk_text(text)
    added_count = 0

    for index, chunk in enumerate(chunks):
        cleaned = clean_text(chunk)

        if cleaned:
            collection.upsert(
                ids=[f"pdf_{file_id}_{index}"],
                documents=[cleaned],
                metadatas=[{
                    "source": filename,
                    "source_type": "pdf",
                    "chunk": index,
                    "department": extract_department(chunk),
                    "original_note": chunk[:1000],
                    "symptoms": ", ".join(find_terms(chunk, SYMPTOMS)),
                    "medications": ", ".join(find_terms(chunk, MEDICATIONS)),
                    "diagnoses": ", ".join(find_terms(chunk, DIAGNOSES)),
                    "created_by": created_by
                }]
            )
            added_count += 1

    return added_count


def ask_rag(tenant_id: int, question: str, n_results: int, chat_history=None):
    intent = detect_intent(question)
    results = query_rag(tenant_id, question, n_results)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not docs or not distances:
        return {
            "question": question,
            "answer": "I don't know based on the provided data.",
            "intent": intent,
            "source": "no_context",
            "context": "",
            "confidence": 0,
            "triage": "UNKNOWN",
            "evidence_count": 0,
            "metadata": [],
            "distances": []
        }

    combined = sorted(zip(distances, docs, metas), key=lambda x: x[0])
    best_distance = combined[0][0]
    dynamic_threshold = best_distance + 0.20

    filtered = [item for item in combined if item[0] <= dynamic_threshold]
    if not filtered:
        filtered = combined[:1]

    sorted_distances = [x[0] for x in filtered]
    sorted_docs = [x[1] for x in filtered]
    sorted_metas = [x[2] for x in filtered]

    best_doc, best_meta, _ = select_best_doc(question, sorted_docs, sorted_metas)

    unique_docs = list(dict.fromkeys(sorted_docs))
    context = "\n".join(unique_docs)
    evidence_count = len(unique_docs)

    avg_distance = sum(sorted_distances) / len(sorted_distances)
    confidence = round(max(0.3, 1 - avg_distance), 2)
    triage = triage_level(best_doc)

    base = {
        "question": question,
        "intent": intent,
        "context": context,
        "best_evidence": best_doc,
        "best_metadata": best_meta,
        "confidence": confidence,
        "triage": triage,
        "evidence_count": evidence_count,
        "metadata": sorted_metas,
        "distances": sorted_distances
    }

    if intent == "department":
        department = best_meta.get("department", "unknown")
        if department and department.lower() != "unknown":
            return {
                **base,
                "answer": f"Patient should go to {department} department.",
                "source": "metadata_single_evidence"
            }

        detected = extract_department(best_doc)
        if detected != "unknown":
            return {
                **base,
                "answer": f"Patient should go to {detected} department.",
                "source": "clinical_extractor_single_evidence"
            }

    if intent == "symptoms":
        symptoms = find_terms(best_doc, SYMPTOMS)
        return {
            **base,
            "answer": f"Symptoms mentioned: {', '.join(symptoms)}." if symptoms else "No symptoms are mentioned in the most relevant evidence.",
            "source": "clinical_extractor_single_evidence"
        }

    if intent == "medications":
        medications = find_terms(best_doc, MEDICATIONS)
        return {
            **base,
            "answer": f"Medications mentioned: {', '.join(medications)}." if medications else "No medications are mentioned in the most relevant evidence.",
            "source": "clinical_extractor_single_evidence"
        }

    if intent == "diagnosis":
        diagnoses = find_terms(best_doc, DIAGNOSES)
        return {
            **base,
            "answer": f"Possible diagnoses mentioned in the most relevant evidence: {', '.join(diagnoses)}." if diagnoses else "No diagnosis is mentioned in the most relevant evidence.",
            "source": "clinical_extractor_single_evidence"
        }

    history_text = ""
    if chat_history:
        for item in chat_history[-6:]:
            history_text += f"{item.get('role', 'user')}: {item.get('content', '')}\n"

    prompt = f"""
You are a cautious clinical reasoning assistant.

Medical reasoning rules:
- Use ONLY the Best Evidence as the primary source.
- Use Additional Filtered Evidence only if it supports the same patient context.
- Do NOT mix unrelated patient records.
- Do NOT invent symptoms, diagnosis, medication, or treatment.
- Do NOT provide a definitive diagnosis unless explicitly stated.
- If evidence is insufficient, say: "I don't know based on the provided data."
- Answer in one short, clinically safe paragraph.

Intent:
{intent}

Triage:
{triage}

Best Evidence:
{best_doc}

Best Metadata:
{best_meta}

Additional Filtered Evidence:
{context}

Chat History:
{history_text}

Question:
{question}

Answer:
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )

    response.raise_for_status()
    data = response.json()

    return {
        **base,
        "answer": data.get("response", "").strip(),
        "source": "ollama_summary_single_evidence" if intent == "summary" else "ollama_safe_single_evidence"
    }