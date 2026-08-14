FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# OpenShift arbitrary UID friendly
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache

# Matplotlib mora imati writable config/cache folder
ENV MPLCONFIGDIR=/tmp/matplotlib

# Folder u kome Vanna pravi fajlove
ENV VANNA_FILES_DIR=/tmp/vanna-files

WORKDIR /app


# ============================================================
# System dependencies + Microsoft ODBC Driver 18 for SQL Server
# ============================================================

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        unixodbc \
        unixodbc-dev \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# Python dependencies
# ============================================================

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


# ============================================================
# Application
# ============================================================

COPY app.py .


# ============================================================
# OpenShift filesystem permissions
# ============================================================

RUN mkdir -p \
        /tmp/vanna-files \
        /tmp/.cache \
        /tmp/matplotlib \
    && chgrp -R 0 /app \
    && chmod -R g=u /app


EXPOSE 8000


CMD ["python", "app.py"]
