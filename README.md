# autogen-with-mcp

## Python 3.12 가상환경 생성 및 패키지 설치 가이드


> ⚠️ **MCP 서버를 실행하려면 Python 3.11 이상이 필요합니다.**  
> (출처: [Python SDK FastMCP Server 공식 문서](https://modelcontextprotocol.io/python-sdk/fastmcp/#server-transport-options))
> 이번 실습에서는 Python 3.12 환경에서 아래 과정을 진행합니다.

1. Python 3.12로 가상환경 생성
```sh
python3.12 -m venv .venv
source .venv/bin/activate
```


2. requirements.txt의 패키지 설치
```sh
pip3 install -r requirements.txt
```

3. Azure AI Foundry(AOAI) 모델 배포 및 환경 변수 설정
   - Azure AI Foundry(예: Azure OpenAI Studio)에서 GPT-4.1 mini 등 원하는 모델을 배포합니다.
   - 배포 후, 아래 정보를 확인하여 `.env` 파일에 추가해야 합니다:
     - AZURE_OPENAI_ENDPOINT: Azure OpenAI Endpoint URL (예: https://xxxx.openai.azure.com/)
     - AZURE_OPENAI_API_KEY: Azure OpenAI API Key
     - AZURE_OPENAI_API_VERSION: API Version (예: 2024-12-01-preview)
     - AZURE_OPENAI_DEPLOYMENT_NAME: 배포한 모델의 Deployment Name
   - 예시:
     ```env
     AZURE_OPENAI_ENDPOINT=https://xxxx.openai.azure.com/
     AZURE_OPENAI_API_KEY=your-azure-openai-key
     AZURE_OPENAI_API_VERSION=2024-12-01-preview
     AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4-1-mini
     ```
   - 자세한 배포 및 환경 변수 설정 방법은 Azure OpenAI Studio(Foundry) 공식 문서를 참고하세요.

---

## MCP 서버 코드 작성 가이드

1. FastMCP 서버 인스턴스 생성
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("weather")
```

2. MCP 도구(툴) 등록
함수에 `@mcp.tool()` 데코레이터를 사용하여 MCP 서버에 도구를 등록할 수 있습니다.
```python
@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state."""
    # ... 구현 ...
    return "..."
```

3. 서버 실행 및 옵션 안내
FastMCP는 main 함수에서 실행하며, 다양한 transport 옵션을 지원합니다.

#### 지원하는 transport 옵션 (MCP 공식 문서 기준)
- `transport="stdio"` : 로컬 subprocess/stdin-stdout 기반 통신 (기본값, 빠르고 간단, 보안 필요 없음)
- `transport="sse"` : HTTP 기반 SSE(Server-Sent Events) 통신 (네트워크 접근, 여러 클라이언트 지원)
- `transport="streamable-http"` : HTTP 기반의 표준 REST API + 스트리밍 응답 지원 (AutoGen에서는 현재 지원하지 않음)

#### 예시: stdio(로컬)
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")  # 공식 기본값, 로컬 subprocess/stdin-stdout
```

#### 예시: SSE(HTTP)
```python
if __name__ == "__main__":
    mcp.run(transport="sse")  # http://localhost:8000/sse (기본 엔드포인트)
```

> **실행 옵션 요약**
> - 로컬 개발/테스트: `stdio` 권장
> - 네트워크/여러 클라이언트: `sse` 권장
> - 클라이언트/REST API/스트리밍: `streamable-http` 권장

공식 문서 참고: [MCP Transports Guide](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) 및 [Python SDK FastMCP Server](https://modelcontextprotocol.io/python-sdk/fastmcp/#server-transport-options)

각 transport에 따라 클라이언트 연결 방식도 달라지니, 아래 클라이언트 가이드도 참고하세요.

---

## AutoGen에서 MCP 서버 코드 호출 가이드

### 1. Local(로컬 stdio) 방식

`autogen_ext`의 `McpWorkbench`와 `StdioServerParams`를 사용하여 MCP 서버를 subprocess로 실행하고, 도구를 자동으로 인식할 수 있습니다.

예시:
```python
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

params = StdioServerParams(
    command="python3",
    args=["weather.py"],
    read_timeout_seconds=60,
)

async with McpWorkbench(server_params=params) as workbench:
    tools = await workbench.list_tools()
    print(tools)
    # 이후 AssistantAgent 등에서 workbench를 연결해 사용
```

#### 전체 예제 흐름 (stdio)
1. MCP 서버 코드(`weather.py`) 작성 및 도구 등록
2. autogen 클라이언트 코드(`mcp_client.py`)에서 MCP 서버를 subprocess로 실행
3. `McpWorkbench`를 통해 도구 목록을 확인하고, AssistantAgent 등에서 활용

#### 실행 방법 (stdio)
   - 클라이언트 실행 (macOS/Linux에서는 python3 권장):
     ```sh
     python3 mcp_client.py
     ```

자세한 예제는 `weather.py`, `mcp_client.py` 파일을 참고하세요.

---

### 2. SSE 방식 (원격/로컬 HTTP)

MCP 서버를 SSE(HTTP)로 실행하면 네트워크를 통해 클라이언트가 접속할 수 있습니다. 이때는 `SseServerParams`와 `SseMcpToolAdapter`를 사용합니다.

#### 서버 실행 예시 (`weather_sse.py`)
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

@mcp.tool()
async def get_alerts(state: str) -> str:
    ...

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    ...

if __name__ == "__main__":
    mcp.run(transport="sse")  # 또는 "stdio", "streamable-http" 등 공식 옵션만 사용
```

#### 클라이언트 예시 (`mcp_client_sse.py`)
```python
from autogen_ext.tools.mcp import SseMcpToolAdapter, SseServerParams

server_params = SseServerParams(url="http://localhost:8000/sse")
adapter1 = await SseMcpToolAdapter.from_server_params(server_params, "get_alerts")
adapter2 = await SseMcpToolAdapter.from_server_params(server_params, "get_forecast")

# 이후 AssistantAgent 등에서 adapter1, adapter2를 tools로 사용
```

#### 전체 예제 흐름 (SSE)
1. MCP 서버 코드(`weather_sse.py`) 작성 및 도구 등록
2. MCP 서버를 HTTP SSE 모드로 실행: `python weather_sse.py`
3. autogen 클라이언트 코드(`mcp_client_sse.py`)에서 SseServerParams로 서버에 접속
4. SseMcpToolAdapter로 도구를 가져와 AssistantAgent 등에서 활용

#### 실행 방법 (SSE)
   - 서버 실행 (macOS/Linux에서는 python3 권장):
     ```sh
     python3 weather_sse.py
     ```
   - 클라이언트 실행 (macOS/Linux에서는 python3 권장):
     ```sh
     python3 mcp_client_sse.py
     ```

자세한 예제는 `weather_sse.py`, `mcp_client_sse.py` 파일을 참고하세요.

---

## 공개된 MCP 서버 사용하기
VS Code와 같은 MCP Host 환경에서는 자신이 직접 만든 MCP 서버뿐만 아니라, 다른 개발자가 만든 MCP 서버(예: 원격 서버, 공개된 MCP 엔드포인트 등)도 쉽게 연결하여 사용할 수 있습니다.


1. **서버 엔드포인트 정보 확인:**
   - 사용할 MCP 서버의 URL(예: `https://example.com/sse`) 또는 접속 정보를 확인합니다.
   - 다양한 공개 MCP 서버 엔드포인트는 [smithery.ai](https://smithery.ai/)에서 탐색하거나 확인할 수 있습니다.

2. **클라이언트 설정:**
   - Autogen, VS Code 등에서 해당 서버의 엔드포인트를 지정하여 연결할 수 있습니다.
   - 예시: `SseServerParams(url="https://example.com/sse")`와 같이 사용

3. **도구 목록 불러오기 및 활용:**
   - 연결된 MCP 서버의 도구 목록을 불러와서, 자신의 프로젝트나 VS Code 내에서 바로 활용할 수 있습니다.



### VS Code에서 Azure MCP Server 사용 가이드 (Microsoft Learn 기반)

- Microsoft 공식 가이드: [Azure MCP Server 개요](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/)
- 빠른 시작: [Azure MCP Server Get Started](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/get-started?tabs=one-click%2Cazure-cli&pivots=mcp-github-copilot)
- `.vscode` 디렉토리에 `mcp.json` 설정 파일을 통해, VS Code에서 Azure MCP 서버에 대한 클라이언트 설정을 할 수 있습니다.

최신 정보와 상세 단계는 반드시 위 공식 문서를 참고하세요.

---

## 🚀 Azure 클라우드 배포 가이드

**FastMCP 서버를 AKS + APIM으로 배포하는 실습 가이드**

### 📖 상세 가이드
**[AKS_APIM_GUIDE.md](./AKS_APIM_GUIDE.md)** 

**학습 내용**: Docker 컨테이너화, Kubernetes 배포, API Gateway 보안, FastMCP 프로토콜
