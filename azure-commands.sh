# Azure CLI 명령어 모음 - FastMCP Weather SSE Server with APIM

# 1. 리소스 그룹 생성
az group create --name rg-mcp-lab --location koreacentral

# 2. AKS 클러스터 생성
az aks create \
    --resource-group rg-mcp-lab \
    --name aks-mcp-cluster \
    --node-count 1 \
    --node-vm-size Standard_DS4_v2 \
    --enable-addons monitoring \
    --generate-ssh-keys

# 3. kubectl 설정
az aks get-credentials --resource-group rg-mcp-lab --name aks-mcp-cluster

# 4. Azure Container Registry 생성
az acr create --resource-group rg-mcp-lab --name acrmcplab --sku Basic

# 5. ACR 로그인
az acr login --name acrmcplab

# 6. Docker 이미지 빌드 및 푸시 (weather_sse_apim.py 사용)
# 단일 플랫폼 빌드
docker build -t acrmcplab.azurecr.io/weather-mcp:latest .
docker push acrmcplab.azurecr.io/weather-mcp:latest

# 멀티 플랫폼 빌드 (권장)
# docker buildx create --name multiplatform-builder --use
# docker buildx build --platform linux/amd64,linux/arm64 \
#   -t acrmcplab.azurecr.io/weather-mcp:latest \
#   --push .

# 7. AKS에 ACR 연결
az aks update -n aks-mcp-cluster -g rg-mcp-lab --attach-acr acrmcplab

# 8. Kubernetes 배포
kubectl apply -f deployment.yaml

# 9. 서비스 상태 확인
kubectl get services weather-mcp-service

# 10. LoadBalancer IP 확인
kubectl get service weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# 11. APIM 생성
az apim create \
    --name apim-mcp-lab \
    --resource-group rg-mcp-lab \
    --publisher-name "MCP Lab" \
    --publisher-email "admin@example.com" \
    --sku-name Developer

# 12. 리소스 정리 (모든 실습 완료 후)
az group delete --name rg-mcp-lab --yes --no-wait

# === APIM API 설정 (weather_sse_apim.py의 FastMCP 엔드포인트 기반) ===

# 13. Backend 정의 (실제 LoadBalancer IP로 업데이트 필요)
# 먼저 kubectl get service weather-mcp-service로 IP 확인
BACKEND_IP=$(kubectl get service weather-mcp-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Backend IP: $BACKEND_IP"

az apim backend create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --backend-id mcp-backend \
    --url "http://$BACKEND_IP:8000" \
    --protocol http

# 14. API 정의 생성 (FastMCP 호환)
az apim api create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --path "/mcp" \
    --display-name "Weather MCP Server API (FastMCP)" \
    --service-url "http://$BACKEND_IP:8000"

# 15. SSE Connection 엔드포인트 (GET /sse) - MCP 프로토콜 초기화
az apim api operation create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id sse-connection \
    --method GET \
    --url-template "/sse" \
    --display-name "SSE Connection (MCP Initialization)"

# 16. MCP Messages 엔드포인트 (POST /messages/{session_id}) - 메시지 전송
az apim api operation create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id mcp-messages \
    --method POST \
    --url-template "/messages/{session_id}" \
    --display-name "MCP Messages (Protocol Communication)"

# 17. SSE Connection에 정책 적용
az apim api operation policy create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id sse-connection \
    --policy-format xml \
    --value @apim-policy-sse-connection.xml

# 18. MCP Messages에 정책 적용
az apim api operation policy create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --operation-id mcp-messages \
    --policy-format xml \
    --value @apim-policy-mcp-messages.xml

# 19. API 레벨 정책 적용 (CORS 및 공통 설정)
az apim api policy create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --policy-format xml \
    --value @apim-policy-api-level.xml

# 20. Subscription Key 생성
az apim subscription create \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --subscription-id mcp-subscription \
    --scope "/apis/weather-mcp-api" \
    --display-name "MCP API Subscription"

# 21. Subscription Key 조회
az apim subscription show \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --subscription-id mcp-subscription \
    --query "primaryKey" \
    --output tsv

# 22. API 엔드포인트 확인
echo "=== APIM API 엔드포인트 목록 ==="
az apim api operation list \
    --resource-group rg-mcp-lab \
    --service-name apim-mcp-lab \
    --api-id weather-mcp-api \
    --query "[].{Name:displayName, Method:method, Template:urlTemplate}" \
    --output table

# 23. APIM Gateway URL 확인
APIM_GATEWAY_URL=$(az apim show \
    --resource-group rg-mcp-lab \
    --name apim-mcp-lab \
    --query "gatewayUrl" \
    --output tsv)
echo "APIM Gateway URL: $APIM_GATEWAY_URL"

# === 배포 상태 확인 스크립트 ===

# 24. 전체 배포 상태 확인
echo "=== AKS 배포 상태 ==="
kubectl get pods -l app=weather-mcp
kubectl get services weather-mcp-service
kubectl logs -l app=weather-mcp --tail=20

echo "=== APIM 연결 테스트 ==="
echo "SSE Connection Test:"
curl -X GET "$APIM_GATEWAY_URL/mcp/sse" \
  -H "Ocp-Apim-Subscription-Key: $(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)" \
  -v

# === 환경 변수 내보내기 ===

# 25. 클라이언트용 환경 변수 설정
echo "=== 환경 변수 설정 ==="
echo "export APIM_GATEWAY_URL=\"$APIM_GATEWAY_URL\""
echo "export APIM_SUBSCRIPTION_KEY=\"$(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)\""
echo "export BACKEND_IP=\"$BACKEND_IP\""

# .env 파일 생성
cat > .env << EOF
APIM_GATEWAY_URL=$APIM_GATEWAY_URL
APIM_SUBSCRIPTION_KEY=$(az apim subscription show --resource-group rg-mcp-lab --service-name apim-mcp-lab --subscription-id mcp-subscription --query primaryKey --output tsv)
BACKEND_IP=$BACKEND_IP
EOF

echo ".env 파일이 생성되었습니다."
