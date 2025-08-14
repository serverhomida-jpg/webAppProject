from pydantic import BaseModel

class Customer(BaseModel):
    CustomerNumber: str | None = None
    Name: str
    Phone: str | None = None
    Email: str | None = None
    Address: str | None = None
    TaxNumber: str | None = None
    NationalAddress: str | None = None

class ServerIP(BaseModel):
    IP: str
    USER: str | None = None
    PASS: str | None = None
    SERVER_EMAIL: str | None = None
    EMAIL_PASS: str | None = None

class CustServer(BaseModel):
    CustomerName: str
    LinkOrNot: bool
    GlobalServerIP: str
    ServerName: str | None = None
    DatabaseName: str | None = None
    ConnectionType: str | None = None
    ConnectedDevices: int = 0
    Notes: str | None = None

class User(BaseModel):
    Username: str
    Password: str  # Hashed password
    Role: str  # e.g., 'admin', 'manager'