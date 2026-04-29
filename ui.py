import streamlit as st
import requests
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "manual")
LEMON_CHECKOUT_URL = os.getenv("LEMON_CHECKOUT_URL", "")

st.set_page_config(
    page_title="Medical SaaS AI",
    page_icon="🩺",
    layout="wide"
)


def safe_json_response(response):
    try:
        return response.json()
    except Exception:
        st.error("API returned non-JSON response")
        st.write("Status code:", response.status_code)
        st.code(response.text if response.text else "Empty response")
        st.stop()


def headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def build_lemon_url(base_url: str, email: str, tenant_id: int):
    separator = "&" if "?" in base_url else "?"
    return (
        f"{base_url}"
        f"{separator}checkout[email]={quote_plus(str(email))}"
        f"&checkout[custom][tenant_id]={quote_plus(str(tenant_id))}"
    )


if "token" not in st.session_state:
    st.session_state.token = None

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "me" not in st.session_state:
    st.session_state.me = None


st.title("🩺 Medical SaaS AI Platform")


if not st.session_state.token:
    auth_tab, register_tab = st.tabs(["Login", "Register"])

    with auth_tab:
        email = st.text_input("Email", value="admin@test.com")
        password = st.text_input("Password", type="password", value="admin123")

        if st.button("Login"):
            res = requests.post(
                f"{API_URL}/login",
                json={
                    "email": email,
                    "password": password
                }
            )
            data = safe_json_response(res)

            if res.status_code == 200:
                st.session_state.token = data["access_token"]
                st.session_state.me = data
                st.success("Logged in")
                st.rerun()
            else:
                st.error(data)

    with register_tab:
        clinic_name = st.text_input("Clinic name")
        reg_email = st.text_input("Register email")
        reg_password = st.text_input("Register password", type="password")

        if st.button("Create Account"):
            res = requests.post(
                f"{API_URL}/register",
                json={
                    "email": reg_email,
                    "password": reg_password,
                    "clinic_name": clinic_name
                }
            )
            data = safe_json_response(res)

            if res.status_code == 200:
                st.session_state.token = data["access_token"]
                st.session_state.me = data
                st.success("Account created")
                st.rerun()
            else:
                st.error(data)

    st.stop()


with st.sidebar:
    st.success("Logged in")

    me_res = requests.get(f"{API_URL}/me", headers=headers())
    me = safe_json_response(me_res)

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
            st.caption("After payment, webhook can activate Pro automatically.")

            with st.expander("Checkout Debug"):
                st.code(checkout_url)

        elif PAYMENT_PROVIDER == "stripe":
            if st.button("Upgrade to Pro"):
                res = requests.post(
                    f"{API_URL}/billing/create-checkout-session",
                    headers=headers()
                )
                data = safe_json_response(res)

                if "checkout_url" in data:
                    st.link_button("Open Stripe Checkout", data["checkout_url"])
                else:
                    st.error(data)

        else:
            st.warning("Payment is not configured.")
            st.write("Contact admin to upgrade your account.")

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

    res = requests.get(f"{API_URL}/dashboard", headers=headers())
    data = safe_json_response(res)

    st.json(data)


with tab2:
    st.subheader("Add Medical Record")

    record_id = st.text_input("Record ID")
    note = st.text_area("Clinical Note", height=150)
    department = st.text_input("Department optional")

    if st.button("Add Record"):
        if not record_id or not note:
            st.error("Record ID and Clinical Note are required.")
        else:
            res = requests.post(
                f"{API_URL}/add-record",
                headers=headers(),
                json={
                    "id": record_id,
                    "note": note,
                    "department": department
                }
            )
            data = safe_json_response(res)

            if res.status_code == 200:
                st.success("Record added")
            else:
                st.error(data)

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
            res = requests.post(
                f"{API_URL}/upload-pdf",
                headers=headers(),
                files=files
            )
            data = safe_json_response(res)

            if res.status_code == 200:
                st.success("PDF uploaded")
            else:
                st.error(data)

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
            res = requests.post(
                f"{API_URL}/upload-csv",
                headers=headers(),
                files=files
            )
            data = safe_json_response(res)

            if res.status_code == 200:
                st.success("CSV uploaded")
            else:
                st.error(data)

            st.json(data)


with tab5:
    st.subheader("Search")

    query = st.text_input("Search query")
    n_results = st.slider("Results", 1, 20, 3)

    if st.button("Search"):
        if not query:
            st.error("Search query is required.")
        else:
            res = requests.post(
                f"{API_URL}/search",
                headers=headers(),
                json={
                    "query": query,
                    "n_results": n_results
                }
            )
            data = safe_json_response(res)

            if res.status_code != 200:
                st.error(data)
            else:
                for i, doc in enumerate(data.get("results", [])):
                    st.markdown(f"### Result {i + 1}")
                    st.write(doc)

                    metadata = data.get("metadata", [])
                    distances = data.get("distances", [])

                    if i < len(metadata):
                        st.json(metadata[i])

                    if i < len(distances):
                        st.write("Distance:", distances[i])


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

        res = requests.post(
            f"{API_URL}/ask",
            headers=headers(),
            json={
                "question": prompt,
                "n_results": n_results,
                "chat_history": st.session_state.chat_messages
            }
        )

        data = safe_json_response(res)

        if res.status_code == 200:
            answer = data.get("answer", "")
        else:
            answer = data.get("detail", str(data))

        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": answer
        })

        with st.chat_message("assistant"):
            st.write(answer)

            if res.status_code == 200:
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
                st.warning(answer)