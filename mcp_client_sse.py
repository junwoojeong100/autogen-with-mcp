from autogen_ext.tools.mcp import SseMcpToolAdapter, SseServerParams
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def main() -> None:
    # Setup server params for remote service
    server_params = SseServerParams(url="http://localhost:8000/sse", headers={"Authorization": "Bearer xxxxxx"})

    print("[LOG] Creating adapter1 (get_alerts) ...")
    adapter1 = await SseMcpToolAdapter.from_server_params(server_params, "get_alerts")
    print("[LOG] adapter1 created: {}".format(adapter1))

    print("[LOG] Creating adapter2 (get_forecast) ...")
    adapter2 = await SseMcpToolAdapter.from_server_params(server_params, "get_forecast")
    print("[LOG] adapter2 created: {}".format(adapter2))

    # Prepare the model client (Azure OpenAI)
    model_client = AzureOpenAIChatCompletionClient(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    )

    # Initialize the AssistantAgent with streaming
    agent = AssistantAgent(
        name="weather_sse_assistant",
        model_client=model_client,
        tools=[adapter1, adapter2],
        reflect_on_tool_use=True,
        model_client_stream=True,
    )

    # Prompt to trigger SSE streaming of alerts and forecast
    prompt = "캘리포니아의 현재 기상 알림과 37.7749, -122.4194 위치의 일기예보를 SSE로 스트리밍해줘."

    # Stream and label responses: tool (MCP 서버) vs model (LLM)
    await Console(
        agent.run_stream(task=prompt)
    )

if __name__ == "__main__":
    asyncio.run(main())
