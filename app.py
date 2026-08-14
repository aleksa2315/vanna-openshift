import os
import html
import hashlib

from pathlib import Path
from urllib.parse import quote

import uvicorn

from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from vanna import Agent, AgentConfig
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.core.registry import ToolRegistry
from vanna.core.user import User, UserResolver, RequestContext

from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.mssql import MSSQLRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory

from vanna.tools import (
    RunSqlTool,
    VisualizeDataTool,
    LocalFileSystem,
    WriteFileTool,
    ListFilesTool,
    RunPythonFileTool,
)


# ============================================================
# User resolver
# ============================================================
#
# Pilot konfiguracija.
#
# Svi zahtevi trenutno koriste istog korisnika.
# Kasnije ovo treba zameniti pravim OpenShift OAuth / SSO / JWT
# resolverom.
#
# ============================================================

STATIC_USER_ID = "openshift-pilot"


class OpenShiftUserResolver(UserResolver):

    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(
            id=STATIC_USER_ID,
            username="openshift-pilot",
            email="pilot@local",
            group_memberships=["users"]
        )


# ============================================================
# Environment variables
# ============================================================

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

MSSQL_HOST = os.environ["MSSQL_HOST"]
MSSQL_PORT = os.getenv("MSSQL_PORT", "1433")
MSSQL_DATABASE = os.environ["MSSQL_DATABASE"]
MSSQL_USER = os.environ["MSSQL_USER"]
MSSQL_PASSWORD = os.environ["MSSQL_PASSWORD"]

PORT = int(os.getenv("PORT", "8000"))

FILES_ROOT = Path(
    os.getenv(
        "VANNA_FILES_DIR",
        "/tmp/vanna-files"
    )
)


# ============================================================
# User workspace
# ============================================================
#
# Vanna LocalFileSystem koristi SHA256(user.id) prvih 16
# karaktera kao user folder.
#
# Zato ovde računamo isti folder kako bismo ga mogli
# ponuditi kroz /downloads.
#
# ============================================================

USER_HASH = hashlib.sha256(
    STATIC_USER_ID.encode("utf-8")
).hexdigest()[:16]

USER_FILE_DIR = FILES_ROOT / USER_HASH

FILES_ROOT.mkdir(
    parents=True,
    exist_ok=True
)

USER_FILE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# ODBC helper
# ============================================================

def odbc_escape(value: str) -> str:
    """
    Escape vrednosti za ODBC connection string.
    Posebno važno za password koji može sadržati ; ili }.
    """
    return "{" + value.replace("}", "}}") + "}"


# ============================================================
# OpenAI
# ============================================================

llm = OpenAILlmService(
    api_key=OPENAI_API_KEY,
    model=OPENAI_MODEL
)


# ============================================================
# Microsoft SQL Server
# ============================================================

odbc_conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER=tcp:{MSSQL_HOST},{MSSQL_PORT};"
    f"DATABASE={MSSQL_DATABASE};"
    f"UID={MSSQL_USER};"
    f"PWD={odbc_escape(MSSQL_PASSWORD)};"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
    "Connection Timeout=30;"
)


mssql = MSSQLRunner(
    odbc_conn_str=odbc_conn_str
)


# ============================================================
# Shared file system
# ============================================================
#
# VEOMA BITNO:
#
# SQL, visualization, file i Python tools moraju koristiti isti
# filesystem.
#
# Tako:
#
# SQL
#   -> napravi query_results_xxx.csv
#
# Python
#   -> može taj CSV da obradi
#
# Python
#   -> napravi XLSX / PDF / ZIP
#
# /downloads
#   -> servira nastale fajlove
#
# ============================================================

file_system = LocalFileSystem(
    working_directory=str(FILES_ROOT)
)


# ============================================================
# Tools
# ============================================================

tools = ToolRegistry()


# ------------------------------------------------------------
# SQL
# ------------------------------------------------------------

tools.register_local_tool(
    RunSqlTool(
        sql_runner=mssql,
        file_system=file_system
    ),
    access_groups=[]
)


# ------------------------------------------------------------
# Charts
# ------------------------------------------------------------

tools.register_local_tool(
    VisualizeDataTool(
        file_system=file_system
    ),
    access_groups=[]
)


# ------------------------------------------------------------
# Write files
# ------------------------------------------------------------
#
# Agent sada može da napravi npr:
#
# generate_report.py
#
# ------------------------------------------------------------

tools.register_local_tool(
    WriteFileTool(
        file_system=file_system
    ),
    access_groups=[]
)


# ------------------------------------------------------------
# List files
# ------------------------------------------------------------

tools.register_local_tool(
    ListFilesTool(
        file_system=file_system
    ),
    access_groups=[]
)


# ------------------------------------------------------------
# Execute generated Python scripts
# ------------------------------------------------------------
#
# Ovo omogućava:
#
# - pandas
# - matplotlib
# - xlsxwriter
# - openpyxl
# - zipfile
#
# i stvarno generisanje PDF/XLSX/ZIP fajlova.
#
# ------------------------------------------------------------

tools.register_local_tool(
    RunPythonFileTool(
        file_system=file_system
    ),
    access_groups=[]
)


# ============================================================
# Agent
# ============================================================

agent = Agent(
    llm_service=llm,
    tool_registry=tools,

    user_resolver=OpenShiftUserResolver(),

    agent_memory=DemoAgentMemory(
        max_items=1000
    ),

    config=AgentConfig(
        max_tool_iterations=30
    )
)


# ============================================================
# Vanna FastAPI
# ============================================================

server = VannaFastAPIServer(agent)

app = server.create_app()


# ============================================================
# Download configuration
# ============================================================

DOWNLOADABLE_EXTENSIONS = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".zip",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
}


def is_downloadable_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in DOWNLOADABLE_EXTENSIONS
    )


# ============================================================
# Download index
# ============================================================
#
# Browser:
#
# https://TVOJ-ROUTE/downloads
#
# ============================================================

@app.get(
    "/downloads",
    response_class=HTMLResponse
)
async def downloads_index():

    USER_FILE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    files = [
        p
        for p in USER_FILE_DIR.iterdir()
        if is_downloadable_file(p)
    ]

    files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    rows = []

    for file_path in files:

        filename = file_path.name

        escaped_filename = html.escape(
            filename
        )

        encoded_filename = quote(
            filename
        )

        size_bytes = file_path.stat().st_size

        if size_bytes >= 1024 * 1024:
            size_text = (
                f"{size_bytes / (1024 * 1024):.2f} MB"
            )

        elif size_bytes >= 1024:
            size_text = (
                f"{size_bytes / 1024:.2f} KB"
            )

        else:
            size_text = (
                f"{size_bytes} B"
            )

        rows.append(
            f"""
            <tr>
                <td>{escaped_filename}</td>
                <td>{size_text}</td>
                <td>
                    <a href="/downloads/{encoded_filename}">
                        Preuzmi
                    </a>
                </td>
            </tr>
            """
        )


    if rows:

        table_body = "\n".join(rows)

    else:

        table_body = """
        <tr>
            <td colspan="3">
                Trenutno nema generisanih fajlova.
            </td>
        </tr>
        """


    page = f"""
    <!DOCTYPE html>

    <html lang="sr">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1"
        >

        <title>
            Vanna izveštaji
        </title>

        <style>

            body {{
                font-family:
                    Arial,
                    Helvetica,
                    sans-serif;

                max-width: 1100px;

                margin:
                    40px auto;

                padding:
                    0 20px;

                background:
                    #f5f5f5;
            }}

            .container {{
                background:
                    white;

                padding:
                    30px;

                border-radius:
                    10px;

                box-shadow:
                    0 2px 10px
                    rgba(0, 0, 0, 0.08);
            }}

            h1 {{
                margin-top:
                    0;
            }}

            table {{
                width:
                    100%;

                border-collapse:
                    collapse;

                margin-top:
                    20px;
            }}

            th,
            td {{
                padding:
                    12px;

                text-align:
                    left;

                border-bottom:
                    1px solid #ddd;
            }}

            th {{
                background:
                    #f0f0f0;
            }}

            a {{
                text-decoration:
                    none;

                font-weight:
                    bold;
            }}

        </style>

    </head>

    <body>

        <div class="container">

            <h1>
                Vanna izveštaji
            </h1>

            <p>
                Ovde se nalaze PDF, Excel, ZIP i ostali
                generisani izveštaji.
            </p>

            <table>

                <thead>

                    <tr>
                        <th>Fajl</th>
                        <th>Veličina</th>
                        <th>Preuzimanje</th>
                    </tr>

                </thead>

                <tbody>

                    {table_body}

                </tbody>

            </table>

        </div>

    </body>

    </html>
    """

    return HTMLResponse(
        content=page
    )


# ============================================================
# Download individual file
# ============================================================
#
# Primer:
#
# /downloads/Fakture_po_artiklima_2026.zip
#
# ============================================================

@app.get(
    "/downloads/{filename}"
)
async def download_file(
    filename: str
):

    # sprečava:
    #
    # ../../../etc/passwd
    #
    safe_filename = Path(filename).name

    if safe_filename != filename:

        raise HTTPException(
            status_code=400,
            detail="Invalid filename"
        )


    file_path = (
        USER_FILE_DIR
        / safe_filename
    )


    if (
        not file_path.exists()
        or not file_path.is_file()
    ):

        raise HTTPException(
            status_code=404,
            detail="File not found"
        )


    if (
        file_path.suffix.lower()
        not in DOWNLOADABLE_EXTENSIONS
    ):

        raise HTTPException(
            status_code=403,
            detail="File type is not downloadable"
        )


    return FileResponse(
        path=str(file_path),
        filename=safe_filename
    )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
