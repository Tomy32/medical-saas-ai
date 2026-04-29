# 🏥 Private Medical AI Assistant (Local RAG System)

## 🔒 Overview

A fully local medical AI assistant that allows healthcare providers to search, analyze, and chat with clinical records securely — without using external APIs.

## 🚀 Features

* 🧠 Local LLM (Ollama - Llama 3.2)
* 📚 RAG with ChromaDB
* 🔍 Semantic search over medical records
* 💬 Chat interface with intent detection
* 📄 PDF & CSV ingestion
* 🧬 Clinical extraction (symptoms, diagnosis, medications)
* ⚠️ Triage system (LOW / MEDIUM / HIGH)
* 📊 Confidence scoring
* 🔐 Login system (basic auth)

## 🏗️ Architecture

User → Streamlit UI → FastAPI → ChromaDB → Ollama

## 📦 Tech Stack

* FastAPI
* Streamlit
* ChromaDB
* Sentence Transformers
* Ollama (Llama 3.2)
* Pandas

## ▶️ Run Locally

### 1. Install dependencies

```
pip install -r requirements.txt
```

### 2. Run Ollama

```
ollama run llama3.2
```

### 3. Start API

```
uvicorn app:app --reload
```

### 4. Start UI

```
streamlit run ui.py
```

---

## ⚠️ Disclaimer

This system is for research and assistance only. It does NOT provide medical diagnosis.

---

## 💼 Use Cases

* Clinics (internal AI assistant)
* Medical research
* Startups (AI prototypes)
* Data analysis of clinical notes

---

## 📧 Contact

Available for customization & deployment.
