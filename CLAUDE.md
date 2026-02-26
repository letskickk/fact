# FACT - 실시간 유튜브 팩트체크 시스템

## 프로젝트 개요
유튜브 라이브 스트림 음성을 실시간으로 캡처 → 음성인식 → 팩트체크하는 시스템

## 기술 스택
- **Backend**: FastAPI + WebSocket (Python 3.12)
- **음성 캡처**: yt-dlp + ffmpeg + deno (JS runtime)
- **음성인식**: OpenAI Whisper API
- **팩트체크**: OpenAI GPT (분류: gpt-5-nano, 검증: gpt-5.2)
- **RAG**: pypdf + OpenAI text-embedding-3-small + 코사인 유사도
- **임베딩 캐시**: SQLite (data/embeddings.db)
- **Frontend**: Vanilla JS + CSS

## 프로젝트 구조
```
C:\fact/
├── app/
│   ├── api/
│   │   ├── routes.py        # REST API (/api/reference-files)
│   │   └── ws.py            # WebSocket 파이프라인
│   ├── capture/
│   │   └── stream.py        # YouTube 오디오 캡처 (yt-dlp + ffmpeg)
│   ├── checker/
│   │   ├── classifier.py    # 팩트체크 필요여부 분류
│   │   ├── prompts.py       # 검증 프롬프트 (3-source)
│   │   └── verifier.py      # 팩트 검증 (Reference/Web/LLM)
│   ├── models/
│   │   └── schemas.py       # Pydantic 모델 (FactCheckResult 등)
│   ├── rag/
│   │   ├── loader.py        # PDF/TXT 텍스트 추출 + 청킹
│   │   └── store.py         # 임베딩 벡터 스토어 + SQLite 캐시
│   ├── stt/
│   │   └── whisper.py       # Whisper API 호출
│   ├── config.py            # Settings (pydantic-settings)
│   └── main.py              # FastAPI 앱 + startup RAG 로딩
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   ├── facts/               # 참조 PDF 파일 (gitignore)
│   ├── youtube_cookies.txt  # YouTube 쿠키 (gitignore)
│   └── embeddings.db        # 임베딩 캐시 (gitignore)
├── scripts/
│   ├── setup.sh             # EC2 초기 설정
│   ├── start.sh             # 서버 시작 (백그라운드)
│   ├── stop.sh              # 서버 중지
│   ├── deploy.sh            # EC2에서 pull + 재시작
│   └── upload-data.bat      # 로컬 → EC2 데이터 업로드
├── deploy.bat               # 원클릭 배포 (로컬 → GitHub → EC2)
├── .env.example
├── .gitignore
└── pyproject.toml
```

## 파이프라인 흐름
1. **캡처**: yt-dlp로 HLS URL 추출 → ffmpeg로 10초 청크 녹음
2. **음성인식**: Whisper API로 텍스트 변환
3. **분류**: gpt-5-nano로 팩트체크 필요여부 판단
4. **RAG 검색**: 발언과 유사한 참조문서 청크 top_k=3 검색
5. **검증**: gpt-5.2 + web_search 도구로 3-source 검증
   - 우선순위: Reference(PDF) → Web Search → LLM Knowledge
   - source_type 필드로 어떤 소스 사용했는지 표시

## 핵심 설계 결정
- **ChromaDB 대신 인메모리 코사인 유사도**: Python 3.14 호환성 문제
- **pymupdf 대신 pypdf**: DLL 로드 실패 → 순수 Python 라이브러리
- **SQLite 임베딩 캐시**: 파일 hash(size+mtime) 기반 캐시 무효화
- **비동기 RAG 초기화**: asyncio.create_task로 서버 시작 차단 방지
- **web_search + JSON mode 비호환**: JSON mode 제거, 마크다운 펜스 스트리핑

## AWS 배포 정보
- **인스턴스**: t3.medium, Ubuntu 22.04
- **퍼블릭 IP**: 3.36.96.197
- **포트**: 8000
- **SSH**: `ssh -i "C:\fact\fact.pem" ubuntu@3.36.96.197`
- **GitHub**: https://github.com/letskickk/fact.git (branch: master)

## 배포 명령어
| 용도 | 명령어 |
|---|---|
| 코드 배포 (로컬) | `deploy.bat` 더블클릭 |
| 데이터 업로드 (로컬) | `scripts\upload-data.bat` 더블클릭 |
| SSH 접속 | `ssh -i "C:\fact\fact.pem" ubuntu@3.36.96.197` |
| 서버 시작 (EC2) | `bash scripts/start.sh` |
| 서버 중지 (EC2) | `bash scripts/stop.sh` |
| 로그 확인 (EC2) | `tail -f ~/fact/logs/server.log` |
| 전체 배포 (EC2) | `bash scripts/deploy.sh` |

## 로컬 개발
```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
# http://localhost:8001
```

## 주의사항
- `.env` 파일은 gitignore - 직접 생성 필요
- `data/facts/` PDF 파일은 gitignore - scp로 업로드 (`scripts\upload-data.bat`)
- YouTube 봇 차단 시 쿠키 갱신 필요 (Chrome 확장: Get cookies.txt LOCALLY)
- 임베딩 캐시는 첫 실행 시 자동 생성 (~30초)
- EC2 포트 8000 보안그룹 인바운드 규칙 필요
