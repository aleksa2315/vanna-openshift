import os

from vanna import Agent, AgentConfig
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.core.registry import ToolRegistry
from vanna.core.user import User, UserResolver, RequestContext

from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.mssql import MSSQLRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory

from vanna.tools import RunSqlTool, VisualizeDataTool


# ============================================================
# User resolver
# ============================================================

class OpenShiftUserResolver(UserResolver):

    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(
            id="openshift-pilot",
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


def odbc_escape(value: str) -> str:
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
# Tools
# ============================================================

tools = ToolRegistry()

tools.register_local_tool(
    RunSqlTool(
        sql_runner=mssql
    ),
    access_groups=[]
)

tools.register_local_tool(
    VisualizeDataTool(),
    access_groups=[]
)


# ============================================================
# Vanna Agent
# ============================================================

agent = Agent(
    llm_service=llm,
    tool_registry=tools,
    user_resolver=OpenShiftUserResolver(),
    agent_memory=DemoAgentMemory(max_items=1000),
    config=AgentConfig()
)


# ============================================================
# FastAPI server
# ============================================================

server = VannaFastAPIServer(agent)

server.run(
    host="0.0.0.0",
    port=PORT
)
