# 🦒 세린이 어드민 웹

세린이 서비스의 관리자 대시보드입니다.

## 스택

- React 18 + TypeScript
- Vite
- SCSS
- Axios

## 기능

- JWT 기반 관리자 로그인
- 가입 신청 목록 (승인 / 거절)
- 승인된 유저 목록
- 유저 삭제
- 액션별 로딩 상태 + 에러 핸들링
- JWT 만료 시 자동 로그아웃

## 개발

```bash
npm install
npm run dev
```

## 빌드

```bash
npm run build
```

Docker로 실행 시 Nginx가 정적 파일을 서빙하고 `/api/`를 백엔드로 프록시합니다.
