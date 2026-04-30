import os
from urllib.parse import quote_plus

import requests
import streamlit as st
from dotenv import load_dotenv


# =========================
# Load local .env
# =========================

load_dotenv()


# =========================
# Page config
# =========================

st.set_page_config(
    page_title="Medical SaaS AI Platform",
    page_icon="🩺",
    layout="wide"
)


# =========================
# Config helper
# Works locally with .env
# Works on Streamlit Cloud with st.secrets
# =========================

def get_config(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass

    return os.getenv(name, default)


API_URL = get_config(
    "API_URL",
    "https://medical-saas-ai.onrender.com"
).rstrip("/")

PAYMENT_PROVIDER = get_config("PAYMENT_PROVIDER", "lemon")

LEMON_CHECKOUT_URL = get_config(
    "LEMON_CHECKOUT_URL",
    ""
)

APP_URL = get_config(
    "APP_URL",
    "http://localhost:8501"
)


# =========================
# Session helpers
# =========================

def init_session():
    defaults = {
        "token": None,
        "user": None,
        "dashboard": None,
        "chat_messages": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_session():
    keys = [
        "token",
        "user",
        "dashboard",
        "chat_messages",
    ]

    for key in keys:
        if key in st.session_state:
            del st.session_state[key]

    init_session()


init_session()


# =========================
# API helper
# =========================

def api_request(method: str, path: str, token: str | None = None, **kwargs):
    url = f"{API_URL}{path}"

    headers = kwargs.pop("headers", {})

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            timeout=120,
            **kwargs
        )
    except requests.exceptions.ConnectionError:
        return None, {
            "error": "Cannot connect to API server.",
            "url": url
        }
    except requests.exceptions.Timeout:
        return None, {
            "error": "API request timeout.",
            "url": url
        }
    except Exception as e:
        return None, {
            "error": str(e),
            "url": url
        }

    try:
        data = response.json()
    except Exception:
        data = {
            "error": "API returned non-JSON response",
            "status_code": response.status_code,
            "text": response.text
        }

    return response, data


def show_error(data):
    if isinstance(data, dict):
        detail = (
            data.get("detail")
            or data.get("error")
            or data.get("message")
            or data
        )
        st.error(detail)
    else:
        st.error(str(data))


def load_me():
    if not st.session_state.token:
        return None

    res, data = api_request(
        "GET",
        "/me",
        token=st.session_state.token
    )

    if not res or res.status_code != 200:
        clear_session()
        return None

    st.session_state.user = data
    return data


def load_dashboard():
    if not st.session_state.token:
        return None

    res, data = api_request(
        "GET",
        "/dashboard",
        token=st.session_state.token
    )

    if not res or res.status_code != 200:
        return None

    st.session_state.dashboard = data
    return data


def refresh_auth_state():
    user = load_me()

    if not user:
        st.warning("Session expired or invalid. Please login again.")
        st.rerun()

    dashboard = load_dashboard()

    return user, dashboard


# =========================
# Lemon checkout helper
# =========================

def build_lemon_checkout_url(base_url: str, email: str, tenant_id: int):
    separator = "&" if "?" in base_url else "?"

    return (
        f"{base_url}"
        f"{separator}checkout[email]={quote_plus(str(email))}"
        f"&checkout[custom][tenant_id]={quote_plus(str(tenant_id))}"
    )


# =========================
# Header
# =========================

st.markdown(
    """
    <div style="display:flex;align-items:center;gap:16px;margin-top:30px;margin-bottom:20px;">
        <div style="font-size:48px;">🩺</div>
        <div style="font-size:46px;font-weight:800;color:#2f3142;">
            Medical SaaS AI Platform
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# =========================
# Health check
# =========================

health_res, health_data = api_request("GET", "/health")

if not health_res or health_res.status_code != 200:
    st.error("API is not reachable.")
    st.json(health_data)
    st.stop()


# =========================
# Auth screen
# =========================

if not st.session_state.token:
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        email = st.text_input(
            "Email",
            value="",
            key="login_email"
        )

        password = st.text_input(
            "Password",
            type="password",
            value="",
            key="login_password"
        )

        if st.button("Login"):
            if not email or not password:
                st.error("Email and password are required.")
            else:
                with st.spinner("Logging in..."):
                    res, data = api_request(
                        "POST",
                        "/login",
                        json={
                            "email": email.strip().lower(),
                            "password": password
                        }
                    )

                if res and res.status_code == 200:
                    st.session_state.token = data["access_token"]
                    st.session_state.user = data
                    load_me()
                    load_dashboard()
                    st.success("Logged in successfully.")
                    st.rerun()
                else:
                    show_error(data)

    with register_tab:
        clinic_name = st.text_input(
            "Clinic name",
            value="",
            key="register_clinic"
        )

        reg_email = st.text_input(
            "Register email",
            value="",
            key="register_email"
        )

        reg_password = st.text_input(
            "Register password",
            type="password",
            value="",
            key="register_password"
        )

        if st.button("Create Account"):
            if not clinic_name or not reg_email or not reg_password:
                st.error("Clinic name, email, and password are required.")
            else:
                with st.spinner("Creating account..."):
                    res, data = api_request(
                        "POST",
                        "/register",
                        json={
                            "email": reg_email.strip().lower(),
                            "password": reg_password,
                            "clinic_name": clinic_name
                        }
                    )

                if res and res.status_code == 200:
                    st.session_state.token = data["access_token"]
                    st.session_state.user = data
                    load_me()
                    load_dashboard()
                    st.success("Account created successfully.")
                    st.rerun()
                else:
                    show_error(data)

    st.stop()


# =========================
# Logged in state
# =========================

user = load_me()

if not user:
    st.sidebar.success("Logged in")
    st.sidebar.error("Invalid user")
    if st.sidebar.button("Clear Session"):
        clear_session()
        st.rerun()
    st.stop()

dashboard = load_dashboard()


# =========================
# Sidebar
# =========================

with st.sidebar:
    st.success("Logged in")

    st.write("Clinic:", user.get("clinic"))
    st.write("Plan:", user.get("plan"))
    st.write("Role:", user.get("role"))

    st.divider()

    if user.get("plan") == "free":
        st.subheader("Upgrade")

        if PAYMENT_PROVIDER == "lemon" and LEMON_CHECKOUT_URL:
            checkout_url = build_lemon_checkout_url(
                LEMON_CHECKOUT_URL,
                user.get("email"),
                user.get("tenant_id")
            )

            st.info("Upgrade to Pro using Lemon Squeezy.")
            st.link_button("🚀 Upgrade to Pro", checkout_url)

            with st.expander("Checkout Debug"):
                st.code(checkout_url)

        else:
            st.warning("Payment is not configured.")
    else:
        st.success("Pro plan active")

    st.divider()

    if st.button("Refresh User"):
        load_me()
        load_dashboard()
        st.rerun()

    if st.button("Logout"):
        clear_session()
        st.rerun()


# =========================
# Main tabs
# =========================

tab_dashboard, tab_add, tab_pdf, tab_csv, tab_search, tab_chat = st.tabs(
    [
        "Dashboard",
        "Add Record",
        "Upload PDF",
        "Upload CSV",
        "Search",
        "Chat"
    ]
)


# =========================
# Dashboard
# =========================

with tab_dashboard:
    st.subheader("Dashboard")

    if st.button("Refresh Dashboard"):
        load_me()
        dashboard = load_dashboard()
        st.rerun()

    if not dashboard:
        st.error("Could not load dashboard.")
    else:
        usage = dashboard.get("usage", {})
        limits = dashboard.get("limits", {})

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Questions",
            f"{usage.get('questions', 0)} / {limits.get('questions_per_month', 0)}"
        )

        col2.metric(
            "Files",
            f"{usage.get('files', 0)} / {limits.get('files_per_month', 0)}"
        )

        col3.metric(
            "Records",
            f"{usage.get('manual_records', 0)} / {limits.get('manual_records_per_month', 0)}"
        )

        st.json(dashboard)


# =========================
# Add Record
# =========================

with tab_add:
    st.subheader("Add Medical Record")

    record_id = st.text_input("Record ID")
    note = st.text_area("Clinical Note", height=160)
    department = st.text_input("Department optional")

    if st.button("Add Record"):
        if not record_id or not note:
            st.error("Record ID and Clinical Note are required.")
        else:
            with st.spinner("Adding record..."):
                res, data = api_request(
                    "POST",
                    "/add-record",
                    token=st.session_state.token,
                    json={
                        "id": record_id,
                        "note": note,
                        "department": department
                    }
                )

            if res and res.status_code == 200:
                st.success("Record added.")
                load_dashboard()
            else:
                show_error(data)

            st.json(data)


# =========================
# Upload PDF
# =========================

with tab_pdf:
    st.subheader("Upload PDF")

    pdf_file = st.file_uploader(
        "PDF file",
        type=["pdf"],
        key="pdf_uploader"
    )

    if st.button("Upload PDF"):
        if not pdf_file:
            st.error("Please select a PDF file.")
        else:
            files = {
                "file": (
                    pdf_file.name,
                    pdf_file.getvalue(),
                    "application/pdf"
                )
            }

            with st.spinner("Uploading PDF..."):
                res, data = api_request(
                    "POST",
                    "/upload-pdf",
                    token=st.session_state.token,
                    files=files
                )

            if res and res.status_code == 200:
                st.success("PDF uploaded.")
                load_dashboard()
            else:
                show_error(data)

            st.json(data)


# =========================
# Upload CSV
# =========================

with tab_csv:
    st.subheader("Upload CSV")

    csv_file = st.file_uploader(
        "CSV file",
        type=["csv"],
        key="csv_uploader"
    )

    if st.button("Upload CSV"):
        if not csv_file:
            st.error("Please select a CSV file.")
        else:
            files = {
                "file": (
                    csv_file.name,
                    csv_file.getvalue(),
                    "text/csv"
                )
            }

            with st.spinner("Uploading CSV..."):
                res, data = api_request(
                    "POST",
                    "/upload-csv",
                    token=st.session_state.token,
                    files=files
                )

            if res and res.status_code == 200:
                st.success("CSV uploaded.")
                load_dashboard()
            else:
                show_error(data)

            st.json(data)


# =========================
# Search
# =========================

with tab_search:
    st.subheader("Search Medical Records")

    query = st.text_input("Search query")
    n_results = st.slider(
        "Results",
        min_value=1,
        max_value=20,
        value=3,
        key="search_results_count"
    )

    if st.button("Search"):
        if not query:
            st.error("Search query is required.")
        else:
            with st.spinner("Searching..."):
                res, data = api_request(
                    "POST",
                    "/search",
                    token=st.session_state.token,
                    json={
                        "query": query,
                        "n_results": n_results
                    }
                )

            if res and res.status_code == 200:
                results = data.get("results", [])
                metadata = data.get("metadata", [])
                distances = data.get("distances", [])

                if not results:
                    st.info("No results found.")

                for i, doc in enumerate(results):
                    st.markdown(f"### Result {i + 1}")
                    st.write(doc)

                    with st.expander("Details"):
                        if i < len(metadata):
                            st.json(metadata[i])
                        if i < len(distances):
                            st.write("Distance:", distances[i])
            else:
                show_error(data)


# =========================
# Chat
# =========================

with tab_chat:
    st.subheader("Chat")

    n_results = st.slider(
        "Context results",
        min_value=1,
        max_value=10,
        value=3,
        key="chat_results_count"
    )

    if st.button("Clear Chat"):
        st.session_state.chat_messages = []
        st.rerun()

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    prompt = st.chat_input("Ask about your medical records...")

    if prompt:
        st.session_state.chat_messages.append(
            {
                "role": "user",
                "content": prompt
            }
        )

        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                res, data = api_request(
                    "POST",
                    "/ask",
                    token=st.session_state.token,
                    json={
                        "question": prompt,
                        "n_results": n_results,
                        "chat_history": st.session_state.chat_messages
                    }
                )

            if res and res.status_code == 200:
                answer = data.get("answer", "")
                st.write(answer)

                with st.expander("Details"):
                    st.write("Intent:", data.get("intent"))
                    st.write("Source:", data.get("source"))
                    st.write("Confidence:", data.get("confidence"))
                    st.write("Triage:", data.get("triage"))
                    st.write("Evidence Count:", data.get("evidence_count"))
                    st.write("Best Evidence:")
                    st.write(data.get("best_evidence"))
                    st.write("Metadata:")
                    st.json(data.get("metadata", []))

                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": answer
                    }
                )

                load_dashboard()

            else:
                answer = (
                    data.get("detail")
                    if isinstance(data, dict)
                    else str(data)
                )
                st.warning(answer)

                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": answer
                    }
                )