
import pyodbc
import hashlib
from fastapi import HTTPException
from cryptography.fernet import Fernet

# ==== قراءة المفتاح من الملف ====
def load_key():
    with open("secret.key", "rb") as key_file:
        return key_file.read()

# ==== دوال التشفير/فك التشفير ====
def decrypt_data(enc_value: str) -> str:
    f = Fernet(load_key())
    return f.decrypt(enc_value.encode()).decode()

# ==== بيانات الاتصال (مشفرّة) ====
SERVER_FASTAPI = 'gAAAAABonaJx479kbmTenZ60EOrjORwG5hJgaO4_cN-swUvsDBvqvf8JpbcNt5hXvrHIcZnN57bVEz_-kIvk_DeC5kLJDkXAKCP0RSLPwpm1UedYEBFh9M0='
DATABASE = 'gAAAAABonaJxLZBL6H01ESHGQSI8XD4GZ3PGyjXY0ZluYstTvUvYrJTyoyuB8cEFLyVGfQCwANF9GMpE54wgSJWiRZjUcXqATQ=='
USERNAME = 'gAAAAABonaJxup28dxySUcFWGptC9lQBGXzA6nP2kWUr07Sb9KpmeKzovxizL2ZRtTnRGOv-VfIPUm_zrj6jAuA920JrOxPVHw=='
PASSWORD = 'gAAAAABonaJxhDZfv1WEqMYKV69GtnxsXJ6Evd7UxyD0L40fwmTMKCes2M9at-iCUOWjpjWIrRpYpPAfVX2HfKJ52qMLAFrgfDrvyZIoygP9JPPPdpMK0ZM='
# ==== الاتصال بقاعدة البيانات ====
def get_db_connection_fastapi(create_db=False):
    conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};' \
               f'SERVER={decrypt_data(SERVER_FASTAPI)};' \
               f'UID={decrypt_data(USERNAME)};' \
               f'PWD={decrypt_data(PASSWORD)};'
    if not create_db:
        conn_str += f'DATABASE={decrypt_data(DATABASE)};'
    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
        return conn
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# ==== إنشاء قاعدة البيانات والجداول ====
def create_database_and_table_fastapi():
    conn = get_db_connection_fastapi(create_db=True)
    cursor = conn.cursor()

    # إنشاء قاعدة البيانات إذا لم تكن موجودة
    cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{decrypt_data(DATABASE)}') CREATE DATABASE {decrypt_data(DATABASE)}")
    cursor.execute(f"USE {decrypt_data(DATABASE)}")

    # إنشاء جدول Customers
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Customers')
        CREATE TABLE Customers (
            ID INT PRIMARY KEY IDENTITY(1,1),
            CustomerNumber VARCHAR(20) UNIQUE NOT NULL,
            Name NVARCHAR(100) NOT NULL,
            Phone VARCHAR(20),
            Email VARCHAR(100),
            Address NVARCHAR(255),
            TaxNumber VARCHAR(20),
            NationalAddress NVARCHAR(255)
        )
    """)

    # إضافة عمود TaxNumber إذا غير موجود
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE Name = N'TaxNumber' AND Object_ID = Object_ID(N'Customers'))
        ALTER TABLE Customers ADD TaxNumber VARCHAR(20)
    """)

    # إضافة عمود NationalAddress إذا غير موجود
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE Name = N'NationalAddress' AND Object_ID = Object_ID(N'Customers'))
        ALTER TABLE Customers ADD NationalAddress NVARCHAR(255)
    """)

    # إنشاء جدول SERVERIP
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SERVERIP')
        CREATE TABLE SERVERIP (
            IP VARCHAR(50) PRIMARY KEY,
            [USER] VARCHAR(50),
            [PASS] VARCHAR(50),
            SERVER_EMAIL VARCHAR(100),
            EMAIL_PASS VARCHAR(50)
        )
    """)

    # إنشاء جدول CUSTSERVER
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'CUSTSERVER')
        CREATE TABLE CUSTSERVER (
            ID INT PRIMARY KEY IDENTITY(1,1),
            CustomerName NVARCHAR(100),
            LinkOrNot BIT,
            [Number] INT,
            GlobalServerIP VARCHAR(50) FOREIGN KEY REFERENCES SERVERIP(IP),
            ServerName NVARCHAR(100),
            DatabaseName NVARCHAR(100),
            ConnectionType NVARCHAR(50),
            ConnectedDevices INT,
            Notes NVARCHAR(255)
        )
    """)

    # إنشاء جدول Users
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
        CREATE TABLE Users (
            ID INT PRIMARY KEY IDENTITY(1,1),
            Username VARCHAR(50) UNIQUE NOT NULL,
            Password VARCHAR(64) NOT NULL,  -- SHA256 hash
            Role VARCHAR(20) NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# إنشاء مستخدمين افتراضيين
def create_default_users():
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    default_users = [
        ('Admin', hashlib.sha256('1691988'.encode()).hexdigest(), 'admin'),
        ('Manager', hashlib.sha256('10'.encode()).hexdigest(), 'manager')
    ]
    for user in default_users:
        try:
            cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES (?, ?, ?)", user)
        except pyodbc.IntegrityError:
            pass  # User already exists
    conn.commit()
    conn.close()
