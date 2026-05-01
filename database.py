import sqlite3
import os

DB_PATH = "medical_db/users.db"

def init_db():
    # التأكد من وجود المجلد
    os.makedirs("medical_db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # جدول المستخدمين المطور
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  email TEXT UNIQUE, 
                  password TEXT, 
                  plan TEXT DEFAULT 'free',
                  payment_status TEXT DEFAULT 'none',
                  receipt_file TEXT)''')
    conn.commit()
    conn.close()

def get_user(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, plan, payment_status, receipt_file FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()
    return user

def register_user(email, password):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def update_user_to_pending(email, filename):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET plan='pending', payment_status='review', receipt_file=? WHERE email=?", (filename, email))
    conn.commit()
    conn.close()

def get_pending_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, receipt_file FROM users WHERE plan='pending'")
    users = c.fetchall()
    conn.close()
    return users

def approve_user(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET plan='pro', payment_status='completed' WHERE email=?", (email,))
    conn.commit()
    conn.close()