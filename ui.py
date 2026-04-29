import streamlit as st
import requests
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

API_URL = os.getenv("API_URL", "https://medical-saas-api.onrender.com").rstrip("/")
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "lemon")
LEMON_CHECKOUT_URL = os.getenv("LEMON_CHECKOUT_URL", "")

st.set_page_config(
    page_title="Medical SaaS AI",
    page_icon="🩺",
    layout="wide"
)


def api_request(method, path, token=None, **kwargs):
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


def headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def build_lemon_url(base_url: str, email: str, tenant_id: int):
    separator = "&" if "?" in base_url else "?"
    return (
        f"{base_url}"
        f"{separator}checkout[email]={quote_plus(str(email))}"
        f"&checkout[custom][tenant_id]={quote_plus(str(tenant_id))}"
    )


def show_error(data):
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("error") or data
        st.error(detail)
    else:
        st.error(data)


if "token" not in st.session_state:
    st.session_state.token = None

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "me" not in st.session_state:
    st.session_state.me = None


st.title("🩺 Medical SaaS AI Platform")


health_res, health_data = api_request("GET", "/health")

if not health_res or health_res.status_code != 200:
    st.error("API is not reachable.")
    st.json(health_data)
    st.stop()


if not st.session_state.token:
    auth_tab, register_tab = st.tabs(["Login", "Register"])

    with auth_tab:
        email = st.text_input("Email", value="admin@test.com")
        password = st.text_input("Password", type="password", value="admin123")

        if st.button("Login", use_container_width=False):
            with st.spinner("Logging in..."):
                res, data = api_request(
                    "POST",
                    "/login",
                    json={
                        "email": email,
                        "password": password
                    }
                )

            if res and res.status_code == 200:
                st.session_state.token = data["access_token"]
                st.session_state.me = data
                st.success("Logged in")
                st.rerun()
            else:
                show_error(data)

    with register_tab:
        clinic_name = st.text_input("Clinic name", value="Test Clinic")
        reg_email = st.text_input("Register email")
        reg_password = st.text_input("Register password", type="password")

        if st.button("Create Account", use_container_width=False):
            if not clinic_name or not reg_email or not reg_password:
                st.error("All fields are required.")
            else:
                with st.spinner("Creating account..."):
                    res, data = api_request(
                        "POST",
                        "/register",
                        json={
                            "email": reg_email,
                            "password": reg_password,
                            "clinic_name": clinic_name
                        }
                    )

                if res and res.status_code == 200:
                    st.session_state.token = data["access_token"]
                    st.session_state.me = data
                    st.success("Account created")
                    st.rerun()
                else:
                    show_error(data)

    st.stop()


with st.sidebar:
    st.success("Logged in")

    me_res, me = api_request(
        "GET",
        "/me",
        token=st.session_state.token
    )

    if not me_res or me_res.status_code != 200:
        show_error(me)
        if st.button("Clear Session"):
            st.session_state.token = None
            st.session_state.chat_messages = []
            st.session_state.me = None
            st.rerun()
        st.stop()

    st.write("Clinic:", me.get("clinic"))
    st.write("Plan:", me.get("plan"))
    st.write("Role:", me.get("role"))

    st.divider()

    if me.get("plan") == "free":
        st.subheader("Upgrade")

        if PAYMENT_PROVIDER == "lemon" and LEMON_CHECKOUT_URL:
            checkout_url = build_lemon_url(
                LEMON_CHECKOUT_URL,
                me.get("email"),
                me.get("tenant_id")
            )

            st.info("Upgrade to Pro using Lemon Squeezy.")
            st.link_button("🚀 Upgrade to Pro", checkout_url)

            with st.expander("Checkout Debug"):
                st.code(checkout_url)

        elif PAYMENT_PROVIDER == "stripe":
            if st.button("Upgrade to Pro"):
                with st.spinner("Creating checkout session..."):
                    res, data = api_request(
                        "POST",
                        "/billing/create-checkout-session",
                        token=st.session_state.token
                    )

                if res and res.status_code == 200 and "checkout_url" in data:
                    st.link_button("Open Stripe Checkout", data["checkout_url"])
                else:
                    show_error(data)

        else:
            st.warning("Payment is not configured.")
    else:
        st.success("Pro plan active")

    st.divider()

    if st.button("Logout"):
        st.session_state.token = None
        st.session_state.chat_messages = []
        st.session_state.me = None
        st.rerun()


tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Dashboard",
    "Add Record",
    "Upload PDF",
    "Upload CSV",
    "Search",
    "Chat"
])


with tab1:
    st.subheader("Dashboard")

    if st.button("Refresh Dashboard"):
        st.rerun()

    with st.spinner("Loading dashboard..."):
        res, data = api_request(
            "GET",
            "/dashboard",
            token=st.session_state.token
        )

    if res and res.status_code == 200:
        usage = data.get("usage", {})
        limits = data.get("limits", {})

        c1, c2, c3 = st.columns(3)
        c1.metric("Questions", f"{usage.get('questions', 0)} / {limits.get('questions_per_month', 0)}")
        c2.metric("Files", f"{usage.get('files', 0)} / {limits.get('files_per_month', 0)}")
        c3.metric("Records", f"{usage.get('manual_records', 0)} / {limits.get('manual_records_per_month', 0)}")

        st.json(data)
    else:
        show_error(data)


with tab2:
    st.subheader("Add Medical Record")

    record_id = st.text_input("Record ID")
    note = st.text_area("Clinical Note", height=150)
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
                st.success("Record added")
            else:
                show_error(data)

            st.json(data)


with tab3:
    st.subheader("Upload PDF")

    pdf = st.file_uploader("PDF file", type=["pdf"])

    if st.button("Upload PDF"):
        if not pdf:
            st.error("Select a PDF")
        else:
            files = {
                "file": (
                    pdf.name,
                    pdf.getvalue(),
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
                st.success("PDF uploaded")
            else:
                show_error(data)

            st.json(data)


with tab4:
    st.subheader("Upload CSV")

    csv = st.file_uploader("CSV file", type=["csv"])

    if st.button("Upload CSV"):
        if not csv:
            st.error("Select a CSV")
        else:
            files = {
                "file": (
                    csv.name,
                    csv.getvalue(),
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
                st.success("CSV uploaded")
            else:
                show_error(data)

            st.json(data)


with tab5:
    st.subheader("Search")

    query = st.text_input("Search query")
    n_results = st.slider("Results", 1, 20, 3)

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
                for i, doc in enumerate(data.get("results", [])):
                    st.markdown(f"### Result {i + 1}")
                    st.write(doc)

                    metadata = data.get("metadata", [])
                    distances = data.get("distances", [])

                    if i < len(metadata):
                        st.json(metadata[i])

                    if i < len(distances):
                        st.write("Distance:", distances[i])
            else:
                show_error(data)


with tab6:
    st.subheader("Chat")

    n_results = st.slider("Context results", 1, 10, 3)

    if st.button("Clear Chat"):
        st.session_state.chat_messages = []
        st.rerun()

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt = st.chat_input("Ask about your medical records...")

    if prompt:
        st.session_state.chat_messages.append({
            "role": "user",
            "content": prompt
        })

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
            else:
                answer = data.get("detail") if isinstance(data, dict) else str(data)
                st.warning(answer)

        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": answer
        })