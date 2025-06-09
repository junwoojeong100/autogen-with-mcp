# MCP 기반 서버로 리팩토링 (APIM 호환)
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
import json
import asyncio

# FastMCP 인스턴스 생성
mcp = FastMCP("weather-mcp-server")

NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

async def make_nws_request(url: str) -> dict[str, Any] | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

def format_alert(feature: dict) -> str:
    props = feature["properties"]
    return (
        f"Event: {props.get('event', 'Unknown')}\n"
        f"Area: {props.get('areaDesc', 'Unknown')}\n"
        f"Severity: {props.get('severity', 'Unknown')}\n"
        f"Description: {props.get('description', 'No description available')}\n"
        f"Instructions: {props.get('instruction', 'No specific instructions provided')}\n"
    )

# MCP 도구로 등록
@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state."""
    url = f"{NWS_API_BASE}/alerts/active?area={state.upper()}"
    data = await make_nws_request(url)
    if not data or "features" not in data:
        return "No alerts found."
    alerts = [format_alert(f) for f in data["features"]]
    return "\n---\n".join(alerts) if alerts else "No alerts found."

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a given latitude and longitude."""
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)
    if not points_data or "properties" not in points_data or "forecast" not in points_data["properties"]:
        return "No forecast found."
    forecast_url = points_data["properties"]["forecast"]
    data = await make_nws_request(forecast_url)
    if not data or "properties" not in data:
        return "No forecast found."
    periods = data["properties"].get("periods", [])
    if not periods:
        return "No forecast found."
    forecast = [f"{p['name']}: {p['detailedForecast']}" for p in periods]
    return "\n".join(forecast)

# MCP 서버 실행 (SSE 타입, /sse GET & /messages/ POST 지원)
if __name__ == "__main__":
    import uvicorn
    
    # FastMCP SSE 앱 가져오기
    sse_app = mcp.sse_app()
    
    # /messages Mount가 제대로 작동하지 않으므로 직접 처리
    # FastMCP SSE 앱의 messages 핸들러를 찾아서 직접 라우트 추가
    messages_mount = None
    for route in sse_app.routes:
        if hasattr(route, 'path') and route.path == '/messages':
            messages_mount = route
            break
    
    if messages_mount and hasattr(messages_mount, 'app'):
        # /messages/ POST 라우트를 직접 추가 (기존 Mount는 그대로 두고)
        from starlette.routing import Route
        
        async def messages_handler(request):
            """Handle /messages/ POST requests"""
            print(f"[DEBUG] Messages handler: {request.method} {request.url}")
            try:
                # 원래 messages mount의 app에 요청 전달
                return await messages_mount.app(request.scope, request.receive, request._send)
            except Exception as e:
                print(f"[ERROR] Messages handler error: {e}")
                from starlette.responses import JSONResponse
                return JSONResponse({"error": str(e)}, status_code=500)
        
        # /messages/ 라우트 추가 (trailing slash 포함)
        new_route = Route("/messages/", messages_handler, methods=["POST"])
        sse_app.routes.append(new_route)
        print("[DEBUG] Added explicit /messages/ POST route")
    else:
        print("[WARNING] Could not find messages mount in SSE app")
    
    print("Starting Weather MCP Server on 0.0.0.0:8000 (APIM Compatible)")
    print("Tools:", ", ".join([tool.__name__ for tool in [get_alerts, get_forecast]]))
    
    # 현재 SSE 앱의 라우트 확인 및 지원 엔드포인트 출력
    print("\n=== SSE App Routes ===")
    supported_endpoints = []
    
    for i, route in enumerate(sse_app.routes):
        methods = getattr(route, 'methods', 'N/A')
        route_type = type(route).__name__
        print(f"  {i+1}. {route.path} ({methods}) -> {route_type}")
        
        # 지원되는 엔드포인트 정보 수집
        if hasattr(route, 'path'):
            if hasattr(route, 'methods') and route.methods:
                for method in route.methods:
                    if route.path == '/sse' and method == 'GET':
                        supported_endpoints.append("GET /sse (SSE streaming)")
                    elif route.path == '/messages' and method == 'POST':
                        supported_endpoints.append("POST /messages (MCP protocol)")
            else:
                # Mount나 다른 타입의 라우트 처리
                if route.path == '/messages':
                    supported_endpoints.append("POST /messages (MCP protocol)")
    
    print(f"\n=== Supported Endpoints ===")
    for endpoint in supported_endpoints:
        print(f"  - {endpoint}")
    
    if not supported_endpoints:
        print("  - No supported endpoints detected")
    
    print("Features: FastMCP-based SSE transport")
    
    uvicorn.run(
        sse_app, 
        host="0.0.0.0", 
        port=8000
    )