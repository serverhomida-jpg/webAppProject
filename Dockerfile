FROM python:3.13

# تثبيت الاعتماديات الأساسية لـ unixODBC و ODBC Driver
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    unixodbc \
    unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc -o microsoft.asc \
    && mkdir -p /etc/apt/keyrings \
    && gpg --dearmor < microsoft.asc > /etc/apt/keyrings/microsoft.gpg \
    && rm microsoft.asc \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17

# إعداد بيئة Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملفات المشروع
COPY . .

# أمر تشغيل التطبيق
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]