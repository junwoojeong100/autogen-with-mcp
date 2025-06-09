from autogen_ext.tools.mcp import SseMcpToolAdapter, SseServerParams
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
import asyncio
import os
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def main() -> None:
    # Generate unique session ID for this client session
    session_id = str(uuid.uuid4())
    print(f"[DEBUG] Generated session ID: {session_id}")
    
    # Get APIM configuration from environment
    apim_endpoint = os.getenv("APIM_ENDPOINT")
    apim_subscription_key = os.getenv("APIM_SUBSCRIPTION_KEY")
    
    # Temporary: Test direct AKS connection
    use_direct_aks = True  # Set to False to use APIM
    
    if use_direct_aks:
        print("[DEBUG] Using direct AKS connection for testing...")
        base_url = "http://20.249.113.197"
        headers = {}
    else:
        if not apim_endpoint or not apim_subscription_key:
            print("[ERROR] APIM_ENDPOINT and APIM_SUBSCRIPTION_KEY environment variables are required")
            return
        base_url = apim_endpoint
        headers = {"Ocp-Apim-Subscription-Key": apim_subscription_key}
    
    print(f"[DEBUG] Base URL: {base_url}")
    if headers:
        print(f"[DEBUG] Subscription Key: {'*' * (len(apim_subscription_key) - 4) + apim_subscription_key[-4:] if len(apim_subscription_key) > 4 else 'SET'}")
    
    # Setup server params
    if use_direct_aks:
        sse_url = f"{base_url}/sse"
    else:
        sse_url = f"{base_url}/mcp/sse"
    
    print(f"[DEBUG] SSE URL: {sse_url}")
    
    # Create custom server params with session_id support
    server_params = SseServerParams(
        url=sse_url, 
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Session-ID": session_id  # Add session ID to headers
        }
    )

    print("[LOG] Creating adapter1 (get_alerts) ...")
    print("[DEBUG] This may take 30-60 seconds for APIM/AKS connection...")
    print(f"[DEBUG] Using session ID: {session_id}")
    
    # Test APIM connectivity first
    print("[DEBUG] Testing APIM endpoint connectivity...")
    
    # Test session_id support
    connection_ok = await test_mcp_connection(sse_url, headers, session_id, base_url, use_direct_aks)
    if not connection_ok:
        print("[WARNING] Session ID test failed, but continuing with adapter creation...")
    
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # Test basic connectivity to APIM
            test_response = await asyncio.wait_for(
                client.get(
                    sse_url,
                    headers=headers,
                    timeout=10.0
                ),
                timeout=15.0
            )
            print(f"[DEBUG] Endpoint status: {test_response.status_code}")
    except Exception as e:
        print(f"[DEBUG] Connectivity test failed: {e}")
    
    # Retry logic for adapter creation
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] Adapter1 creation attempt {attempt + 1}/{max_retries}")
            adapter1 = await asyncio.wait_for(
                SseMcpToolAdapter.from_server_params(server_params, "get_alerts"),
                timeout=60.0
            )
            print("[LOG] adapter1 created: {}".format(adapter1))
            break
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                print(f"[ERROR] Failed to create adapter1 after {max_retries} attempts")
                return
            await asyncio.sleep(2)  # Wait before retry

    print("[LOG] Creating adapter2 (get_forecast) ...")
    
    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] Adapter2 creation attempt {attempt + 1}/{max_retries}")
            adapter2 = await asyncio.wait_for(
                SseMcpToolAdapter.from_server_params(server_params, "get_forecast"),
                timeout=60.0
            )
            print("[LOG] adapter2 created: {}".format(adapter2))
            break
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                print(f"[ERROR] Failed to create adapter2 after {max_retries} attempts")
                return
            await asyncio.sleep(2)  # Wait before retry

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

async def test_mcp_connection(sse_url, headers, session_id, base_url, use_direct_aks):
    """Test MCP connection with session_id support"""
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            # Test SSE connection
            print(f"[DEBUG] Testing SSE connection: {sse_url}")
            sse_response = await client.get(
                sse_url,
                headers={**headers, "Accept": "text/event-stream"},
                timeout=10.0
            )
            print(f"[DEBUG] SSE status: {sse_response.status_code}")
            
            # Test messages endpoint with session_id as query parameter
            if use_direct_aks:
                messages_url = f"{base_url}/messages/"
            else:
                messages_url = f"{base_url}/mcp/messages/"
            
            print(f"[DEBUG] Testing messages endpoint: {messages_url}?session_id={session_id}")
            messages_response = await client.post(
                messages_url,
                params={"session_id": session_id},  # Use query parameter
                headers={**headers, "Content-Type": "application/json"},
                json={"test": "connection"},
                timeout=10.0
            )
            print(f"[DEBUG] Messages status: {messages_response.status_code}")
            
            return True
    except Exception as e:
        print(f"[DEBUG] Connection test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(main())