
# MCP 기반 서버로 리팩토링
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

mcp = FastMCP("weather")

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
    # 1. 포인트 정보 조회
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)
    if not points_data or "properties" not in points_data or "forecast" not in points_data["properties"]:
        return "No forecast found."
    forecast_url = points_data["properties"]["forecast"]
    # 2. 예보 정보 조회
    data = await make_nws_request(forecast_url)
    if not data or "properties" not in data:
        return "No forecast found."
    periods = data["properties"].get("periods", [])
    if not periods:
        return "No forecast found."
    forecast = [f"{p['name']}: {p['detailedForecast']}" for p in periods]
    return "\n".join(forecast)


# MCP 서버 실행 (SSE 타입)
if __name__ == "__main__":
    mcp.run(transport="sse") 
