
# APIM에서 Microsoft Entra ID(OAuth 2.0) 인증 적용 가이드

> **필수 조건:** 본 가이드는 Azure API Management(APIM) 인스턴스가 최소 Developer(개발자) SKU 이상에서 동작합니다. 운영 환경에서는 Standard 이상을 권장합니다.

이 문서는 Azure API Management(APIM)에서 Microsoft Entra ID(구 Azure AD)를 이용한 OAuth 2.0 인증을 적용하는 방법을 안내합니다.

---


## 1. Microsoft Entra ID(구 Azure AD) 앱 등록 및 API 권한(스코프) 설정

1. Azure Portal 접속 > Microsoft Entra ID > **앱 등록** > **새 등록**
2. **이름** 입력, **지원되는 계정 유형** 선택 (조직 내 단일 테넌트 권장)
3. **리디렉션 URI**는 개발자 포털(테스트 콘솔 등에서 OAuth 인증이 필요할 때만) 등록: 
   - 예시: `https://{apim-name}.azure-api.net/signin` 또는 `https://{apim-name}.developer.azure-api.net/signin`
   - 백엔드 API 보호만 목적이라면 리디렉션 URI는 생략 가능
4. 앱 등록 후 **애플리케이션(클라이언트) ID**와 **디렉터리(테넌트) ID**를 기록
5. **클라이언트 시크릿** 생성 (API 호출 시 필요)
6. **Expose an API(웹 API 노출)** 메뉴에서 Application ID URI(예: `api://{client-id}`)를 설정
7. **스코프 추가(Add a scope)**: 
   - Scope name, Admin consent display name/description 입력, Enabled 상태로 생성
   - API에서 필요한 모든 스코프를 추가하고, 각 스코프 이름을 기록
8. (v2 엔드포인트 사용 시) 앱 매니페스트에서 `accessTokenAcceptedVersion`을 2로 설정

---


## 2. APIM에 OAuth 2.0 인증서버 등록

1. APIM 인스턴스 > **보안** > **OAuth 2.0 + OpenID Connect** > **+ 추가**
2. 아래 정보 입력
   - 이름, 클라이언트 ID, 클라이언트 시크릿
   - 권한 부여 엔드포인트: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/authorize`
   - 토큰 엔드포인트: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token`
   - 스코프: `api://{client-id}/.default` 또는 필요한 리소스 스코프(위에서 기록한 스코프)
   - (참고) v1 엔드포인트 사용 시 URL에서 `/v2.0`을 제거

---


## 3. API 또는 Operation에 OAuth 2.0 인증 정책 적용

1. APIM에서 API(또는 Operation/Global) > **정책 편집** > `<validate-jwt>`로 토큰 검증 정책 추가
2. 예시 정책(권장):

```xml
<validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized. Access token is missing or invalid."
    require-expiration-time="true" require-scheme="Bearer" output-token-variable-name="jwt">
  <openid-config url="https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration" />
  <audiences>
    <audience>api://{client-id}</audience>
  </audiences>
  <issuers>
    <issuer>https://sts.windows.net/{tenant-id}/</issuer>
  </issuers>
  <required-claims>
    <claim name="aud">
      <value>api://{client-id}</value>
    </claim>
  </required-claims>
</validate-jwt>
```

> - v2 엔드포인트 사용 시 openid-config URL에 `/v2.0` 포함, v1은 제외
> - audience/issuer/claim 값은 앱 등록 시 정보와 일치해야 함
> - [validate-jwt 정책 공식 문서](https://learn.microsoft.com/ko-kr/azure/api-management/validate-jwt-policy) 참고
> - Microsoft Entra에서 발급된 토큰만 검증하려면 [validate-azure-ad-token 정책](https://learn.microsoft.com/ko-kr/azure/api-management/validate-azure-ad-token-policy)도 활용 가능

---


## 4. (선택) 개발자 포털에서 OAuth 인증 버튼 노출

- API > **보안** > OAuth 2.0 서버 연결
- 개발자 포털에서 “OAuth 2.0 인증” 버튼이 자동 노출됨
- [OAuth 2.0 인증 테스트 콘솔 연동 공식 가이드](https://learn.microsoft.com/ko-kr/azure/api-management/api-management-howto-oauth2) 참고

---


## 참고 공식 문서 및 추가 자료
- [APIM OAuth 2.0 인증서버 등록](https://learn.microsoft.com/ko-kr/azure/api-management/api-management-howto-protect-backend-with-aad)
- [APIM JWT 검증 정책](https://learn.microsoft.com/ko-kr/azure/api-management/validate-jwt-policy)
- [API 노출 및 스코프 등록 가이드](https://learn.microsoft.com/ko-kr/azure/active-directory/develop/quickstart-configure-app-expose-web-apis)
- [accessTokenAcceptedVersion 매니페스트 설정](https://learn.microsoft.com/ko-kr/azure/active-directory/develop/reference-app-manifest)
- [API Management 인증/인가 개념](https://learn.microsoft.com/ko-kr/azure/api-management/authentication-authorization-overview)

---

## 추가 고려사항 및 실전 팁

1. **JWT 패싱**
   - 백엔드 서비스에서도 토큰 검증이 필요하다면 `<set-header>` 정책을 이용해 Authorization 헤더를 그대로 전달합니다.
2. **다중 스코프 관리**
   - 여러 API를 보호할 경우 스코프별로 정책을 구분하고, 필요한 리소스에만 최소 권한을 부여하세요.
3. **토큰 발급 테스트**
   - [MSAL 라이브러리](https://learn.microsoft.com/azure/active-directory/develop/msal-overview)나 개발자 포털을 통해 토큰을 발급받고 Postman 등으로 호출해 보는 것을 권장합니다.
4. **로깅과 모니터링 강화**
   - APIM 진단 로그와 Application Insights를 활용하면 인증 실패 원인을 빠르게 파악할 수 있습니다.
5. **운영 환경 최적화**
   - 인증 서버와 APIM을 동일 지역에 배치하고 필요한 경우 프라이빗 네트워크 구성을 적용하여 지연을 최소화합니다.
