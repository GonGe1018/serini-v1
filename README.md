<div align="center">

# 🦒 세린이
<br/>

<img src="./banner.png" width="800" />

<br/>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)](https://mysql.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose)




Discord DM으로 과제·퀴즈·동영상 마감 현황을 자동으로 알려드립니다.

</div>

---

## ✨ 주요 기능

### Discord 봇
| 명령어 | 설명 |
|--------|------|
| `/가입` | 서비스 가입 신청 (개인정보 동의 → 학번/비밀번호 입력) |
| `/상태` | 승인 상태 및 다음 알림 시간 확인 |
| `/업데이트` | 과제 현황 즉시 업데이트 |
| `/비밀번호` | 집현캠퍼스 비밀번호 변경 |
| `/탈퇴` | 서비스 탈퇴 및 데이터 삭제 |
| `/clear` | 봇 메시지 모두 삭제 |
| `/도움말` | 명령어 안내 |

- 📅 **매일 08:00 / 13:00 / 21:00** 자동 알림 (KST)
- 🔴 오늘 마감 과제 강조 표시
- 🔄 버튼 클릭으로 즉시 업데이트

---

## 🏗️ 아키텍처

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Discord 봇  │     │  FastAPI API │     │  React Admin │
│   (bot/)     │────▶│  (backend/) │◀────│   (admin/)   │
└──────┬───────┘     └──────┬──────┘     └──────────────┘
       │                    │
       │    ┌───────────────┘
       │    │
       ▼    ▼
  ┌─────────────┐     ┌─────────────┐
  │    MySQL     │     │   shared/   │
  │  (Docker)    │     │ DB·암호화·설정│
  └─────────────┘     └─────────────┘
```

### 디렉토리 구조

```
serini-service-v1/
├── bot/                    # Discord 봇
│   ├── main.py             # 슬래시 명령어 + 스케줄러
│   ├── registration.py     # 가입 플로우 + 비밀번호 변경
│   ├── report.py           # 리포트 발송 + DM 관리
│   ├── scraper.py          # ecampus 크롤링 (Playwright)
│   └── embeds.py           # Discord embed 빌더
├── backend/                # FastAPI 백엔드
│   └── app/
│       ├── api/users/      # CRUD + 라우터 + DTO
│       ├── core/           # 설정 + JWT 인증
│       └── db/             # DB 연결 + 의존성
├── admin/                  # React 어드민 웹
│   └── src/
│       ├── pages/          # 로그인 + 대시보드
│       ├── components/     # PrivateRoute
│       └── styles/         # SCSS
├── shared/                 # 공유 패키지
│   └── src/shared/         # DB 모델 + AES 암호화 + 설정
├── docker-compose.yml
└── .env.example
```

---

## 🔒 보안

- 비밀번호는 **AES-256-GCM + AAD**로 암호화 저장
- Docker 컨테이너 **non-root** 실행
- MySQL 포트 **localhost만 바인딩**
- Nginx **보안 헤더** 적용 (CSP, X-Frame-Options, HSTS)
- JWT 토큰 **만료 시간** 설정



<div align="center">


</div>
