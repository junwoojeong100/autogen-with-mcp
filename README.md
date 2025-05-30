

# autogen-with-mcp


## Python 3.12 가상환경 생성 및 패키지 설치 가이드

> ⚠️ **AutoGen에서 MCP 서버를 실행하려면 Python 3.10 이상이 필요합니다.**
> 이번 실습에서는 Python 3.12 환경에서 아래 과정을 진행합니다.

1. Python 3.12로 가상환경 생성
```sh
python3.12 -m venv myenv
source myenv/bin/activate
```

2. requirements.txt의 패키지 설치
```sh
pip3 install -r requirements.txt
```

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

3. 서버 실행
FastMCP는 일반적으로 main 함수에서 실행합니다.
```python
if __name__ == "__main__":
    mcp.serve()
```

---

## autogen에서 MCP 서버 코드 호출 가이드

`autogen_ext`의 `McpWorkbench`와 `StdioServerParams`를 사용하여 MCP 서버를 프로세스로 실행하고, 도구를 자동으로 인식할 수 있습니다.

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

### 전체 예제 흐름
1. MCP 서버 코드(`weather.py`) 작성 및 도구 등록
2. autogen 클라이언트 코드(`mcp_client.py`)에서 MCP 서버를 subprocess로 실행
3. `McpWorkbench`를 통해 도구 목록을 확인하고, AssistantAgent 등에서 활용

---
자세한 예제는 `weather.py`, `mcp_client.py` 파일을 참고하세요.
