import os

from vanna import Agent, AgentConfig
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.core.registry import ToolRegistry
from vanna.core.user import CookieEmailUserResolver

from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.mysql import MySQLRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory

from vanna.tools import RunSqlTool, VisualizeDataTool


# OpenAI
llm = OpenAILlmService(
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.getenv("OPENAI_MODEL", "gpt-5")
)


# MySQL
mysql = MySQLRunner(
    host=os.environ["MYSQL_HOST"],
    port=int(os.getenv("MYSQL_PORT", "3306")),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"]
)


# Tools
tools = ToolRegistry()

tools.register_local_tool(
    RunSqlTool(sql_runner=mysql),
    access_groups=[]
)

tools.register_local_tool(
    VisualizeDataTool(),
    access_groups=[]
)


# Agent
agent = Agent(
    llm_service=llm,
    tool_registry=tools,
    user_resolver=CookieEmailUserResolver(),
    agent_memory=DemoAgentMemory(max_items=1000),
    config=AgentConfig()
)


# Web server
server = VannaFastAPIServer(agent)

server.run(
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8000"))
)
