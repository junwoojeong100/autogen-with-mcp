from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main() -> None:
    params = StdioServerParams(
        command="python3",
        args=["weather.py"],
        read_timeout_seconds=60,
    )

    async with McpWorkbench(server_params=params) as workbench:
        tools = await workbench.list_tools()
        print("[사용 가능한 MCP 도구 목록]")
        print(tools)

        # 모델 클라이언트 준비 (Azure OpenAI)
        model_client = AzureOpenAIChatCompletionClient(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )

        # AssistantAgent에 MCP Workbench와 모델 클라이언트 연결
        agent = AssistantAgent(
            name="weather_assistant",
            model_client=model_client,
            workbench=workbench,
            reflect_on_tool_use=True,
            model_client_stream=True,
        )

        # 프롬프트 입력 시 MCP tool을 자동 호출
        prompt = "캘리포니아의 현재 기상 알림과 37.7749, -122.4194 위치의 일기예보를 알려줘."
        await Console(agent.run_stream(task=prompt))

if __name__ == "__main__":
    asyncio.run(main())
