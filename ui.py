import streamlit as st
import requests

API_URL = "https://medical-saas-ai.onrender.com" # استبدله برابط Render الخاص بك
ADMIN_PASS_UI = "admin123" # كلمة سر لوحة التحكم في الواجهة

st.set_page_config(page_title="Medical AI Pro", page_icon="🏥")

if "email" not in st.session_state:
    st.title("🏥 مرحبًا بك في Medical AI")
    auth_mode = st.radio("اختر", ["تسجيل الدخول", "حساب جديد"])
    email = st.text_input("البريد الإلكتروني")
    pwd = st.text_input("كلمة المرور", type="password")
    
    if st.button("استمرار"):
        st.session_state.email = email
        st.rerun()
else:
    # جلب بيانات المستخدم الحالية
    user_info = requests.get(f"{API_URL}/me", params={"email": st.session_state.email}).json()
    
    st.sidebar.title(f"👤 {st.session_state.email}")
    st.sidebar.info(f"الخطة الحالية: **{user_info['plan'].upper()}**")
    
    menu = ["الذكاء الاصطناعي", "الترقية للـ PRO 💎", "إدارة النظام ⚙️"]
    choice = st.sidebar.selectbox("القائمة", menu)

    if choice == "الذكاء الاصطناعي":
        st.subheader("استشارة الذكاء الاصطناعي الطبي")
        q = st.text_area("أدخل ملاحظاتك السريرية أو سؤالك:")
        if st.button("تحليل"):
            with st.spinner("جاري التفكير..."):
                res = requests.post(f"{API_URL}/ask", data={"question": q, "email": st.session_state.email})
                st.markdown(f"### النتيجة:\n{res.json().get('answer')}")

    elif choice == "الترقية للـ PRO 💎":
        if user_info['plan'] == 'pro':
            st.success("أنت مشترك بالفعل في النسخة الاحترافية!")
        elif user_info['plan'] == 'pending':
            st.warning("طلبك قيد المراجعة حالياً. سيتم التفعيل فور التأكد من الإيصال.")
        else:
            st.subheader("فتح الميزات الاحترافية")
            st.markdown("""
            1. **حوّل مبلغ الاشتراك (20$ شهرياً) عبر:**
                * **WhatsApp:** +218XXXXXXXX (سداد / تداول / رصيد)
                * **USDT (TRC20):** `TXXXX_YOUR_WALLET_ADDRESS`
            2. **ارفع صورة الإيصال هنا:**
            """)
            up_file = st.file_uploader("ارفع الإيصال", type=['jpg', 'png'])
            if st.button("إرسال الإيصال"):
                if up_file:
                    requests.post(f"{API_URL}/upload-receipt", data={"email": st.session_state.email}, files={"file": up_file})
                    st.success("تم الإرسال! انتظر التفعيل.")

    elif choice == "إدارة النظام ⚙️":
        pwd_admin = st.text_input("كلمة مرور الإدارة", type="password")
        if pwd_admin == ADMIN_PASS_UI:
            st.subheader("طلبات الترقية المعلقة")
            admin_key = "MY_SECRET_ADMIN_123" # الـ ADMIN_KEY المسجل في Render
            pending = requests.get(f"{API_URL}/admin/pending", headers={"x-admin-key": admin_key}).json()
            
            if not pending: st.write("لا توجد طلبات حالياً.")
            for user in pending:
                col1, col2 = st.columns([3, 1])
                col1.write(f"Email: {user[0]} | File: {user[1]}")
                if col2.button("تفعيل", key=user[0]):
                    requests.post(f"{API_URL}/admin/approve", params={"email": user[0]}, headers={"x-admin-key": admin_key})
                    st.rerun()