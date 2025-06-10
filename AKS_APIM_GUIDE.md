# 🚀 AKS + APIM 기반 MCP 서버 실습 가이드

> **필수 조건:** 본 가이드는 Azure API Management(APIM) 인스턴스가 최소 Developer(개발자) SKU 이상에서 동작합니다. 운영 환경에서는 Standard 이상을 권장합니다.

```
[Client]
   |
   |  (API 호출, SSE 등)
   v
[Azure API Management (APIM)]
   |
   |  (API Gateway, 인증/정책)
   v
[AKS LoadBalancer Service]
   |
   |  (내부 트래픽)
   v
[AKS Cluster]
   |
   |  (Pod)
   v
[FastMCP 서버 컨테이너]
   |
   |  (이미지)
   v
[Azure Container Registry (ACR)]
```

## 1. 리소스 그룹 및 인프라 생성

- **리소스 그룹 생성**
```bash
az group create \
  --name rg-mcp-lab \
  --location koreacentral
```

- **AKS 클러스터 생성**
```bash
az aks create \
  --resource-group rg-mcp-lab \
  --name aks-mcp-cluster \
  --node-count 1 \
  --node-vm-size Standard_DS4_v2 \
  --enable-addons monitoring \
  --generate-ssh-keys
```

- **kubectl 인증 정보 가져오기**
```bash
az aks get-credentials \
  --resource-group rg-mcp-lab \
  --name aks-mcp-cluster
```

- **Azure Container Registry 생성**
```bash
az acr create \
  --resource-group rg-mcp-lab \
  --name acrmcplab \
  --sku Basic
```

- **AKS와 ACR 연결**
```bash
az aks update \
  --name aks-mcp-cluster \
  --resource-group rg-mcp-lab \
  --attach-acr acrmcplab
```


## 2. 애플리케이션 빌드 및 배포

- **ACR(Azure Container Registry) 로그인**
  - 로컬 Docker가 Azure Container Registry(acrmcplab)에 접근할 수 있도록 인증합니다.
```bash
az acr login --name acrmcplab
```

- **Docker 이미지 빌드 및 푸시**
  - weather_sse_apim.py를 포함한 서버 이미지를 빌드하고, ACR에 업로드합니다.
```bash
docker build -t acrmcplab.azurecr.io/weather-mcp:latest .

docker push acrmcplab.azurecr.io/weather-mcp:latest
```
  - (참고) 멀티플랫폼 빌드가 필요한 경우 아래 명령을 사용할 수 있습니다.
    ```bash
    # docker buildx create --name multiplatform-builder --use
    # docker buildx build \
    #   --platform linux/amd64,linux/arm64 \
    #   -t acrmcplab.azurecr.io/weather-mcp:latest \
    #   --push .
    ```

- **Kubernetes에 배포**
```bash
kubectl apply -f deployment.yaml
```

## 3. APIM 리소스 및 엔드포인트 구성

- **LoadBalancer IP & PORT 확인**
  - AKS에서 외부로 노출된 서비스의 포트와 IP를 확인합니다.
```bash
kubectl get service weather-mcp-service
```
  - 예시 출력:
  ```
  NAME                   TYPE           CLUSTER-IP    EXTERNAL-IP      PORT(S)        AGE
  weather-mcp-service    LoadBalancer   10.0.148.34   20.249.113.197   80:30125/TCP   2d3h
  ```

- **LoadBalancer IP & PORT 값을 환경변수로 저장**
```bash
BACKEND_IP=$(kubectl get service weather-mcp-service \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

BACKEND_PORT=$(kubectl get service weather-mcp-service \
  -o jsonpath='{.spec.ports[0].port}')
```

- **APIM 인스턴스 생성**
```bash
az apim create \
  --name apim-mcp-lab \
  --resource-group rg-mcp-lab \
  --publisher-name "MCP Lab" \
  --publisher-email "admin@example.com" \
  --sku-name Developer
```

- **APIM Backend 등록**
```bash
az apim backend create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --backend-id mcp-backend \
  --url "http://$BACKEND_IP:$BACKEND_PORT" \
  --protocol http
```

- **APIM API 등록**
```bash
az apim api create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --path "/mcp" \
  --display-name "Weather MCP Server API (FastMCP)" \
  --service-url "http://$BACKEND_IP:$BACKEND_PORT"
```

- **GET /sse Operation 등록**
```bash
az apim api operation create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --operation-id sse-connection \
  --method GET \
  --url-template "/sse" \
  --display-name "SSE Connection (MCP Initialization)"
```

- **POST /messages/{session_id} Operation 등록**
```bash
az apim api operation create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --operation-id mcp-messages \
  --method POST \
  --url-template "/messages/{session_id}" \
  --display-name "MCP Messages (Protocol Communication)"
```

- **Operation별 정책 적용**
```bash
az apim api operation policy create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --operation-id sse-connection \
  --policy-format xml \
  --value @apim-policy-sse-connection.xml
az apim api operation policy create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --operation-id mcp-messages \
  --policy-format xml \
  --value @apim-policy-mcp-messages.xml
```

- **API 레벨 정책 적용**
```bash
az apim api policy create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --policy-format xml \
  --value @apim-policy-api-level.xml
```

## 4. 배포 결과 확인 및 Subscription Key 발급

- **APIM Subscription Key 생성**
  - API 호출에 사용할 Subscription Key를 생성합니다.
```bash
az apim subscription create \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --subscription-id mcp-subscription \
  --scope "/apis/weather-mcp-api" \
  --display-name "MCP API Subscription"
```

- **Subscription Key 조회**
  - 발급된 Subscription Key(Primary Key)를 확인합니다.
```bash
az apim subscription show \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --subscription-id mcp-subscription \
  --query "primaryKey" \
  --output tsv
```

- **API 엔드포인트 목록 확인**
  - APIM에 등록된 API의 엔드포인트(Operation) 목록을 확인합니다.
```bash
az apim api operation list \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --api-id weather-mcp-api \
  --query "[].{Name:displayName, Method:method, Template:urlTemplate}" \
  --output table
```

- **APIM Gateway URL 확인**
  - APIM Gateway의 엔드포인트 URL을 확인합니다.
```bash
APIM_GATEWAY_URL=$(az apim show \
  --resource-group rg-mcp-lab \
  --name apim-mcp-lab \
  --query "gatewayUrl" \
  --output tsv)
echo "APIM Gateway URL: $APIM_GATEWAY_URL"
```

- **배포 상태 및 APIM 연결 테스트**
  - AKS와 APIM의 배포 상태를 확인하고, 실제로 API 호출이 가능한지 테스트합니다.
```bash
echo "=== AKS 배포 상태 ==="
kubectl get pods -l app=weather-mcp
kubectl get services weather-mcp-service
kubectl logs -l app=weather-mcp --tail=20

echo "=== APIM 연결 테스트 ==="
echo "SSE Connection Test:"
curl -X GET "$APIM_GATEWAY_URL/mcp/sse" \
  -H "Ocp-Apim-Subscription-Key: $(az apim subscription show \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --subscription-id mcp-subscription \
    --query primaryKey \
    --output tsv)" \
  -v
```

- **환경 변수 및 .env 파일 생성**
  - 클라이언트에서 사용할 환경 변수와 .env 파일을 생성합니다.
```bash
echo "export APIM_GATEWAY_URL=\"$APIM_GATEWAY_URL\""
echo "export APIM_SUBSCRIPTION_KEY=\"$(az apim subscription show \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --subscription-id mcp-subscription \
  --query primaryKey \
  --output tsv)\""
echo "export BACKEND_IP=\"$BACKEND_IP\""

cat > .env << EOF
APIM_GATEWAY_URL=$APIM_GATEWAY_URL
APIM_SUBSCRIPTION_KEY=$(az apim subscription show \
  --resource-group rg-mcp-lab \
  --service-name apim-mcp-lab \
  --subscription-id mcp-subscription \
  --query primaryKey \
  --output tsv)
BACKEND_IP=$BACKEND_IP
EOF
echo ".env 파일이 생성되었습니다."
```


## 5. 리소스 정리

- **실습 리소스 전체 삭제**
```bash
az group delete --name rg-mcp-lab --yes --no-wait
```

---

## 추가 고려사항 및 실전 팁

1. **네트워크와 보안**
   - 실습은 기본 오픈 환경을 기준으로 하지만, 실제 운영에서는 NSG(네트워크 보안 그룹)와 Ingress Controller(NGINX, AGIC 등) 설정을 꼭 검토하세요.
   - APIM과 AKS를 프라이빗 네트워크로 연결하려면 VNET 통합 및 프라이빗 엔드포인트 구성을 추가로 진행해야 합니다.

2. **APIM 정책 파일 이해**
   - `apim-policy-api-level.xml`, `apim-policy-mcp-messages.xml`, `apim-policy-sse-connection.xml` 파일의 역할과 주요 정책 내용을 미리 파악하세요.
   - 정책 파일에 주석을 달거나 별도 문서로 정리해두면 유지보수에 도움이 됩니다.

3. **인증 및 보안 강화**
   - 실습에서는 Subscription Key만 사용하지만, 실제 서비스에서는 OAuth2, JWT 등 추가 인증 방식을 적용하는 것이 안전합니다.
   - APIM에 Custom Domain과 HTTPS 인증서를 적용하는 방법도 미리 확인해 두세요.

4. **모니터링과 로깅**
   - Azure Monitor, Log Analytics, Application Insights 등과 연동하여 AKS 및 컨테이너 상태를 모니터링하면 장애 대응이 쉬워집니다.

5. **트러블슈팅(Troubleshooting)**
   - 이미지 Pull 실패, ACR 권한 문제, APIM Backend 연결 오류 등 자주 발생하는 문제와 해결법(FAQ)을 별도 정리해두면 실습과 운영 모두에 도움이 됩니다.

6. **기타 실전 팁**
   - 리소스 네이밍 규칙을 정해두면 여러 환경을 관리할 때 혼동을 줄일 수 있습니다.
   - 실습 후에는 반드시 리소스를 삭제하여 불필요한 비용이 발생하지 않도록 하세요.