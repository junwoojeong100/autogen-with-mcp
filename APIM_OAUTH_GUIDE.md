# 🚧 APIM에서 Microsoft Entra ID(OAuth 2.0) 인증 적용 가이드 (작성중)

> **필수 조건:** 본 가이드는 Azure API Management(APIM) 인스턴스가 최소 Developer(개발자) SKU 이상에서 동작합니다. 운영 환경에서는 Standard 이상을 권장합니다.

이 문서는 Azure API Management(APIM)에서 Microsoft Entra ID(구 Azure AD)를 이용한 OAuth 2.0 인증을 적용하는 방법을 안내합니다.

---

## 1. Microsoft Entra ID(구 Azure AD) 앱 등록

1. Azure Portal 접속 > Microsoft Entra ID > **앱 등록** > **새 등록**
2. 리디렉션 URI에 `https://{apim-name}.azure-api.net/signin` (APIM 개발자 포털 주소) 추가
   - (환경에 따라 `https://{apim-name}.developer.azure-api.net/signin`도 함께 등록 가능)
3. **클라이언트 ID**, **테넌트 ID** 확인, **클라이언트 시크릿** 생성

---

## 2. APIM에 OAuth 2.0 인증서버 등록

1. APIM 인스턴스 > **보안** > **OAuth 2.0 + OpenID Connect** > **+ 추가**
2. 아래 정보 입력
   - 이름, 클라이언트 ID, 클라이언트 시크릿
   - 권한 부여 엔드포인트: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/authorize`
   - 토큰 엔드포인트: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token`
   - 스코프: `api://{client-id}/.default` 또는 필요한 리소스 스코프

---

## 3. API 또는 Operation에 OAuth 2.0 인증 정책 적용

1. APIM에서 API > **정책 편집** > `<validate-jwt>` 또는 `<check-header>` 등으로 토큰 검증 정책 추가
2. 예시 정책:

```xml
<validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized"
    require-expiration-time="true" require-scheme="Bearer" output-token-variable-name="jwt">
  <openid-config url="https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration" />
  <audiences>
    <audience>api://{client-id}</audience>
  </audiences>
</validate-jwt>
```

---

## 4. (선택) 개발자 포털에서 OAuth 인증 버튼 노출

- API > **보안** > OAuth 2.0 서버 연결
- 개발자 포털에서 “OAuth 2.0 인증” 버튼이 자동 노출됨

---

## 참고 공식 문서
- [APIM OAuth 2.0 인증서버 등록](https://learn.microsoft.com/ko-kr/azure/api-management/api-management-howto-protect-backend-with-aad)
- [APIM JWT 검증 정책](https://learn.microsoft.com/ko-kr/azure/api-management/api-management-access-restriction-policies#ValidateJWT)
