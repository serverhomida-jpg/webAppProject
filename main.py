
from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from io import StringIO
import csv
import pyodbc
import hashlib
from database import get_db_connection_fastapi, create_database_and_table_fastapi
from models import Customer, ServerIP, CustServer, User
from utils import is_valid_email, is_valid_numeric, generate_customer_number_fastapi

async def lifespan(app: FastAPI):
    create_database_and_table_fastapi()
    create_users_table()
    yield
    print("Application is shutting down...")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
security = HTTPBasic()

# Create Users Table and Add Default Users
def create_users_table():
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
        CREATE TABLE Users (
            ID INT PRIMARY KEY IDENTITY(1,1),
            Username VARCHAR(50) UNIQUE NOT NULL,
            Password VARCHAR(64) NOT NULL,  -- SHA256 hash
            Role VARCHAR(20) NOT NULL
        )
    """)
    # Add default users
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

# Validate User for Authentication
def validate_user(username: str, password: str, required_role: str = None):
    hashed_pass = hashlib.sha256(password.encode()).hexdigest()
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    cursor.execute("SELECT Role FROM Users WHERE Username = ? AND Password = ?", (username, hashed_pass))
    result = cursor.fetchone()
    conn.close()
    if result and (required_role is None or result[0] == required_role):
        return True
    return False

# Login Page
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    cursor.execute("SELECT Username FROM Users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()

    with open("login.html", "r", encoding="utf-8") as f:
        html = f.read()
    # Insert usernames into the <select> element
    options = "".join(f'<option value="{user}">{user}</option>\n' for user in users)
    html = html.replace("<!-- Filled dynamically by server -->", options)
    return HTMLResponse(content=html)
# Login Post
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if validate_user(username, password):
        return RedirectResponse(url="/", status_code=303)
    else:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")

# Users Management Page (Admin Only)
@app.get("/users", response_class=HTMLResponse)
async def manage_users(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password, 'admin'):
        raise HTTPException(status_code=401, detail="غير مصرح")
    with open("users.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# Users Data
@app.get("/users/data")
async def get_users(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password, 'admin'):
        raise HTTPException(status_code=401, detail="غير مصرح")
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    cursor.execute("SELECT ID, Username, Role FROM Users")
    users = [{"ID": row[0], "Username": row[1], "Role": row[2]} for row in cursor.fetchall()]
    conn.close()
    return users

# Add User
@app.post("/users")
async def add_user(user: User, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password, 'admin'):
        raise HTTPException(status_code=401, detail="غير مصرح")
    hashed_pass = hashlib.sha256(user.Password.encode()).hexdigest()
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Users (Username, Password, Role) VALUES (?, ?, ?)", (user.Username, hashed_pass, user.Role))
        conn.commit()
        return {"message": "تم إضافة المستخدم!"}
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقًا!")
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Update User
@app.put("/users/{id}")
async def update_user(id: int, user: User, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password, 'admin'):
        raise HTTPException(status_code=401, detail="غير مصرح")
    hashed_pass = hashlib.sha256(user.Password.encode()).hexdigest() if user.Password else None
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        if hashed_pass:
            cursor.execute("UPDATE Users SET Username = ?, Password = ?, Role = ? WHERE ID = ?", (user.Username, hashed_pass, user.Role, id))
        else:
            cursor.execute("UPDATE Users SET Username = ?, Role = ? WHERE ID = ?", (user.Username, user.Role, id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود!")
        conn.commit()
        return {"message": "تم تعديل المستخدم!"}
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقًا!")
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Delete User
@app.delete("/users/{id}")
async def delete_user(id: int, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password, 'admin'):
        raise HTTPException(status_code=401, detail="غير مصرح")
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Users WHERE ID = ?", (id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود!")
        conn.commit()
        return {"message": "تم حذف المستخدم!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Protect Existing Routes
@app.get("/", response_class=HTMLResponse)
async def read_root(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/manage", response_class=HTMLResponse)
async def manage_customers(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    with open("manage.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/serverip", response_class=HTMLResponse)
async def manage_serverip(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    with open("serverip.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/custserver", response_class=HTMLResponse)
async def manage_custserver(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    with open("custserver.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/customers")
async def get_customers(search: str = "", credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    query = """
        SELECT ID, CustomerNumber, Name, Phone, Email, Address, TaxNumber, NationalAddress 
        FROM Customers 
        WHERE Name LIKE ? OR CustomerNumber LIKE ?
    """
    params = (f'%{search}%', f'%{search}%') if search else ('%', '%')
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [{"ID": row[0], "CustomerNumber": row[1], "Name": row[2], "Phone": row[3], "Email": row[4], "Address": row[5], "TaxNumber": row[6], "NationalAddress": row[7]} for row in rows]
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch customers: {str(e)}")
    finally:
        conn.close()

@app.post("/customers")
async def add_customer(customer: Customer, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    if not customer.Name:
        raise HTTPException(status_code=400, detail="الاسم مطلوب!")
    if customer.Phone and not is_valid_numeric(customer.Phone):
        raise HTTPException(status_code=400, detail="رقم الهاتف يجب أن يكون أرقام فقط!")
    if customer.Email and not is_valid_email(customer.Email):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني غير صحيح!")
    if customer.TaxNumber and not is_valid_numeric(customer.TaxNumber):
        raise HTTPException(status_code=400, detail="الرقم الضريبي يجب أن يكون أرقام فقط!")
    
    customer_number = customer.CustomerNumber or generate_customer_number_fastapi()
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Customers (CustomerNumber, Name, Phone, Email, Address, TaxNumber, NationalAddress) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (customer_number, customer.Name, customer.Phone, customer.Email, customer.Address, customer.TaxNumber, customer.NationalAddress))
        conn.commit()
        return {"message": "تم إضافة العميل!"}
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail="رقم العميل موجود مسبقًا!")
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.put("/customers/{id}")
async def update_customer(id: int, customer: Customer, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    if not customer.Name:
        raise HTTPException(status_code=400, detail="الاسم مطلوب!")
    if customer.Phone and not is_valid_numeric(customer.Phone):
        raise HTTPException(status_code=400, detail="رقم الهاتف يجب أن يكون أرقام فقط!")
    if customer.Email and not is_valid_email(customer.Email):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني غير صحيح!")
    if customer.TaxNumber and not is_valid_numeric(customer.TaxNumber):
        raise HTTPException(status_code=400, detail="الرقم الضريبي يجب أن يكون أرقام فقط!")
    
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Customers SET CustomerNumber = ?, Name = ?, Phone = ?, Email = ?, Address = ?, TaxNumber = ?, NationalAddress = ? 
            WHERE ID = ?
        """, (customer.CustomerNumber or generate_customer_number_fastapi(), customer.Name, customer.Phone, customer.Email, customer.Address, customer.TaxNumber, customer.NationalAddress, id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="العميل غير موجود!")
        conn.commit()
        return {"message": "تم تعديل العميل!"}
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail="رقم العميل موجود مسبقًا!")
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/customers/{id}")
async def delete_customer(id: int, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Customers WHERE ID = ?", (id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="العميل غير موجود!")
        conn.commit()
        return {"message": "تم حذف العميل!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/export")
async def export_to_csv(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ID, CustomerNumber, Name, Phone, Email, Address, TaxNumber, NationalAddress FROM Customers")
        rows = cursor.fetchall()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "CustomerNumber", "Name", "Phone", "Email", "Address", "TaxNumber", "NationalAddress"])
        writer.writerows(rows)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=customers.csv"}
        )
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Failed to export data: {str(e)}")
    finally:
        conn.close()

# Routes for SERVERIP
@app.get("/serverip/data")
async def get_serverip(search: str = "", credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    query = """
        SELECT IP, [USER], [PASS], SERVER_EMAIL, EMAIL_PASS 
        FROM SERVERIP 
        WHERE IP LIKE ? OR [USER] LIKE ?
    """
    params = (f'%{search}%', f'%{search}%') if search else ('%', '%')
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [{"IP": row[0], "USER": row[1], "PASS": row[2], "SERVER_EMAIL": row[3], "EMAIL_PASS": row[4]} for row in rows]
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch SERVERIP: {str(e)}")
    finally:
        conn.close()

@app.post("/serverip")
async def add_serverip(serverip: ServerIP, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    if not serverip.IP:
        raise HTTPException(status_code=400, detail="IP مطلوب!")
    
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO SERVERIP (IP, [USER], [PASS], SERVER_EMAIL, EMAIL_PASS) 
            VALUES (?, ?, ?, ?, ?)
        """, (serverip.IP, serverip.USER, serverip.PASS, serverip.SERVER_EMAIL, serverip.EMAIL_PASS))
        conn.commit()
        return {"message": "تم إضافة SERVERIP!"}
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail="IP موجود مسبقًا!")
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.put("/serverip/{ip}")
async def update_serverip(ip: str, serverip: ServerIP, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE SERVERIP SET [USER] = ?, [PASS] = ?, SERVER_EMAIL = ?, EMAIL_PASS = ? 
            WHERE IP = ?
        """, (serverip.USER, serverip.PASS, serverip.SERVER_EMAIL, serverip.EMAIL_PASS, ip))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="SERVERIP غير موجود!")
        conn.commit()
        return {"message": "تم تعديل SERVERIP!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/serverip/{ip}")
async def delete_serverip(ip: str, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM SERVERIP WHERE IP = ?", (ip,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="SERVERIP غير موجود!")
        conn.commit()
        return {"message": "تم حذف SERVERIP!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Routes for CUSTSERVER
@app.get("/custserver/data")
async def get_custserver(search: str = "", credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    query = """
        SELECT ID, CustomerName, LinkOrNot, [Number], GlobalServerIP, ServerName, DatabaseName, ConnectionType, ConnectedDevices, Notes 
        FROM CUSTSERVER 
        WHERE CustomerName LIKE ? OR ServerName LIKE ?
    """
    params = (f'%{search}%', f'%{search}%') if search else ('%', '%')
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [{"ID": row[0], "CustomerName": row[1], "LinkOrNot": bool(row[2]), "Number": row[3], "GlobalServerIP": row[4], "ServerName": row[5], "DatabaseName": row[6], "ConnectionType": row[7], "ConnectedDevices": row[8], "Notes": row[9]} for row in rows]
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch CUSTSERVER: {str(e)}")
    finally:
        conn.close()

@app.get("/global_ips")
async def get_global_ips(credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT IP FROM SERVERIP")
        rows = cursor.fetchall()
        return [{"IP": row[0]} for row in rows]
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch global IPs: {str(e)}")
    finally:
        conn.close()

@app.post("/custserver")
async def add_custserver(custserver: CustServer, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    if not custserver.CustomerName or not custserver.GlobalServerIP:
        raise HTTPException(status_code=400, detail="اسم العميل وايبي السيرفر العالمي مطلوبان!")
    
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM CUSTSERVER WHERE GlobalServerIP = ?", (custserver.GlobalServerIP,))
        count = cursor.fetchone()[0]
        number = count + 1
        
        cursor.execute("""
            INSERT INTO CUSTSERVER (CustomerName, LinkOrNot, [Number], GlobalServerIP, ServerName, DatabaseName, ConnectionType, ConnectedDevices, Notes) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (custserver.CustomerName, custserver.LinkOrNot, number, custserver.GlobalServerIP, custserver.ServerName, custserver.DatabaseName, custserver.ConnectionType, custserver.ConnectedDevices, custserver.Notes))
        conn.commit()
        return {"message": "تم إضافة CUSTSERVER!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.put("/custserver/{id}")
async def update_custserver(id: int, custserver: CustServer, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("SELECT GlobalServerIP FROM CUSTSERVER WHERE ID = ?", (id,))
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="CUSTSERVER غير موجود!")
        old_ip = result[0]
        if custserver.GlobalServerIP != old_ip:
            cursor.execute("SELECT COUNT(*) FROM CUSTSERVER WHERE GlobalServerIP = ?", (custserver.GlobalServerIP,))
            count = cursor.fetchone()[0]
            number = count + 1
        else:
            cursor.execute("SELECT [Number] FROM CUSTSERVER WHERE ID = ?", (id,))
            number = cursor.fetchone()[0]
        
        cursor.execute("""
            UPDATE CUSTSERVER SET CustomerName = ?, LinkOrNot = ?, [Number] = ?, GlobalServerIP = ?, ServerName = ?, DatabaseName = ?, ConnectionType = ?, ConnectedDevices = ?, Notes = ? 
            WHERE ID = ?
        """, (custserver.CustomerName, custserver.LinkOrNot, number, custserver.GlobalServerIP, custserver.ServerName, custserver.DatabaseName, custserver.ConnectionType, custserver.ConnectedDevices, custserver.Notes, id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="CUSTSERVER غير موجود!")
        conn.commit()
        return {"message": "تم تعديل CUSTSERVER!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/custserver/{id}")
async def delete_custserver(id: int, credentials: HTTPBasicCredentials = Depends(security)):
    if not validate_user(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="غير مصرح")
    try:
        conn = get_db_connection_fastapi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM CUSTSERVER WHERE ID = ?", (id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="CUSTSERVER غير موجود!")
        conn.commit()
        return {"message": "تم حذف CUSTSERVER!"}
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    import os
    if os.environ.get("NGROK_AUTHTOKEN"):
        from pyngrok import ngrok
        public_url = ngrok.connect(8000).public_url
        print(f" * ngrok tunnel \"{public_url}\" -> \"http://127.0.0.1:8000\"")
    uvicorn.run(app, host="127.0.0.1", port=8000)
