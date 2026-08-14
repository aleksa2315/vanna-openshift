import os

from vanna import Agent, AgentConfig
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.core.registry import ToolRegistry
from vanna.core.user import User, UserResolver, RequestContext

from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.mysql import MySQLRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory

from vanna.tools import RunSqlTool, VisualizeDataTool


# ============================================================
# User resolver
# ============================================================
# Vanna 2.0.2 nema CookieEmailUserResolver u objavljenom paketu.
# Za pilot koristimo jednog statickog korisnika.
#
# OVO NIJE production authentication.
# Kasnije možemo povezati OpenShift OAuth / SSO / JWT.
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

MYSQL_HOST = os.environ["MYSQL_HOST"]
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PASSWORD = os.environ["MYSQL_PASSWORD"]

PORT = int(os.getenv("PORT", "8000"))


# ============================================================
# OpenAI
# ============================================================

llm = OpenAILlmService(
    api_key=OPENAI_API_KEY,
    model=OPENAI_MODEL
)


# ============================================================
# MySQL
# ============================================================

mysql = MySQLRunner(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    database=MYSQL_DATABASE,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD
)


# ============================================================
# Tools
# ============================================================

tools = ToolRegistry()


# SQL execution
tools.register_local_tool(
    RunSqlTool(
        sql_runner=mysql
    ),
    access_groups=[]
)


# Charts / visualization
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

    agent_memory=DemoAgentMemory(
        max_items=1000
    ),

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
