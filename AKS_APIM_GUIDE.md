# AKS + APIM을 활용한 MCP 서버 보안 실습 가이드

---

## 📑 목차
1. [아키텍처 개요](#아키텍처-개요)
2. [프로젝트 구조 확인](#📋-프로젝트-구조-확인)
3. [사전 준비사항](#사전-준비사항)
4. [AKS 클러스터 생성](#1-aks-클러스터-생성)
5. [MCP 서버 컨테이너 이미지 생성](#2-mcp-서버-컨테이너-이미지-생성)
6. [Kubernetes 배포 파일 생성](#3-kubernetes-배포-파일-생성)
7. [Azure API Management 설정](#4-azure-api-management-설정)
8. [클라이언트 코드 수정](#5-클라이언트-코드-수정)
9. [환경 변수 설정](#6-환경-변수-설정)
10. [실행 및 테스트](#7-실행-및-테스트)
11. [디버깅 및 문제해결](#8-디버깅-및-문제해결)
12. [중요 참고사항 및 주의점](#중요한-참고사항-및-주의점)
13. [보안 강화 포인트](#보안-강화-포인트)
14. [추가 보안 설정 (선택사항)](#추가-보안-설정-선택사항)
15. [정리 및 리소스 삭제](#정리-및-리소스-삭제)
16. [요약](#🎯-요약)
17. [문제해결 FAQ](#🔧-문제해결-faq)
18. [추가 리소스 및 참고자료](#📚-추가-리소스-및-참고자료)

---


이 가이드는 **FastMCP 기반 MCP 서버(weather_sse_apim.py)**를 AKS에 배포하고 **Azure API Management(APIM)**을 통해 보안을 강화하는 실습 과정을 다룹니다.

## 아키텍처 개요

```
[로컬 mcp_client_sse_apim.py] → [Azure APIM] → [AKS의 weather_sse_apim.py] → [NWS API]
                                    ↓                        ↓
                              [SSE /sse (GET)]        [Messages /messages/{session_id} (POST)]
                              [Authentication]        [Session Management]              
```

- **weather_sse_apim.py**: AKS 클러스터에 배포된 FastMCP 기반 MCP 서버 (APIM 호환)
- **mcp_client_sse_apim.py**: 로컬에서 실행되는 클라이언트 (APIM 연동, 재시도 로직 포함)
- **APIM**: API 게이트웨이로 인증, 모니터링, 보안 기능 제공
- **핵심 엔드포인트**:
  - `GET /sse`: SSE 연결 초기화 (MCP 프로토콜 시작)
  - `POST /messages`: MCP 메시지 전송 (도구 호출 등)

### 📋 프로젝트 구조 확인

💡 **Tip:** 실습을 시작하기 전에 다음과 같은 파일 구조가 있는지 꼭 확인하세요.

```
autogen-with-mcp/
├── AKS_APIM_GUIDE.md              # 이 가이드 파일
├── azure-commands.sh              # Azure CLI 명령어 스크립트 (전체 배포 자동화)
├── check_deployment_status.sh     # 배포 상태 확인 스크립트
├── Dockerfile                     # 컨테이너 이미지 생성용
├── deployment.yaml                # Kubernetes 배포 설정
├── requirements.txt               # Python 패키지 의존성
├── weather_sse_apim.py            # 🔥 주요: FastMCP 기반 MCP 서버 (APIM 호환)
├── mcp_client_sse_apim.py         # 🔥 주요: MCP 클라이언트 (APIM 연동, 재시도 로직)
├── mcp_client_sse.py              # 직접 연결용 클라이언트 (테스트용)
├── apim-policy-sse-connection.xml # APIM SSE 연결 정책 (GET /sse)
├── apim-policy-mcp-messages.xml   # APIM MCP POST 메시지 정책 (POST /messages/{session_id})
├── apim-policy-api-level.xml      # APIM API 레벨 정책 (CORS, 공통 설정)
└── README.md                      # 프로젝트 설명
```


## 사전 준비사항

- Azure CLI 설치 및 로그인
- Docker 설치
- kubectl 설치
- Azure 구독 및 리소스 그룹
- Python 3.12+ 설치
- Git (프로젝트 클론용)

## 1. AKS 클러스터 생성

```bash

# 리소스 그룹 생성
az group create --name rg-mcp-lab --location koreacentral

# AKS 클러스터 생성 (기본 노드 1개)
az aks create \
  --resource-group rg-mcp-lab \
  --name aks-mcp-cluster \
  --node-count 1 \
  --node-vm-size Standard_DS4_v2 \
  --enable-addons monitoring \
  --generate-ssh-keys

# kubectl 설정
az aks get-credentials --resource-group rg-mcp-lab --name aks-mcp-cluster
```

## 2. MCP 서버 컨테이너 이미지 생성

### Dockerfile 생성
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY weather_sse_apim.py .

EXPOSE 8000

CMD ["python", "weather_sse_apim.py"]
```

**참고**: 이 Dockerfile은 weather_sse_apim.py에서 FastMCP를 사용하여 SSE 및 Messages 엔드포인트를 제공합니다. 서버는 `/sse` (GET, SSE 스트리밍)과 `/messages/{session_id}` (POST, MCP 프로토콜) 경로를 모두 지원합니다.

### 이미지 빌드 및 푸시

#### 기본 빌드 방법
```bash
# Azure Container Registry 생성
az acr create --resource-group rg-mcp-lab --name acrmcplab --sku Basic

# ACR에 로그인
az acr login --name acrmcplab

# 이미지 빌드 및 푸시 (단일 플랫폼)
docker build -t acrmcplab.azurecr.io/weather-mcp:latest .
docker push acrmcplab.azurecr.io/weather-mcp:latest
```

#### 멀티 플랫폼 빌드 방법 (권장)

**🚀 Docker Buildx를 사용한 멀티 플랫폼 이미지 빌드**

멀티 플랫폼 이미지를 생성하면 다양한 아키텍처(Intel/AMD, Apple Silicon 등)에서 동일한 이미지를 사용할 수 있습니다.

```bash
# 1. Docker Buildx 활성화 확인
docker buildx version

# 2. 멀티 플랫폼 빌더 생성 (최초 1회만)
docker buildx create --name multiplatform-builder --use

# 3. 빌더 부트스트랩 (최초 1회만)
docker buildx inspect --bootstrap

# 4. 멀티 플랫폼 이미지 빌드 및 푸시
docker buildx build --platform linux/amd64,linux/arm64 \
  -t acrmcplab.azurecr.io/weather-mcp:latest \
  --push .
```

**💡 주요 장점:**
- **linux/amd64**: 대부분의 클라우드 인스턴스와 Intel/AMD 프로세서
- **linux/arm64**: Apple Silicon Mac, ARM 기반 서버, AWS Graviton 등
- **단일 태그**: 하나의 이미지 태그로 모든 플랫폼 지원
- **자동 선택**: Docker가 실행 환경에 맞는 아키텍처를 자동으로 선택

**🔍 빌드 확인:**
```bash
# 이미지의 멀티 플랫폼 정보 확인
docker buildx imagetools inspect acrmcplab.azurecr.io/weather-mcp:latest

# 예상 출력:
# Name:      acrmcplab.azurecr.io/weather-mcp:latest
# MediaType: application/vnd.docker.distribution.manifest.list.v2+json
# Digest:    sha256:...
# 
# Manifests:
#   Name:        acrmcplab.azurecr.io/weather-mcp:latest@sha256:...
#   MediaType:   application/vnd.docker.distribution.manifest.v2+json
#   Platform:    linux/amd64
# 
#   Name:        acrmcplab.azurecr.io/weather-mcp:latest@sha256:...
#   MediaType:   application/vnd.docker.distribution.manifest.v2+json
#   Platform:    linux/arm64
```

**⚠️ 주의사항:**
- 멀티 플랫폼 빌드는 `--push` 플래그가 필요합니다 (로컬 저장 불가)
- 빌드 시간이 더 오래 걸립니다 (두 개의 아키텍처를 빌드하므로)
- ARM64 빌드 시 일부 패키지는 컴파일이 필요할 수 있습니다

```bash
# AKS에 ACR 연결 (⚠️ ACR 이름이 정확히 일치해야 함)
az aks update -n aks-mcp-cluster -g rg-mcp-lab --attach-acr acrmcplab
```

## 3. Kubernetes 배포 파일 생성

### deployment.yaml
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: weather-mcp-deployment
  labels:
    app: weather-mcp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: weather-mcp
  template:
    metadata:
      labels:
        app: weather-mcp
    spec:
      containers:
      - name: weather-mcp
        image: acrmcplab.azurecr.io/weather-mcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: PORT
          value: "8000"
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "128Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: weather-mcp-service
spec:
  selector:
    app: weather-mcp
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer
```

### AKS에 배포
```bash
kubectl apply -f deployment.yaml

# 서비스 상태 확인
kubectl get services weather-mcp-service
```

## 4. Azure API Management 설정

### APIM 인스턴스 생성
```bash
az apim create \
  --name apim-mcp-lab \
  --resource-group rg-mcp-lab \
  --publisher-name "MCP Lab" \
  --publisher-email "admin@example.com" \
  --sku-name Developer
```

### FastMCP 호환 API 등록 및 정책 설정

#### 1. 백엔드 서비스 IP 확인
먼저 AKS에서 실행 중인 서비스의 외부 IP를 확인합니다:

```bash
# 서비스 외부 IP 확인
kubectl get services weather-mcp-service

# IP만 추출하기
BACKEND_IP=$(kubectl get services weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Backend IP: $BACKEND_IP"
```

#### 2. FastMCP 호환 API 생성
Azure Portal에서 APIM 서비스로 이동:

1. **APIs** → **+ Add API** → **HTTP** 선택
2. **설정값 입력:**
   - **Display name**: `Weather MCP API (FastMCP)`
   - **Name**: `weather-mcp-api`
   - **Web service URL**: `http://[위에서 확인한 외부 IP]:8000` (예: `http://20.1.2.3:8000`)
   - **API URL suffix**: `mcp`

#### 3. FastMCP 핵심 Operations 추가

**🔥 중요: FastMCP는 오직 2개의 엔드포인트만 사용합니다:**

1. **SSE Connection (GET /sse):**
   - **Method**: GET
   - **URL**: `/sse`
   - **Display name**: `SSE Connection (MCP Initialization)`
   - **용도**: MCP 프로토콜 초기화 및 세션 생성

2. **MCP Messages (POST /messages/{session_id}):**
   - **Method**: POST
   - **URL**: `/messages/{session_id}`
   - **Display name**: `MCP Messages (Protocol Communication)`
   - **용도**: 도구 호출 및 응답 처리

**Azure CLI로 API 생성:**
```bash
# 백엔드 IP 설정
BACKEND_IP=$(kubectl get service weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# 백엔드 정의
az apim backend create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --backend-id mcp-backend \
    --url "http://$BACKEND_IP:8000" \
    --protocol http

# API 생성
az apim api create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --path "/mcp" \
    --display-name "Weather MCP Server API (FastMCP)" \
    --service-url "http://$BACKEND_IP:8000"

# SSE Connection 엔드포인트
az apim api operation create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id sse-connection \
    --method GET \
    --url-template "/sse" \
    --display-name "SSE Connection (MCP Initialization)"

# MCP Messages 엔드포인트  
az apim api operation create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id mcp-messages \
    --method POST \
    --url-template "/messages/{session_id}" \
    --display-name "MCP Messages (Protocol Communication)"
```

#### 4. APIM 정책 설정

각 엔드포인트별로 전용 정책을 적용합니다:

**4.1. SSE Connection 정책 적용:**
```bash
az apim api operation policy create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id sse-connection \
    --policy-format xml \
    --value @apim-policy-sse-connection.xml
```

**4.2. MCP Messages 정책 적용:**
```bash
az apim api operation policy create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id mcp-messages \
    --policy-format xml \
    --value @apim-policy-mcp-messages.xml
```

**4.3. API 레벨 정책 적용 (CORS 등):**
```bash
az apim api policy create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --policy-format xml \
    --value @apim-policy-api-level.xml
```

#### 5. Subscription Key 생성

Azure Portal에서 **APIM** → **APIs** → **Weather MCP API** → **All operations** → **Policies**로 이동하여 다음 정책을 설정합니다:

```xml
<policies>
    <inbound>
        <base />
        <!-- API Key 인증 -->
        <check-header name="Ocp-Apim-Subscription-Key" failed-check-httpcode="401" failed-check-error-message="Subscription key is required" />
        
        <!-- Rate limiting -->
        <rate-limit calls="1000" renewal-period="60" />
        
        <!-- CORS 설정 (SSE 연결을 위해 필수) -->
        <cors allow-credentials="true">
            <allowed-origins>
                <origin>*</origin> <!-- 🔒 운영 환경에서는 특정 도메인으로 제한 -->
            </allowed-origins>
            <allowed-methods>
                <method>GET</method>
                <method>POST</method>
                <method>OPTIONS</method>
            </allowed-methods>
            <allowed-headers>
                <header>*</header>
            </allowed-headers>
        </cors>
        
        <!-- SSE 연결을 위한 캐시 비활성화 -->
        <set-header name="Cache-Control" exists-action="override">
            <value>no-cache</value>
        </set-header>
        <set-header name="Connection" exists-action="override">
            <value>keep-alive</value>
        </set-header>
    </inbound>
    <backend>
        <base />
        <!-- SSE 연결을 위한 긴 타임아웃 설정 -->
        <timeout>300</timeout>
    </backend>
    <outbound>
        <base />
        <!-- SSE 응답 헤더 설정 -->
        <choose>
            <when condition="@(context.Request.Method == "GET")">
                <set-header name="Content-Type" exists-action="override">
                    <value>text/event-stream</value>
                </set-header>
                <set-header name="Cache-Control" exists-action="override">
                    <value>no-cache</value>
                </set-header>
            </when>
        </choose>
        
        <!-- 응답 헤더 추가 -->
        <set-header name="X-Powered-By" exists-action="override">
            <value>Azure APIM</value>
        </set-header>
    </outbound>
    <on-error>
        <base />
        <!-- 에러 처리 -->
        <return-response>
            <set-status code="500" reason="Internal Server Error" />
            <set-header name="Content-Type" exists-action="override">
                <value>application/json</value>
            </set-header>
            <set-body>@{
                return new JObject(
                    new JProperty("error", context.LastError.Message),
                    new JProperty("timestamp", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"))
                ).ToString();
            }</set-body>
        </return-response>
    </on-error>
</policies>
```

#### 5. Subscription Key 관리

1. **Products** → **Unlimited** (또는 새 Product 생성) → **Add API**에서 생성한 API 추가
2. **Subscriptions**에서 새 구독 생성:
   - **Name**: `mcp-client-subscription`
   - **Display name**: `MCP Client Subscription`
   - **Products**: 위에서 설정한 Product 선택
3. 생성된 **Primary key**를 클라이언트에서 사용

## 5. 클라이언트 코드 수정

### mcp_client_sse_apim.py (현재 구현된 버전)
```python
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
    # Get APIM configuration from environment
    apim_endpoint = os.getenv("APIM_ENDPOINT")
    apim_subscription_key = os.getenv("APIM_SUBSCRIPTION_KEY")
    
    # Temporary: Test direct AKS connection
    use_direct_aks = True  # Set to False to use APIM
    
    if use_direct_aks:
        print("[DEBUG] Using direct AKS connection for testing...")
        base_url = "http://20.249.113.197"  # Your actual AKS LoadBalancer IP
        headers = {}
    else:
        if not apim_endpoint or not apim_subscription_key:
            print("[ERROR] APIM_ENDPOINT and APIM_SUBSCRIPTION_KEY environment variables are required")
            return
        base_url = apim_endpoint
        headers = {"Ocp-Apim-Subscription-Key": apim_subscription_key}
    
    print(f"[DEBUG] Base URL: {base_url}")
    
    # Setup server params
    if use_direct_aks:
        sse_url = f"{base_url}/sse"
    else:
        sse_url = f"{base_url}/mcp/sse"
    
    print(f"[DEBUG] SSE URL: {sse_url}")
    
    server_params = SseServerParams(
        url=sse_url, 
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache"
        }
    )

    print("[LOG] Creating adapter1 (get_alerts) ...")
    print("[DEBUG] This may take 30-60 seconds for APIM/AKS connection...")
    
    # Test APIM connectivity first
    print("[DEBUG] Testing endpoint connectivity...")
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            test_response = await asyncio.wait_for(
                client.get(sse_url, headers=headers, timeout=10.0),
                timeout=15.0
            )
            print(f"[DEBUG] Endpoint status: {test_response.status_code}")
    except Exception as e:
        print(f"[DEBUG] Connectivity test failed: {e}")
    
    # Retry logic for adapter creation
    max_retries = 3
    
    # Create adapter1 (get_alerts)
    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] Adapter1 creation attempt {attempt + 1}/{max_retries}")
            adapter1 = await asyncio.wait_for(
                SseMcpToolAdapter.from_server_params(server_params, "get_alerts"),
                timeout=60.0
            )
            print("[LOG] adapter1 created successfully")
            break
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                print(f"[ERROR] Failed to create adapter1 after {max_retries} attempts")
                return
            await asyncio.sleep(2)

    print("[LOG] Creating adapter2 (get_forecast) ...")
    
    # Create adapter2 (get_forecast)
    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] Adapter2 creation attempt {attempt + 1}/{max_retries}")
            adapter2 = await asyncio.wait_for(
                SseMcpToolAdapter.from_server_params(server_params, "get_forecast"),
                timeout=60.0
            )
            print("[LOG] adapter2 created successfully")
            break
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                print(f"[ERROR] Failed to create adapter2 after {max_retries} attempts")
                return
            await asyncio.sleep(2)

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

    # Interactive console mode
    print("[LOG] 날씨 어시스턴트가 준비되었습니다!")
    print("[LOG] 대화를 시작합니다. 'quit' 또는 'exit'를 입력하면 종료됩니다.")
    print("\n💡 테스트 예시:")
    print("- What are the current weather alerts for California?")
    print("- Can you get the forecast for coordinates 37.7749, -122.4194?")
    print("- Show me weather alerts for Texas")
    
    # Start interactive console
    await Console(agent).start()

if __name__ == "__main__":
    asyncio.run(main())
```

**🔥 현재 구현의 주요 특징:**
- **직접 AKS 연결 모드**: `use_direct_aks = True`로 설정하여 APIM 우회 가능
- **하드코딩된 IP**: 실제 AKS LoadBalancer IP (20.249.113.197) 사용  
- **연결성 테스트**: httpx를 통한 사전 연결 확인
- **재시도 로직**: 어댑터 생성 실패 시 최대 3회 재시도
- **스트리밍 모드**: `model_client_stream=True`로 실시간 응답
- **대화형 콘솔**: Console 모드로 대화 지속
- **좌표 기반 예보**: latitude, longitude를 사용한 날씨 예보 조회

## 6. 환경 변수 설정

### .env 파일 생성 및 환경변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 다음 내용을 추가합니다:

```env
# Azure OpenAI 설정 (필수)
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini

# APIM 설정 (APIM 사용 시 필요)
APIM_ENDPOINT=https://apim-mcp-lab.azure-api.net
APIM_SUBSCRIPTION_KEY=your-apim-subscription-key

# 백엔드 정보 (참고용)
BACKEND_IP=your-aks-loadbalancer-ip
```

**💡 현재 클라이언트 동작 방식:**
- **직접 AKS 연결**: `use_direct_aks = True` (기본값)
  - 하드코딩된 IP: `http://20.249.113.197` 사용
  - APIM 환경변수 불필요
- **APIM 경유**: `use_direct_aks = False`로 변경 시
  - `APIM_ENDPOINT`, `APIM_SUBSCRIPTION_KEY` 필요

**🔧 클라이언트 코드에서 APIM 모드로 변경하려면:**
```python
# mcp_client_sse_apim.py 파일에서
use_direct_aks = False  # True -> False로 변경
```

**💡 환경변수 자동 설정 (azure-commands.sh 실행 시):**
`azure-commands.sh`를 실행하면 `.env` 파일이 자동으로 생성됩니다:

```bash
# 전체 배포 스크립트 실행
bash azure-commands.sh

# 또는 환경변수만 설정
BACKEND_IP=$(kubectl get service weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
APIM_GATEWAY_URL=$(az apim show --resource-group rg-mcp-lab --name apim-mcp-lab --query "gatewayUrl" --output tsv)
APIM_SUBSCRIPTION_KEY=$(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)

cat > .env << EOF
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
APIM_ENDPOINT=$APIM_GATEWAY_URL
APIM_SUBSCRIPTION_KEY=$APIM_SUBSCRIPTION_KEY
BACKEND_IP=$BACKEND_IP
EOF
```

**🔍 환경변수 확인:**
```bash
# .env 파일 내용 확인
cat .env

# 환경변수 로드 테스트
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
print('APIM Endpoint:', os.getenv('APIM_ENDPOINT'))
print('APIM Subscription Key:', '*' * 10 if os.getenv('APIM_SUBSCRIPTION_KEY') else 'NOT SET')
print('Backend IP:', os.getenv('BACKEND_IP'))
print('Direct AKS mode: Check use_direct_aks variable in mcp_client_sse_apim.py')
"
```

## 7. 실행 및 테스트

### 자동화된 배포 및 테스트

**🚀 한 번에 모든 것을 배포하려면:**
```bash
# 전체 배포 스크립트 실행 (환경변수 자동 설정 포함)
bash azure-commands.sh

# .env 파일이 자동 생성됨을 확인
cat .env
```

### 단계별 배포 확인

### 1단계: AKS에서 MCP 서버 상태 확인
```bash
# 포드 상태 확인
kubectl get pods -l app=weather-mcp

# 서비스 LoadBalancer IP 확인  
kubectl get svc weather-mcp-service

# 서버 로그 확인 (FastMCP 엔드포인트 등록 확인)
kubectl logs -l app=weather-mcp --tail=20

# 예상 로그 출력:
# [LOG] Starting FastMCP server on 0.0.0.0:8000
# [ROUTES] GET /sse -> handle_sse
# [ROUTES] POST /messages/{session_id} -> handle_messages
```

### 2단계: 백엔드 직접 테스트 (APIM 우회)
```bash
# 백엔드 IP 가져오기
BACKEND_IP=$(kubectl get svc weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Backend IP: $BACKEND_IP"

# SSE 엔드포인트 직접 테스트
curl -X GET "http://$BACKEND_IP:8000/sse" \
  -H "Accept: text/event-stream" \
  -H "Cache-Control: no-cache" \
  -v

# 예상 응답: SSE 스트림 시작 및 session_id 수신
```

### 3단계: APIM을 통한 API 테스트
```bash
# APIM 정보 가져오기
APIM_URL=$(az apim show --resource-group rg-mcp-lab --name apim-mcp-lab --query "gatewayUrl" --output tsv)
SUBSCRIPTION_KEY=$(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)

echo "APIM Gateway URL: $APIM_URL"
echo "Subscription Key: ${SUBSCRIPTION_KEY:0:10}..."

# APIM을 통한 SSE 연결 테스트
curl -X GET "$APIM_URL/mcp/sse" \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY" \
  -H "Accept: text/event-stream" \
  -v

# 응답 헤더에서 APIM 처리 확인:
# X-Powered-By: Azure APIM
```

### 4단계: 로컬 클라이언트 실행
```bash
# 필요한 패키지 설치 (최초 1회만 실행)
pip install -r requirements.txt

# Azure OpenAI 환경변수를 .env에 추가 (수동 - 필수)
# AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY 등

# 클라이언트 실행 (현재는 직접 AKS 연결 모드)
python3 mcp_client_sse_apim.py
```

**📋 현재 클라이언트 동작 방식:**
- **기본 모드**: 직접 AKS 연결 (`use_direct_aks = True`)
- **하드코딩 IP**: `http://20.249.113.197` (실제 LoadBalancer IP)
- **APIM 모드**: 코드에서 `use_direct_aks = False`로 변경 시 APIM 경유

### 5단계: 클라이언트 실행 로그 예시

**성공적인 직접 AKS 연결:**
```
[DEBUG] Using direct AKS connection for testing...
[DEBUG] Base URL: http://20.249.113.197
[DEBUG] SSE URL: http://20.249.113.197/sse
[LOG] Creating adapter1 (get_alerts) ...
[DEBUG] This may take 30-60 seconds for APIM/AKS connection...
[DEBUG] Testing endpoint connectivity...
[DEBUG] Endpoint status: 200
[DEBUG] Adapter1 creation attempt 1/3
[LOG] adapter1 created successfully
[LOG] Creating adapter2 (get_forecast) ...
[DEBUG] Adapter2 creation attempt 1/3
[LOG] adapter2 created successfully
[LOG] 날씨 어시스턴트가 준비되었습니다!
[LOG] 대화를 시작합니다. 'quit' 또는 'exit'를 입력하면 종료됩니다.

💡 테스트 예시:
- What are the current weather alerts for California?
- Can you get the forecast for coordinates 37.7749, -122.4194?
- Show me weather alerts for Texas

User: What are the weather alerts for California?
```

### 6단계: 실제 테스트 예시
클라이언트 실행 후 다음과 같은 질문들을 시도해보세요:

**테스트 시나리오:**
1. **날씨 경고 조회:**
   ```
   "What are the current weather alerts for California?"
   "Show me any severe weather warnings for Texas"
   ```

2. **일기예보 조회 (좌표 기반):**
   ```
   "Can you get the forecast for coordinates 37.7749, -122.4194?"
   "What's the weather forecast for latitude 40.7589, longitude -73.9851?"
   ```

3. **한국어 테스트:**
   ```
   "캘리포니아의 현재 기상 알림을 알려줘"
   "37.7749, -122.4194 좌표의 일기예보는?"
   ```

### 📊 성공 시 예상 결과

**어시스턴트 응답 예시:**
```
Assistant: I'll check the current weather alerts for California.

[도구 호출: get_alerts("California")]

Based on the latest data from the National Weather Service, here are the current weather alerts for California:

�️ High Wind Warning - Los Angeles County
📅 Valid until: 2025-06-10 18:00 PST
🎯 Affected areas: Coastal areas and mountain regions  
⚠️ Details: Southwest winds 25-35 mph with gusts up to 60 mph expected...

🔥 Red Flag Warning - Northern California
📅 Valid until: 2025-06-10 20:00 PST
🎯 Affected areas: North Bay hills and mountains
⚠️ Details: Critical fire weather conditions due to strong winds and low humidity...

Please stay safe and follow local emergency guidelines.
```
- "Can you get the weather forecast for New York City? (latitude: 40.7128, longitude: -74.0060)"
- "Are there any severe weather warnings for Texas?"

## 8. 디버깅 및 문제해결

### 일반적인 문제와 해결방법

#### 1. MCP 서버 연결 실패
```bash
# 포드 상태 확인
kubectl get pods -l app=weather-mcp

# 포드 로그 확인
kubectl logs -l app=weather-mcp

# 서비스 상태 확인
kubectl get svc weather-mcp-service

# 포드 내부 접속하여 디버깅
kubectl exec -it <pod-name> -- sh
```

#### 2. APIM 연결 문제
```bash
# APIM 서비스 상태 확인
az apim show --name apim-mcp-lab --resource-group rg-mcp-lab

# API 설정 확인
# Azure Portal > APIM > APIs > Test 탭에서 직접 테스트
```

### 📦 Python 패키지 설치

실습 시작 전에 다음 명령어로 필요한 Python 패키지들을 설치합니다:

```bash
# 가상환경 생성 (권장)
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 패키지 설치
pip install -r requirements.txt
```

### requirements.txt 내용 확인
프로젝트 루트의 `requirements.txt` 파일에 다음 내용이 포함되어 있는지 확인하세요:

```pip-requirements
autogen-agentchat
autogen-ext[openai,azure,mcp]
openai
python-dotenv
httpx
mcp[cli]
fastapi
uvicorn
```

**💡 Tip**: 가상환경 사용을 권장하며, 이 requirements.txt 파일은 MCP 서버와 클라이언트 모두에서 사용됩니다.

#### 환경변수 설정 확인
실습 진행 전에 환경변수가 올바르게 설정되었는지 확인합니다:

```bash
# .env 파일 존재 확인
ls -la .env

# 환경변수 로드 테스트 (Python에서)
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
required_vars = ['AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_DEPLOYMENT_NAME', 'APIM_SUBSCRIPTION_KEY']
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    print(f'❌ 누락된 환경변수: {missing}')
else:
    print('✅ 모든 필수 환경변수가 설정되었습니다.')
"
```

#### 4. 네트워크 연결 문제
```bash
# LoadBalancer IP 확인
kubectl get svc weather-mcp-service

# 포트 포워딩으로 로컬 테스트
kubectl port-forward svc/weather-mcp-service 8080:80

# 로컬에서 MCP 서버 직접 테스트
curl http://localhost:8080/sse
```

### 로그 모니터링

#### AKS 로그 확인
```bash
# 실시간 로그 확인
kubectl logs -f -l app=weather-mcp

# 특정 포드의 로그 확인
kubectl logs <pod-name> --previous

# 모든 컨테이너의 로그 확인
kubectl logs -l app=weather-mcp --all-containers=true
```

#### APIM 로그 확인
- Azure Portal → APIM → APIs → Settings → Diagnostic logs
- Application Insights 연동으로 상세 로그 확인
- Request/Response 추적 활성화

## 중요한 참고사항 및 주의점

### 🔍 실습 전 필수 확인사항
1. **Azure 구독 한도**: APIM Developer 계층은 구독당 1개만 생성 가능
2. **비용 고려**: APIM Developer 계층 시간당 요금 발생 (월 약 $50-100)
3. **리전 선택**: 모든 리소스를 동일한 리전(koreacentral)에 배치하여 네트워크 지연 최소화
4. **리소스 정리**: 실습 완료 후 반드시 리소스 그룹을 삭제하여 비용 절약
5. **권한 확인**: Azure 구독에서 리소스 생성 권한이 있는지 사전 확인

### ⚠️ 운영 환경 적용 시 주의사항
1. **Event Hub 로깅**: 현재 가이드에서는 주석 처리됨. 운영 환경에서는 실제 Event Hub 설정 필요
2. **SSL/TLS 인증서**: 프로덕션 환경에서는 자체 도메인과 SSL 인증서 사용 권장
3. **네트워크 보안**: 현재 LoadBalancer 타입은 공개 IP 할당. 운영 환경에서는 Private Link 고려
4. **환경변수 보안**: 운영 환경에서는 Azure Key Vault 사용 권장
5. **백업 전략**: 컨테이너 이미지 및 설정의 정기적인 백업 설정
6. **모니터링**: 종합적인 모니터링 및 경고 시스템 구축

### 🚀 성능 최적화 팁
1. **리소스 제한**: deployment.yaml의 CPU/메모리 제한값을 워크로드에 맞게 조정
2. **복제본 수**: 트래픽 패턴에 따라 replicas 수 조정
3. **캐싱**: APIM에서 응답 캐싱 정책 적용 고려
4. **Auto Scaling**: HPA(Horizontal Pod Autoscaler) 설정으로 자동 확장

### 🔐 추가 보안 권장사항
1. **네트워크 정책**: Kubernetes 네트워크 정책으로 Pod 간 통신 제한
2. **Service Mesh**: Istio 등을 활용한 마이크로서비스 보안
3. **이미지 스캔**: 컨테이너 이미지 보안 취약점 정기 스캔
4. **RBAC**: Kubernetes RBAC 설정으로 권한 관리

## 보안 강화 포인트

1. **API Key 인증**: APIM에서 구독 키를 통한 인증
2. **Rate Limiting**: API 호출 제한으로 남용 방지  
3. **네트워크 분리**: AKS 클러스터 내부 네트워크와 외부 분리
4. **모니터링**: APIM에서 API 호출 로그 및 메트릭 수집
5. **SSL/TLS**: HTTPS 통신 강제
6. **환경변수 보안**: 민감한 정보를 환경변수로 관리

## 추가 보안 설정 (선택사항)

### Azure Key Vault 연동
```bash
# Key Vault 생성
az keyvault create \
    --name kv-mcp-lab \
    --resource-group rg-mcp-lab \
    --location koreacentral

# 시크릿 저장
az keyvault secret set \
    --vault-name kv-mcp-lab \
    --name "apim-subscription-key" \
    --value "your-apim-subscription-key"

# AKS에서 Key Vault 접근 설정
az aks enable-addons \
    --addons azure-keyvault-secrets-provider \
    --name aks-mcp-cluster \
    --resource-group rg-mcp-lab
```

### JWT 토큰 인증 추가
```xml
<validate-jwt header-name="Authorization" failed-validation-httpcode="401">
    <openid-config url="https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration" />
    <required-claims>
        <claim name="aud" match="all">
            <value>your-api-audience</value>
        </claim>
    </required-claims>
</validate-jwt>
```

### 네트워크 보안 그룹 설정
```bash
# NSG 생성
az network nsg create \
    --resource-group rg-mcp-lab \
    --name nsg-mcp-lab

# 포트 8000 인바운드 규칙 추가 (APIM에서만)
az network nsg rule create \
    --resource-group rg-mcp-lab \
    --nsg-name nsg-mcp-lab \
    --name AllowAPIMInbound \
    --protocol Tcp \
    --direction Inbound \
    --priority 1000 \
    --source-address-prefixes "APIM-IP-RANGE" \
    --source-port-ranges "*" \
    --destination-address-prefixes "*" \
    --destination-port-ranges 8000 \
    --access Allow
```

### IP 화이트리스트 설정
```xml
<ip-filter action="allow">
    <address-range from="192.168.1.0" to="192.168.1.255" />
    <address>203.0.113.1</address>
</ip-filter>
```

## 정리 및 리소스 삭제

실습 완료 후 Azure 비용을 절약하기 위해 리소스를 정리합니다.

### 단계별 삭제 (선택적)
```bash
# 1. Kubernetes 리소스 삭제
kubectl delete -f deployment.yaml

# 2. APIM 삭제
az apim delete --name apim-mcp-lab --resource-group rg-mcp-lab --yes

# 3. AKS 클러스터 삭제
az aks delete --name aks-mcp-cluster --resource-group rg-mcp-lab --yes

# 4. ACR 삭제
az acr delete --name acrmcplab --resource-group rg-mcp-lab --yes
```

### 전체 리소스 그룹 삭제 (권장)
```bash
# ⚠️ 리소스 그룹 전체 삭제 (모든 리소스 포함, 복구 불가)
az group delete --name rg-mcp-lab --yes --no-wait
```

### 🔄 실습 진행 순서 요약 (FastMCP 기반)

이 가이드를 처음 진행하시는 분들을 위한 단계별 체크리스트입니다:

#### ✅ 사전 준비 (5-10분)
- [ ] Azure CLI 설치 및 로그인 (`az login`)
- [ ] Docker Desktop 설치 및 실행 확인
- [ ] kubectl 설치 확인
- [ ] Python 3.12+ 설치 확인
- [ ] 프로젝트 파일 구조 확인 (weather_sse_apim.py, mcp_client_sse_apim.py)

#### ✅ Azure 리소스 생성 (15-20분)
- [ ] 리소스 그룹 생성
- [ ] AKS 클러스터 생성 (시간 소요: 약 10분)
- [ ] Azure Container Registry(ACR) 생성
- [ ] APIM 인스턴스 생성 (시간 소요: 약 15분)

#### ✅ FastMCP 서버 배포 (10-15분)
- [ ] weather_sse_apim.py 기반 컨테이너 이미지 빌드 및 푸시
- [ ] Kubernetes 배포 (deployment.yaml)
- [ ] LoadBalancer 서비스 생성 및 IP 확인
- [ ] FastMCP 엔드포인트 확인 (GET /sse, POST /messages/{session_id})

#### ✅ APIM 설정 (10-15분)  
- [ ] FastMCP 호환 API 생성 (2개 엔드포인트만)
- [ ] SSE Connection 정책 적용 (apim-policy-sse-connection.xml)
- [ ] MCP Messages 정책 적용 (apim-policy-mcp-messages.xml)
- [ ] API 레벨 정책 적용 (apim-policy-api-level.xml)
- [ ] 구독 키 생성 및 확인

#### ✅ 클라이언트 설정 및 테스트 (5-10분)
- [ ] .env 파일 생성 (자동 또는 수동)
- [ ] Python 패키지 설치
- [ ] mcp_client_sse_apim.py 실행 및 테스트
- [ ] 재시도 로직 작동 확인

**⏱️ 총 소요시간: 약 45분-1시간**

**🚀 원클릭 배포: `bash azure-commands.sh` 실행으로 대부분 자동화 가능**

### 🏗️ 구현한 FastMCP 아키텍처

```
[mcp_client_sse_apim.py] → [APIM Gateway] → [AKS weather_sse_apim.py] → [NWS API]
         ↓                        ↓                      ↓
   [재시도 로직]              [인증/정책]           [FastMCP Protocol]
   [자동 어댑터 생성]         [로드밸런싱]          [SSE + POST 엔드포인트]
```

**핵심 구현사항:**
1. **weather_sse_apim.py**: FastMCP 기반 MCP 서버 - `/sse` (GET), `/messages/{session_id}` (POST) 지원
2. **mcp_client_sse_apim.py**: 재시도 로직과 디버그 출력이 포함된 APIM 호환 클라이언트  
3. **3개의 전용 APIM 정책**: SSE 연결, MCP 메시지, API 레벨 정책 분리
4. **자동화된 배포**: azure-commands.sh로 환경변수까지 자동 설정

### 🔧 학습한 기술 스택 (FastMCP 중심)
- **FastMCP 프로토콜**: SSE 기반 MCP 서버/클라이언트 구현
- **컨테이너화**: Docker를 통한 FastMCP 서버 패키징  
- **오케스트레이션**: Kubernetes를 활용한 MCP 서버 관리
- **API 게이트웨이**: Azure APIM을 통한 MCP 프로토콜 보안 및 라우팅
- **클라우드 네이티브**: Azure 관리형 서비스 + MCP 통합
- **에러 처리**: 세션 관리, 404 오류 해결, 재시도 로직 구현

### 🎨 실무 활용 가능한 MCP 패턴
이 FastMCP 아키텍처를 통해 다음과 같은 실무 시나리오에 적용할 수 있습니다:
- **엔터프라이즈 AI 에이전트 서비스**: 보안이 강화된 MCP 기반 AI 에이전트 플랫폼
- **마이크로서비스 MCP 아키텍처**: 각 마이크로서비스가 MCP 서버로 작동하는 분산 시스템
- **API 경제 + MCP**: MCP 프로토콜 기반 도구 API 제공 및 수익화 
- **하이브리드 MCP 네트워크**: 온프레미스 도구와 클라우드 AI 에이전트 연계

### 🔄 다음 단계 제안 (MCP 특화)

#### 기본 확장 (난이도: ⭐⭐)
1. **MCP 도구 확장**: 추가적인 날씨 API나 다른 도메인 도구 추가
2. **멀티 세션 관리**: 동시 다중 클라이언트 세션 지원 강화

#### 중급 확장 (난이도: ⭐⭐⭐)  
3. **MCP 프로토콜 모니터링**: 세션별, 도구별 사용량 및 성능 메트릭 수집
4. **MCP 보안 강화**: 세션별 권한 관리, 도구별 접근 제어
5. **MCP 멀티테넌트**: 다중 클라이언트를 위한 테넌트별 도구 세트 분리

#### 고급 확장 (난이도: ⭐⭐⭐⭐)
6. **MCP 서버 페더레이션**: 여러 MCP 서버 간 도구 공유 및 라우팅
7. **MCP 프로토콜 확장**: 커스텀 MCP 기능 및 프로토콜 확장 구현
8. **서비스 메시**: Istio 도입을 통한 고급 트래픽 관리 및 보안

## 🔧 문제해결 FAQ (FastMCP 기반)

### Q1: "MCP 서버 연결 실패" 오류가 발생합니다
**증상**: `Connection refused` 또는 `Server not reachable` 오류
**해결방법:**
```bash
# 1. AKS 포드 상태 확인
kubectl get pods -l app=weather-mcp
kubectl logs -l app=weather-mcp --tail=20

# 2. 서비스 상태 확인 
kubectl get svc weather-mcp-service
kubectl describe svc weather-mcp-service

# 3. 엔드포인트 확인 (포드가 서비스에 연결되었는지)
kubectl get endpoints weather-mcp-service

# 4. APIM 백엔드 URL 확인
az apim backend show --resource-group rg-mcp-lab --service-name apim-mcp-lab --backend-id mcp-backend
```

### Q2: "404 Not Found" on /messages/{session_id} POST 요청
**증상**: SSE 연결은 성공하지만 POST /messages/{session_id} 요청이 404 오류
**해결방법:**
```bash
# 1. 서버 로그에서 라우트 등록 확인
kubectl logs -l app=weather-mcp | grep -E "(routes|messages|session)"

# 2. 클라이언트에서 세션 ID 디버그 출력 확인
# mcp_client_sse_apim.py에서 DEBUG 메시지 확인

# 3. APIM 정책에서 URL 재작성 확인
# apim-policy-mcp-messages.xml에서 {session_id} 파라미터 전달 확인

# 4. 수동으로 엔드포인트 테스트
BACKEND_IP=$(kubectl get svc weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl -X GET "http://$BACKEND_IP:8000/sse" -v
```

### Q3: "어댑터 생성 실패" 재시도 후에도 계속 실패
**증상**: 클라이언트에서 MCP 어댑터 생성이 반복적으로 실패
**해결방법:**
```bash
# 1. FastMCP 서버의 /sse 엔드포인트 직접 테스트
BACKEND_IP=$(kubectl get svc weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl -X GET "http://$BACKEND_IP:8000/sse" \
  -H "Accept: text/event-stream" \
  -H "Cache-Control: no-cache" \
  -v

# 2. APIM을 통한 /sse 엔드포인트 테스트
APIM_URL=$(az apim show --resource-group rg-mcp-lab --name apim-mcp-lab --query "gatewayUrl" --output tsv)
SUBSCRIPTION_KEY=$(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)

curl -X GET "$APIM_URL/mcp/sse" \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY" \
  -H "Accept: text/event-stream" \
  -v

# 3. 환경변수 재확인
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
print('APIM Gateway URL:', os.getenv('APIM_GATEWAY_URL'))
print('Has Subscription Key:', bool(os.getenv('APIM_SUBSCRIPTION_KEY')))
"
```

### Q4: APIM에서 "401 Unauthorized" 오류가 발생합니다
**증상**: API 호출 시 인증 실패 메시지
**해결방법:**
```bash
# 1. 구독 키 확인 및 재생성
az apim subscription show \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --subscription-id mcp-subscription

# 2. 새 구독 키 생성 (필요시)
az apim subscription regenerate-keys \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --subscription-id mcp-subscription \
  --key-type primary

# 3. .env 파일 업데이트
NEW_KEY=$(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)
sed -i "s/APIM_SUBSCRIPTION_KEY=.*/APIM_SUBSCRIPTION_KEY=$NEW_KEY/" .env
```

### Q5: Azure OpenAI 연결 오류가 발생합니다
**증상**: OpenAI API 관련 인증 또는 연결 오류
**해결방법:**
1. Azure OpenAI 서비스가 배포되어 있고 활성화되어 있는지 확인
2. API 키와 엔드포인트가 올바른지 확인 (Azure Portal에서 재확인)
3. 배포 모델 이름이 정확한지 확인 (예: gpt-4o-mini, gpt-35-turbo)
4. API 버전이 지원되는 버전인지 확인

### Q6: 컨테이너 이미지 빌드 실패
**증상**: Docker 빌드 또는 푸시 과정에서 오류
**해결방법:**
1. Docker 서비스가 실행 중인지 확인: `docker --version`
2. ACR에 로그인되어 있는지 확인: `az acr login --name acrmcplab`
3. 이미지 태그 이름과 ACR 이름이 일치하는지 확인
4. 네트워크 연결 상태 확인 (방화벽 설정 등)

### Q5: Kubernetes 배포 실패
**증상**: `kubectl apply` 명령어 실행 시 오류
**해결방법:**
1. kubectl이 올바른 클러스터에 연결되어 있는지 확인: `kubectl config current-context`
2. AKS 클러스터 상태 확인: `az aks show --name aks-mcp-cluster --resource-group rg-mcp-lab`
3. ACR과 AKS가 연결되어 있는지 확인: `az aks check-acr --name aks-mcp-cluster --resource-group rg-mcp-lab --acr acrmcplab`
4. YAML 파일 문법 검증: `kubectl apply --dry-run=client -f deployment.yaml`

### Q6: "Rate limit exceeded" 오류가 발생합니다
**증상**: APIM에서 호출 제한 오류
**해결방법:**
1. APIM 정책에서 rate-limit 값 확인 및 조정
2. 필요시 구독 계층 업그레이드 고려
3. 클라이언트에서 재시도 로직 구현

### Q7: 비용이 예상보다 높게 나옵니다
**해결방법:**
1. Azure Cost Management에서 리소스별 비용 분석
2. 사용하지 않는 리소스 정리: `az group delete --name rg-mcp-lab --yes`
3. 개발 환경에서는 더 낮은 SKU 사용 고려
4. 자동 셧다운 정책 설정

---

## 📚 추가 리소스 및 참고자료

### 🔗 공식 문서
- [Azure Kubernetes Service (AKS) 문서](https://docs.microsoft.com/azure/aks/)
- [Azure API Management 문서](https://docs.microsoft.com/azure/api-management/)
- [Model Context Protocol (MCP) 사양](https://modelcontextprotocol.io/)
- [AutoGen 프레임워크 문서](https://microsoft.github.io/autogen/)

### 🛠️ 도구 및 유틸리티
- [Azure CLI 설치 가이드](https://docs.microsoft.com/cli/azure/install-azure-cli)
- [kubectl 설치 가이드](https://kubernetes.io/docs/tasks/tools/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Visual Studio Code Azure 확장팩](https://marketplace.visualstudio.com/items?itemName=ms-vscode.vscode-node-azure-pack)

### 🎯 실무 적용 사례
- **금융 서비스**: AI 기반 고객 상담 봇의 안전한 외부 API 연동
- **헬스케어**: 의료 데이터 처리 시 규정 준수를 위한 보안 게이트웨이
- **전자상거래**: 개인화 추천 시스템의 확장 가능한 마이크로서비스 아키텍처
- **제조업**: IoT 데이터 처리를 위한 엣지-클라우드 하이브리드 환경

### 💡 커뮤니티 및 지원
- [Azure 한국 사용자 그룹](https://www.facebook.com/groups/krazure/)
- [Kubernetes 한국 커뮤니티](https://kubernetes.slack.com/channels/korea-users)
- [Microsoft Learn - 무료 학습 경로](https://docs.microsoft.com/learn/)

---

## ✅ 실습 완료 체크리스트

실습을 성공적으로 완료했는지 확인하기 위한 최종 체크리스트입니다:

### 🎯 핵심 기능 검증
- [ ] AKS 클러스터에서 MCP 서버 정상 실행 (`kubectl get pods -l app=weather-mcp`)
- [ ] APIM를 통한 API 호출 성공 (Azure Portal Test 기능 사용)
- [ ] 로컬 클라이언트에서 날씨 정보 조회 성공
- [ ] 보안 정책(API Key, Rate Limiting) 정상 작동 확인

###  비용 관리
- [ ] 실습 완료 후 리소스 정리 완료 (`az group delete --name rg-mcp-lab`)
- [ ] Azure 비용 알림 설정 확인

**🎉 축하합니다!** 모든 항목을 완료하셨다면 AKS + APIM을 활용한 보안 강화 MCP 서버 구축 실습을 성공적으로 마무리하셨습니다.

---

**📝 라이선스**: 이 가이드는 MIT 라이선스 하에 제공되며, 교육 및 상업적 목적으로 자유롭게 사용할 수 있습니다.

**🙋‍♂️ 기여하기**: 이 가이드의 개선사항 제안이나 오류 신고는 GitHub Issues를 통해 언제든지 환영합니다.

**⚠️ 면책조항**: 이 가이드는 교육 목적으로 작성되었으며, 운영 환경에 적용하기 전에 보안 검토 및 성능 테스트를 반드시 수행하시기 바랍니다.
