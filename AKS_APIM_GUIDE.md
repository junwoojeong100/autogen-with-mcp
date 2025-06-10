
# AKS + APIM 기반 MCP 서버 실습 가이드

## 1. 사전 준비
- Azure CLI, Docker, kubectl, Python 3.12+ 설치
- Azure 구독 및 권한

## 2. 리소스 생성
### 생성되는 리소스
- **리소스 그룹**: 실습에 필요한 모든 리소스의 컨테이너 역할
- **AKS (Azure Kubernetes Service)**: 컨테이너 오케스트레이션 클러스터
- **ACR (Azure Container Registry)**: 컨테이너 이미지 저장소
- **APIM (API Management)**: API 게이트웨이 및 보안/정책 관리

리소스 그룹 생성 (모든 리소스의 컨테이너 역할)
```bash
az group create --name rg-mcp-lab --location koreacentral
```

AKS 클러스터 생성 (컨테이너 오케스트레이션)
```bash
az aks create --resource-group rg-mcp-lab --name aks-mcp-cluster --node-count 1 --enable-addons monitoring --generate-ssh-keys
```

컨테이너 레지스트리 생성 (이미지 저장)
```bash
az acr create --resource-group rg-mcp-lab --name acrmcplab --sku Basic
```

API Management 인스턴스 생성 (API 게이트웨이)
```bash
az apim create --resource-group rg-mcp-lab --name apim-mcp-lab --publisher-name "MCP Lab" --publisher-email "admin@example.com" --sku-name Developer
```

kubectl 인증 정보 가져오기 (AKS 제어)
```bash
az aks get-credentials --resource-group rg-mcp-lab --name aks-mcp-cluster
```

AKS와 ACR 연결 (이미지 풀링 권한 부여)
```bash
az aks update -n aks-mcp-cluster -g rg-mcp-lab --attach-acr acrmcplab
```

## 3. 애플리케이션 배포
컨테이너 이미지 빌드 (애플리케이션 패키징)
```bash
docker build -t acrmcplab.azurecr.io/weather-mcp:latest .
```

이미지 레지스트리에 푸시 (ACR로 업로드)
```bash
docker push acrmcplab.azurecr.io/weather-mcp:latest
```

Kubernetes에 배포 (애플리케이션 실행)
```bash
kubectl apply -f deployment.yaml
```

## 4. APIM 연동

### APIM에서 생성되는 오브젝트 및 정책
- **Backend**: 실제 MCP 서버(LoadBalancer IP)를 가리키는 백엔드 리소스
- **API**: 외부에 노출되는 MCP Weather API 엔드포인트 (경로, 이름, 백엔드 연결 포함)
- **Operation**: API 하위에 실제로 호출 가능한 엔드포인트(예: GET /sse, POST /messages/{session_id})를 등록. 각 Operation마다 메서드, 경로, 설명, 정책을 지정할 수 있음.
- **정책(Policy)**: API Gateway에서 인증, CORS, 라우팅, 보안 등 다양한 동작을 제어하는 XML 기반 규칙. 예시: SSE 연결 허용, 메시지 경로 매핑, API Key 인증 등. (apim-policy-sse-connection.xml 등 참고)

AKS 서비스의 LoadBalancer IP 조회 (APIM 백엔드 연결용)
```bash
BACKEND_IP=$(kubectl get service weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
```

APIM에 Backend 등록 (실제 MCP 서버 연결)
```bash
az apim backend create --resource-group rg-mcp-lab --service-name apim-mcp-lab --backend-id mcp-backend --url "http://$BACKEND_IP" --protocol http
```

APIM에 API 등록 (외부 노출용 엔드포인트 생성)
```bash
az apim api create --resource-group rg-mcp-lab --service-name apim-mcp-lab --api-id mcp-api --path "/mcp" --display-name "MCP Weather API" --service-url "http://$BACKEND_IP"
```

#### Operation 등록 예시 (필수 엔드포인트)
GET /sse 엔드포인트 등록 (SSE 연결용)
```bash
az apim api operation create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id mcp-api \
  --operation-id get-sse \
  --display-name "SSE Connect" \
  --method GET \
  --url-template "/sse" \
  --response-status 200
```

POST /messages/{session_id} 엔드포인트 등록 (메시지 전송용)
```bash
az apim api operation create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id mcp-api \
  --operation-id post-messages \
  --display-name "Send MCP Message" \
  --method POST \
  --url-template "/messages/{{session_id}}" \
  --response-status 200
```


## 5. 환경 변수 및 클라이언트 실행
- `.env` 파일에 Azure OpenAI, APIM, Backend 정보 입력
```bash
pip install -r requirements.txt
python3 mcp_client_sse_apim.py
```

## 6. 리소스 정리
```bash
az group delete --name rg-mcp-lab --yes --no-wait
```

---