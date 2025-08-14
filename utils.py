import re
from database import get_db_connection_fastapi

# Function to validate email format
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# Function to validate phone or tax number (numeric only)
def is_valid_numeric(value):
    return value.isdigit() or not value  # Allow empty or digits only

# Generate next CustomerNumber
def generate_customer_number_fastapi():
    conn = get_db_connection_fastapi()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(CAST(SUBSTRING(CustomerNumber, 5, LEN(CustomerNumber)-4) AS INT)) FROM Customers WHERE CustomerNumber LIKE 'CUST%'")
    max_num = cursor.fetchone()[0]
    next_num = (max_num or 0) + 1
    conn.close()
    return f'CUST{next_num:04d}'