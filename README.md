# Bookmark Intelligence

설치 페이지: [GitHub Pages](https://eggr0.github.io/obsidian-bookmark-intelligence/)

GitHub Pages는 `site/`의 정적 설치 안내를 `main` 브랜치에 반영할 때 자동 배포합니다. 저장소 관리자 화면에서 Pages의 source를 `GitHub Actions`로 한 번 활성화해야 공개 URL이 동작합니다.

Chrome과 Firefox 북마크를 로컬에서 감지하고, 중복을 정리한 뒤, 핵심 요약만 Obsidian Markdown 노트로 남기는 로컬 우선 북마크 정리 도구입니다.

Chrome과 Firefox에서 새 북마크를 감지하고 핵심 요약 노트를 Obsidian에 만드는 로컬 우선 도구입니다. 광고와 일일 사용량 제한 없이 Ollama 또는 사용자가 직접 연결한 AI API를 선택합니다.

무료 핵심은 `새 북마크 -> 본문/자막 추출 -> 요약 -> Markdown 노트 1개`입니다. 기존 북마크 대량 분석, 고급 중복 검토, 앱 상태 백업과 로그인 기반 동기화는 별도 유료 Pro 기능으로 제공합니다.

백업 Pro 기능은 Vault의 Markdown, 원문, 자막, API 키를 복사하지 않습니다. 앱 데이터의 SQLite 큐, 중복/재시도 상태, 활동 기록, 사용자 프롬프트만 검증된 ZIP으로 저장하며, 복원 시 동일 Vault인지 확인합니다.

## 목표

- Chrome과 Firefox에서 북마크 생성, 수정, 이동, 삭제 이벤트를 실시간 감지합니다.
- Chrome/Firefox 공용 WebExtension 코드베이스를 사용합니다.
- 기존 북마크 수천 개 분석은 Pro 기능입니다.
- 웹페이지 본문 추출은 `trafilatura`를 재사용합니다.
- YouTube는 `yt-dlp`로 메타데이터와 자막만 가져오며 영상 파일은 저장하지 않습니다.
- 요약은 기본적으로 로컬 Ollama 모델을 사용합니다.
- Obsidian에는 읽기 좋은 핵심 Markdown만 저장합니다.
- SQLite는 Obsidian을 대체하는 DB가 아니라, Vault 밖 앱 데이터 폴더에서 중복 방지와 재시도를 위한 내부 작업 큐로만 사용합니다.
- 처리 과정과 완료 결과를 앱 데이터 JSONL 로그, 콘솔, 브라우저 확장 알림으로 보여줍니다.

## 현재 기본 구성

이 프로젝트는 Vault 경로를 하드코딩하지 않고 `config.toml`에서 지정합니다. Windows D: 드라이브 Vault 예시는 다음과 같습니다.

```toml
[obsidian]
vault_path = "D:\\obsidian"
notes_subdir = "Bookmarks"
```

기본 결과 위치는 다음 구조입니다.

```text
D:\obsidian
  Bookmarks\
    요약된 북마크 노트.md
```

`Bookmarks`는 요약 노트가 저장되는 출력 폴더입니다. 큐, 이벤트와 활동 로그는 Vault 밖 OS별 앱 데이터 폴더에 저장됩니다.

## 전체 작동 방식

```text
Chrome / Firefox
  -> WebExtension
  -> Native Messaging
  -> 로컬 Python 에이전트
  -> URL 정규화와 중복 제거
  -> 앱 데이터의 SQLite 작업 큐
  -> Worker
  -> trafilatura 또는 yt-dlp
  -> 선택한 AI 공급자 요약
  -> Obsidian Markdown
```

브라우저 확장 프로그램은 북마크 이벤트를 감지해서 로컬 에이전트에 전달하는 역할만 합니다. 웹페이지를 긁거나 파일을 쓰거나 요약을 만들지 않습니다.

로컬 에이전트는 URL을 정규화하고 중복을 제거한 뒤, 처리할 작업을 큐에 넣습니다. Worker는 큐를 읽어 웹 본문이나 YouTube 자막을 가져오고, 설정된 AI 공급자로 요약한 뒤, Obsidian 노트를 만듭니다.

## 주요 기능

### 실시간 북마크 감지

확장 프로그램은 다음 브라우저 이벤트를 감지합니다.

- `bookmarks.onCreated`: 새 북마크 생성
- `bookmarks.onChanged`: 제목 또는 URL 수정
- `bookmarks.onMoved`: 폴더 이동
- `bookmarks.onRemoved`: 삭제

이 이벤트는 작은 JSON 메시지로 로컬 Native Host에 전달됩니다. Native Host는 이벤트를 `events.jsonl`에 남기고, 처리 대상 URL을 SQLite 작업 큐에 등록합니다.

### Chrome/Firefox 공용 확장 프로그램

소스 코드는 `extension/`에 하나만 유지합니다.

```text
extension/
  background.js
  popup.html
  popup.css
  popup.js
  manifest.chrome.json
  manifest.firefox.json
```

빌드 스크립트가 Chrome용, Firefox용 산출물을 각각 만듭니다. 팝업에는 Native Host 연결 상태를 확인하는 `Test connection` 버튼이 있습니다.

팝업에서 할 수 있는 동작은 다음과 같습니다.

- `Test connection`: Native Host와 Vault 연결 상태 확인
- 기존 북마크 대량 분석: Pro 기능으로 별도 제공
- `Get local agent`: GitHub Releases에서 로컬 agent/server 설치 파일 받기
- `Settings`: 확장 프로그램 설정 페이지 열기

여러 Chrome/Firefox 프로필을 사용하는 경우, 확장 프로그램 설치마다 `profile_id`를 로컬 storage에 생성해서 이벤트에 포함합니다. 따라서 같은 Windows 계정 안에서 Chrome 프로필을 여러 개 쓰더라도 `browser + profile_id + bookmark_id` 기준으로 북마크 항목이 분리됩니다.

### 스토어 설치와 로컬 agent 다운로드

Chrome Web Store와 Firefox Add-ons에서 검색 설치가 되려면 각 스토어 개발자 계정으로 패키지를 업로드하고 심사를 통과해야 합니다. 이 저장소는 제출 가능한 패키지를 생성합니다.

```powershell
python .\scripts\build_extensions.py
```

생성되는 제출 패키지:

```text
outputs\chrome-extension.zip
outputs\firefox-extension.xpi
```

확장 프로그램 자체는 스토어에서 설치할 수 있게 만들 수 있지만, 로컬 agent/server는 브라우저 스토어가 자동 설치해주지 않습니다. `Get local agent` 버튼은 최신 GitHub Release Windows 번들을 직접 다운로드하며, 사용자는 ZIP 안의 `install.ps1`을 한 번 실행해야 합니다.

스토어 제출 체크리스트와 listing 문안은 `STORE_SUBMISSION.md`에 정리되어 있습니다.

### 기존 북마크 수천 개 가져오기

실시간 이벤트와 별도로, 기존 Chrome/Firefox 북마크를 한 번에 가져올 수 있습니다.

기존 북마크 대량 분석은 Pro 기능입니다. Pro가 활성화된 설치에서는 SQLite 큐에 작업을 넣고, 중단 후에도 재시도 가능한 방식으로 순차 처리합니다.

고급 중복 정리는 자동 삭제가 아니라 여러 브라우저 프로필의 같은 canonical URL을 그룹으로 보여주는 Pro 보고서입니다.

```powershell
bookmark-agent --config .\config.toml duplicate-report --domain github.com
```

보고서에는 브라우저, 프로필, 북마크 ID, 제목, 폴더가 포함됩니다. 사용자가 확인한 뒤 브라우저에서 삭제해야 하며, 프로그램은 북마크를 임의로 삭제하거나 이동하지 않습니다.

대량 분석은 다음 명령으로 시작합니다.

```text
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --limit 5000
```

수천 개를 처리할 때도 원문과 자막은 Vault에 저장하지 않습니다. 각 URL은 하나의 요약 Markdown만 만들며, 큐와 재시도 상태는 Vault 밖 앱 데이터의 SQLite에 보관됩니다. 무료 설치에서 이 명령을 실행하면 Pro 기능 안내와 함께 종료됩니다.

필요한 북마크만 요약하려면 `summarize` 모드를 사용합니다.

```powershell
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --type youtube --limit 50
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --domain github.com --limit 25
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --folder AI --limit 100
```

수천 개를 처리하는 동안 확장 프로그램 알림과 `activity.jsonl`에 큐 등록, 추출, 요약, 저장, 실패, 재시도 상태가 기록됩니다. 로컬 Ollama 또는 사용자가 직접 연결한 API는 일일 사용량 제한 없이 동작하지만, 외부 API는 해당 공급자의 요금과 한도를 따릅니다.

기존 북마크 대량 분석은 확장 프로그램 설정 페이지의 `Preview existing bookmarks`로 먼저 수량을 확인한 뒤 `Analyze existing bookmarks`로 전체 큐에 넣을 수 있습니다. 이 기능은 Pro entitlement가 필요하며, 북마크를 이동하거나 삭제하지 않습니다.

### URL 정규화와 중복 제거

같은 글이 여러 북마크 폴더에 들어 있거나, 추적 파라미터만 다른 URL로 저장되어 있을 수 있습니다.

예를 들어 다음 URL은 같은 대상으로 취급됩니다.

```text
https://example.com/article?utm_source=newsletter#comments
https://example.com/article
```

처리 과정에서는 다음 정리를 합니다.

- 스킴과 호스트 소문자화
- `utm_*`, `fbclid`, `gclid`, `msclkid` 같은 추적 파라미터 제거
- URL fragment 제거
- 쿼리 파라미터 정렬
- canonical URL 기준 중복 제거

최종 노트는 canonical URL 기준으로 하나만 만들고, 여러 브라우저 북마크가 같은 리소스를 가리킬 수 있습니다.

### 작업 큐와 처리 상태

북마크가 감지되거나 기존 북마크 import의 `summarize` 모드로 선택되면, 바로 요약을 시작하는 것이 아니라 먼저 SQLite 작업 큐에 들어갑니다.

큐에 들어가는 시점은 다음과 같습니다.

```text
실시간 브라우저 북마크 생성/수정 이벤트
  -> Native Host 수신
  -> canonical URL 생성
  -> 중복 URL 확인
  -> resources 테이블에 pending 작업 등록

기존 북마크 import summarize 모드
  -> Chrome/Firefox 북마크 파일 스캔
  -> 필터 적용
  -> canonical URL 생성
  -> 중복 URL 확인
  -> resources 테이블에 pending 작업 등록
```

worker는 이 큐에서 `pending` 상태인 작업을 가져와 처리합니다.

처리 상태는 다음처럼 바뀝니다.

```text
pending
  -> processing
  -> succeeded

pending
  -> processing
  -> failed
  -> retry time 도달
  -> processing
  -> succeeded 또는 failed
```

SQLite에 남는 주요 상태는 다음과 같습니다.

- `process_status`: `pending`, `processing`, `succeeded`, `failed`
- `retry_count`: 실패 횟수
- `next_retry_at`: 다음 재시도 가능 시간
- `last_error`: 마지막 실패 이유
- `markdown_path`: 성공 시 생성된 Obsidian 노트 경로

즉 브라우저 확장 프로그램은 북마크 이벤트를 놓치지 않게 큐에 넣는 역할이고, 실제 본문 추출과 요약은 worker가 순차적으로 처리합니다.

### 삭제, 재추가, 이름 변경 동작

이 시스템은 브라우저 북마크 항목과 요약 대상 리소스를 분리해서 봅니다.

```text
bookmarks 테이블
  -> 브라우저별 북마크 항목 추적
  -> browser + profile_id + bookmark_id 기준
  -> title, parent_id, status 기록

resources 테이블
  -> 실제 요약 대상 URL 추적
  -> canonical_url 기준
  -> process_status, retry_count, markdown_path 기록
```

같은 URL을 지웠다가 다시 북마크하면 다음처럼 동작합니다.

```text
북마크 삭제
  -> bookmark_events에 removed 이벤트 기록
  -> bookmarks 상태를 removed로 갱신
  -> 기존 Obsidian 요약 노트는 삭제하지 않음
  -> resources의 성공 기록도 유지

같은 URL을 다시 북마크
  -> 새 bookmark_id 또는 기존 bookmark_id가 active로 기록
  -> canonical_url 기준으로 resources 중복 확인
  -> 이미 succeeded 상태면 새 요약 노트를 만들지 않음
  -> failed/pending 상태였으면 다시 처리 대상으로 둘 수 있음
```

즉 같은 글을 지웠다 다시 저장해도 Obsidian 노트가 계속 늘어나지 않습니다. 이미 요약된 canonical URL이면 기존 결과를 재사용하는 쪽이 기본값입니다.

북마크 이름만 변경하면 다음처럼 동작합니다.

```text
북마크 제목 변경
  -> bookmark_events에 changed 이벤트 기록
  -> bookmarks.title 갱신
  -> resources.title도 최신 제목으로 갱신 시도
  -> 이미 succeeded 상태인 리소스는 자동 재요약하지 않음
  -> 기존 Markdown 파일명도 자동 변경하지 않음
```

이름 변경만으로 원문 내용이 바뀐 것은 아니므로, 기본값은 재요약하지 않는 것입니다. 아직 처리 전인 `pending` 또는 실패 후 재시도 대상인 리소스라면, 나중에 worker가 처리할 때 최신 제목이 노트 제목으로 쓰일 수 있습니다.

URL 자체가 바뀌면 이야기가 다릅니다.

```text
북마크 URL 변경
  -> 새 canonical_url 계산
  -> 새 URL이 기존에 처리된 적 없으면 pending 리소스로 등록
  -> 기존 URL의 요약 노트는 자동 삭제하지 않음
```

자동 삭제와 자동 파일명 변경을 하지 않는 이유는 Obsidian 노트가 사용자가 읽고 수정할 수 있는 최종 지식 파일이기 때문입니다. 브라우저 북마크 조작만으로 이미 만든 노트를 지우거나 이름을 바꾸면 사용자가 추가한 메모를 잃을 수 있습니다.

### 웹페이지 요약 과정

일반 웹페이지는 다음 순서로 처리됩니다.

```text
북마크 URL
  -> canonical URL 생성
  -> 이미 처리한 URL인지 확인
  -> trafilatura로 HTML 다운로드 및 본문 추출
  -> 제목, 저자, 게시일, 본문 일부 정리
  -> 선택한 AI 공급자에 요약 요청
  -> Obsidian Markdown 저장
```

본문 전체를 Obsidian에 저장하지 않습니다. 핵심 요약과 원본 링크만 남깁니다.

### YouTube 요약 과정

YouTube URL은 영상 파일을 받지 않고 `yt-dlp`로 메타데이터와 자막만 가져옵니다.

```text
YouTube URL
  -> yt-dlp 메타데이터 조회
  -> 제목, 채널, 길이, 설명 추출
  -> 사용 가능한 자막 또는 자동 자막 조회
  -> 선택한 AI 공급자에 요약 요청
  -> Obsidian Markdown 저장
```

자막을 가져올 수 없거나 YouTube 쪽에서 일시적으로 막혀도, 그 자체만으로 작업 전체를 실패 처리하지는 않습니다. worker는 가능한 경우 제목, 채널, 길이, 설명 같은 메타데이터를 사용해서 요약을 계속 진행합니다. 영상 자체는 저장하지 않습니다.

자막 처리 방식은 다음과 같습니다.

```text
yt-dlp 메타데이터 조회 성공
  -> 기입 자막 확인
  -> 자동 생성 자막 확인
  -> ko, en 우선으로 VTT 자막 다운로드 시도
  -> 자막 성공: transcript 기반 요약
  -> 자막 실패: metadata + description 기반 요약으로 후퇴
```

자막만 실패한 경우 요약 입력에는 다음 의미의 문장이 들어갑니다.

```text
Transcript unavailable; summarize from metadata and description.
```

이 경우에도 Obsidian 노트는 생성될 수 있습니다. 다만 실제 발화 내용이 빠지므로 자막 기반 요약보다 품질이 낮을 수 있습니다.

작업 전체가 실패로 기록되는 경우는 별도입니다.

- `yt-dlp`가 영상 정보 자체를 가져오지 못한 경우
- YouTube 접근 오류가 메타데이터 조회 단계에서 발생한 경우
- Ollama가 꺼져 있거나 설정된 모델이 없는 경우
- Markdown 저장에 실패한 경우

이때는 `processing_failed` 활동 로그가 남고, SQLite 큐에 `retry_count`, `next_retry_at`, `last_error`가 기록됩니다.

### AI 공급자

기본 공급자는 Ollama입니다. 외부 API를 선택하면 입력 본문이 해당 공급자로 전송됩니다.

```toml
[summarizer]
provider = "ollama"
model = "qwen2.5:7b"
base_url = "http://localhost:11434"
api_key_env = ""
timeout_seconds = 120
```

Ollama가 꺼져 있거나 모델이 없으면 작업은 실패로 기록되고 재시도 대상이 됩니다. OpenAI 호환 API는 `provider = "openai"`, Gemini는 `provider = "gemini"`, Anthropic은 `provider = "anthropic"`로 선택할 수 있습니다. 유료 hosted gateway를 사용할 때는 `provider = "hosted"`를 선택합니다.

```toml
[summarizer]
provider = "openai"
base_url = "https://api.openai.com/v1"
model = "gpt-5.4-nano"
api_key_env = "OPENAI_API_KEY"
timeout_seconds = 120
```

API 키는 환경 변수로만 읽으며 SQLite, 로그, Vault, Markdown에 저장하지 않습니다.

`hosted`는 `[entitlements]`의 account ID와 bearer token을 사용해 중앙 gateway를 호출하며 성공한 요약 1건당 hosted credit 1개를 차감합니다. gateway 운영자는 upstream OpenAI-compatible API 키를 환경 변수에만 보관합니다.

### Obsidian plugin

The release includes `outputs/obsidian-bookmark-intelligence-plugin.zip`. Copy `manifest.json`, `main.js`, and `README.md` from the archive into `<vault>/.obsidian/plugins/bookmark-intelligence/`, then enable **Bookmark Intelligence** in Obsidian. The plugin is a desktop-only status and control surface: it reads the local activity log and can run the configured agent once. The browser extension and Native Messaging agent are still required for real-time bookmark capture.

The plugin does not create a Vault index or move notes. Local Ollama summarization still requires hardware capable of running the selected model.

### Pro entitlement

결제 서비스가 준비되면 `[entitlements]`에 entitlement endpoint와 account ID를 지정하고 다음 명령으로 구독 상태를 갱신합니다.

```powershell
$env:BOOKMARK_INTELLIGENCE_ACCESS_TOKEN = "사용자 액세스 토큰"
bookmark-agent --config .\config.toml refresh-entitlement
```

agent는 plan, 기능 목록, 만료 시각만 앱 데이터에 캐시하며 액세스 토큰은 저장하지 않습니다. entitlement 서버가 설정된 경우 Pro 기능 확인 시 15분보다 오래된 캐시만 자동 갱신하고, 서버가 일시적으로 unavailable이면 기존 캐시로 동작합니다. 만료되거나 비활성화된 entitlement는 Free로 처리됩니다. 개발 테스트에서만 `BOOKMARK_INTELLIGENCE_DEV_PRO=1` 환경 변수를 일시적으로 사용할 수 있으며, 설정 파일의 값으로는 Pro 기능을 활성화할 수 없습니다.

### 후원 링크

확장 프로그램 설정 페이지는 `config.toml`의 `[support]`에 실제 URL이 입력된 채널만 표시합니다. GitHub Sponsors, Polar, Ko-fi, Buy Me a Coffee, Patreon, PayPal, Toss, 사용자 지정 링크를 지원합니다. 계정이 없는 채널은 빈 값으로 두며 가짜 링크를 표시하지 않습니다.

```toml
[support]
github = "https://github.com/sponsors/your-account"
polar = ""
ko_fi = ""
buy_me_a_coffee = ""
patreon = ""
paypal = ""
toss = ""
custom = ""
```

Ollama 모델은 `/api/generate` 호출 시 Ollama가 로컬에서 로드합니다. 이미 메모리에 올라와 있으면 바로 응답하고, 아직 로드되지 않았다면 첫 요청에서 로드 시간이 걸릴 수 있습니다.

GPU나 모델 로드 관련 상황은 다음처럼 처리됩니다.

```text
Ollama 실행 중 + 모델 설치됨 + 로드 성공
  -> 정상 요약

Ollama 실행 중 + 모델 설치됨 + GPU 사용 불가
  -> Ollama가 CPU fallback을 할 수 있으면 느리게라도 요약
  -> Ollama가 오류를 반환하면 worker는 failed로 기록

Ollama 실행 중 + 모델 없음
  -> /api/generate 실패
  -> worker는 failed로 기록
  -> retry_count 증가
  -> next_retry_at 이후 재시도

Ollama 꺼짐 또는 응답 없음
  -> 요청 실패 또는 timeout
  -> worker는 failed로 기록
  -> retry_count 증가
  -> next_retry_at 이후 재시도
```

이 프로젝트는 GPU 상태를 직접 제어하지 않습니다. GPU 사용 여부와 CPU fallback 여부는 Ollama 런타임이 결정합니다. agent는 Ollama가 성공 응답을 주면 요약을 저장하고, 오류나 timeout을 주면 실패로 기록하고 재시도합니다.

설정된 모델이 설치되어 있는지는 `doctor` 명령에서 확인합니다.

```powershell
bookmark-agent --config .\config.toml doctor
```

Pro 앱 상태 백업/복원:

```powershell
bookmark-agent --config .\config.toml backup --output .\bookmark-intelligence-state.zip
bookmark-agent --config .\config.toml restore --input .\bookmark-intelligence-state.zip
```

무료 설치에서는 두 명령이 Pro 안내와 함께 종료됩니다. 복원 중에는 worker를 중지해야 하며, 복원 대상 Vault와 백업의 Vault 식별자가 다르면 거부됩니다.

결제·로그인 entitlement 서버의 최소 구현은 `server/billing_service.py`에 있습니다. 계정 등록/로그인, 선택적 이메일 인증·비밀번호 재설정, bearer token, 결제 주문 매핑, Polar Standard Webhooks 검증, Toss 결제 API 재조회, 중복 이벤트 차단, 기본 요청 rate limit을 제공합니다. 공개 운영에는 여전히 HTTPS reverse proxy, 분산 rate limiting, managed database, secret manager, 메일 발송 보안과 abuse monitoring이 필요합니다. 상세 실행법은 [`server/README.md`](server/README.md)를 참조합니다.

로그인 후 발급된 access token은 확장 설정의 Pro 연결에 입력하지 않습니다. 설정 페이지에는 entitlement endpoint, account ID, token 환경 변수 이름만 저장하고, token 값은 worker를 시작하는 사용자 환경 변수에 둡니다. 자세한 PowerShell 로그인 예시는 [`server/README.md`](server/README.md)에 있습니다.

모델이 없다면 먼저 내려받습니다.

```powershell
ollama pull qwen2.5:7b
```

### 작업 진행 알림

worker는 처리 과정을 다음 위치에 기록합니다.

```text
%LOCALAPPDATA%\Bookmark Intelligence\<vault-id>\activity.jsonl
```

기록되는 단계는 다음과 같습니다.

```text
worker_started
batch_started
processing_started
extraction_started
extraction_completed
summarizer_started
summarizer_completed
processing_succeeded
processing_failed
```

특히 `summarizer_started`와 `summarizer_completed`에는 사용한 공급자와 모델명이 들어갑니다.

AI 호출에 실패하면 `processing_failed`에 실패 이유가 남습니다. 상태는 Vault 밖 앱 데이터의 `activity.jsonl`과 브라우저 알림에서 확인할 수 있습니다.

예시:

```markdown
## 2026-08-11T04:20:00Z - summarizer_started

- Title: Ollama summary started
- Message: Calling ollama model qwen2.5:7b.
- URL: https://example.com/article
- Provider: ollama
- Model: qwen2.5:7b
```

현재 기본값은 Windows 데스크톱 알림 대신 브라우저 확장 프로그램 알림을 사용하는 것입니다. worker는 앱 데이터의 `activity.jsonl`에 상태를 남기고, 확장 프로그램이 이를 읽어 브라우저 알림을 띄웁니다.

agent 쪽 활동 기록 설정은 `config.toml`에서 조정합니다.

```toml
[notifications]
enabled = true
desktop = false
activity_log = true
activity_note = false
print_to_console = true
notify_on_start = false
notify_on_success = true
notify_on_failure = true
```

활동 노트는 생성하지 않습니다. 기본 설정은 `desktop = false`이며 과정은 브라우저 알림과 콘솔에서 확인합니다.

브라우저 확장 알림은 확장 프로그램 설정 페이지에서 조정합니다.

### 확장 프로그램 설정 페이지

확장 프로그램의 `Settings` 버튼 또는 브라우저 확장 관리 화면의 옵션 페이지에서 다음 설정을 변경할 수 있습니다.

- Local agent download URL
- 브라우저 알림 사용 여부
- 큐 등록 알림 사용 여부
- Obsidian 요약 저장 완료 알림 사용 여부
- 처리 실패 알림 사용 여부
- worker 활동 로그 polling 사용 여부
- polling 주기
- 요약 입력 프롬프트

확장 알림과 다운로드 URL 설정은 브라우저 extension storage에 저장됩니다. 요약 입력 프롬프트, AI 연결, Pro entitlement 연결 설정은 Vault 밖 앱 데이터 폴더에 저장됩니다. 설정 페이지에서 Ollama, OpenAI 호환 API, Gemini, Anthropic, hosted gateway의 공급자·모델·endpoint와 API 키 환경 변수 이름, entitlement endpoint·account ID·access token 환경 변수 이름을 바꿀 수 있습니다. API 키와 access token 값 자체는 저장하지 않습니다. 프롬프트에서는 `{{title}}`, `{{url}}`, `{{source_text}}` 변수를 사용할 수 있습니다.

### 로컬 모델 하드웨어 요구사항

이 프로젝트는 요약을 클라우드 AI 서비스가 아니라 사용자의 로컬 Ollama 모델로 처리합니다. 따라서 선택한 모델을 실행할 수 있는 하드웨어가 필요합니다.

기본 설정은 사용 가능한 경우 `qwen2.5:7b`를 사용합니다. 더 큰 모델은 더 많은 RAM/VRAM과 시간이 필요하고, GPU를 사용할 수 없으면 Ollama가 CPU fallback으로 느리게 처리하거나 모델 로드에 실패할 수 있습니다. 모델 로드 실패, Ollama 종료, timeout은 worker에서 `processing_failed`로 기록되고 재시도 대상이 됩니다.

낮은 사양의 컴퓨터에서는 더 작은 Ollama 모델을 설정하는 것이 좋습니다.

## 왜 SQLite를 쓰는가

Obsidian은 최종 지식 저장소입니다. SQLite는 사용자가 읽는 DB가 아니라 내부 작업표입니다.

SQLite가 필요한 이유는 다음 상태를 안정적으로 기억하기 위해서입니다.

- 이 URL을 이미 처리했는가
- 같은 canonical URL이 몇 번 들어왔는가
- 처리 중 실패했는가
- 몇 번 재시도했는가
- 다음 재시도 시간은 언제인가
- 어떤 Markdown 파일로 저장되었는가
- 삭제된 북마크와 활성 북마크를 어떻게 구분할 것인가

Markdown만으로도 목록은 만들 수 있지만, 실패 재시도와 중복 방지에는 비효율적입니다. 그래서 SQLite는 프로그램의 작업 큐이고, Obsidian Markdown은 사람이 읽는 최종 결과입니다.

## 저장되는 Markdown 예시

```markdown
---
source_url: "https://example.com/article"
canonical_url: "https://example.com/article"
resource_type: "webpage"
processed_at: "2026-08-11T03:30:00Z"
---

# Example Article

## Summary

짧은 핵심 요약입니다.

## Key Points

- 중요한 포인트 1
- 중요한 포인트 2
- 중요한 포인트 3

```

## 설치

### 업데이트

Git checkout으로 설치한 사용자는 기존 `config.toml`과 Vault를 유지한 채 다음 명령으로 최신 코드를 받고 다시 빌드할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update.ps1 -VaultPath D:\obsidian -SkipOpen
```

Linux/macOS:

```bash
SKIP_OPEN=1 ./scripts/update.sh
```

GitHub Release ZIP으로 설치한 경우에는 Git checkout이 필요 없는 updater를 사용합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-release.ps1 -VaultPath D:\obsidian -SkipOpen
```

```bash
VAULT_PATH="$HOME/Obsidian" SKIP_OPEN=1 ./scripts/update-release.sh
```

이 updater는 GitHub의 `latest` Windows/source Release asset과 `SHA256SUMS.txt`를 내려받아 SHA-256을 검증한 뒤 현재 설치 디렉터리에 반영하고 설치합니다. 따라서 Native Messaging manifest가 임시 폴더를 가리키지 않으며, 기존 `config.toml`과 Vault Markdown도 보존됩니다. 브라우저 스토어 확장은 각 스토어의 심사·게시 후 스토어 자동 업데이트 정책을 따릅니다. 설치 중 실행 중인 worker는 기존 프로세스가 계속 실행될 수 있으므로, 업데이트 후 worker를 한 번 재시작하는 것이 권장됩니다.

태그가 GitHub Release로 배포되면 Release에는 Chrome ZIP, Firefox XPI, Windows Native Host, 소스 번들이 함께 올라갑니다. 브라우저 스토어 자동 업데이트는 각 스토어 심사와 게시가 완료된 뒤 스토어 정책에 따라 동작합니다.

### 빠른 설치

Windows에서는 `install.ps1`로 대부분의 설치 과정을 한 번에 실행할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -VaultPath D:\obsidian
```

Windows Release ZIP에는 Native Messaging 실행 파일이 함께 들어 있으므로 기본 설치는 이를 그대로 사용합니다. 소스에서 Native Host를 다시 빌드해야 할 때만 `-RebuildNativeHost`를 추가합니다.

이 스크립트가 처리하는 일은 다음과 같습니다.

- Python 가상환경 생성 또는 재사용
- Python 의존성 설치
- `config.toml` 생성 또는 기존 설정 재사용
- SQLite 초기화와 마이그레이션
- Chrome/Firefox 확장 산출물 빌드
- Native Host 실행 파일 빌드
- Chrome/Firefox Native Messaging Host 등록
- worker Windows 시작 프로그램 등록
- `doctor` 실행
- 확장 프로그램 설치 페이지 열기

이미 `config.toml`이 있으면 기본적으로 덮어쓰지 않습니다. Vault 경로를 강제로 다시 쓰려면 `-ForceConfig`를 붙입니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -VaultPath D:\obsidian -ForceConfig
```

브라우저 설치 페이지를 열지 않으려면 `-SkipOpen`, 현재 세션에서 worker를 바로 시작하지 않으려면 `-SkipStartWorker`를 사용할 수 있습니다.

Linux/mac에서는 `install.sh`를 사용할 수 있습니다.

```bash
chmod +x ./install.sh
./install.sh --vault-path "$HOME/Obsidian"
```

이 스크립트는 Python 가상환경과 의존성을 준비하고, 확장 산출물을 만들고, Chrome/Firefox Native Messaging manifest를 사용자별 위치에 설치합니다.

기본 Native Messaging manifest 설치 위치:

```text
Linux Chrome:  ~/.config/google-chrome/NativeMessagingHosts/obsidian_bookmark_agent.json
Linux Firefox: ~/.mozilla/native-messaging-hosts/obsidian_bookmark_agent.json
mac Chrome:    ~/Library/Application Support/Google/Chrome/NativeMessagingHosts/obsidian_bookmark_agent.json
mac Firefox:   ~/Library/Application Support/Mozilla/NativeMessagingHosts/obsidian_bookmark_agent.json
```

worker 자동 실행:

- Linux: user systemd가 있으면 user service를 등록하고, 없으면 XDG autostart 파일을 만듭니다.
- macOS: LaunchAgent를 등록합니다.

Unix 계열에서도 확장 프로그램 자체는 브라우저에서 한 번 수동으로 로드해야 합니다.

### 수동 설치

### 1. Python 환경 준비

Windows PowerShell에서 프로젝트 폴더로 이동한 뒤 실행합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[build]
```

### 2. Ollama 준비

Ollama를 실행하고 사용할 모델을 내려받습니다.

```powershell
ollama pull qwen2.5:7b
```

### 3. 설정 파일 생성

Vault 경로는 예시처럼 D: 드라이브 경로를 지정할 수 있습니다.

```powershell
bookmark-agent --config .\config.toml init-config --vault-path D:\obsidian --force
bookmark-agent --config .\config.toml init-db
```

`config.toml`은 개인 경로가 들어가는 파일이라 GitHub에는 올리지 않습니다. 공유용 기본값은 `config.example.toml`에 둡니다.

확장 프로그램 팝업의 `Get local agent` 버튼은 최신 Windows 설치 번들을 직접 다운로드합니다. ZIP을 푼 뒤 `install.ps1`을 실행하면 의존성 설치, Native Host 등록, worker 시작까지 진행됩니다. 브라우저 확장 프로그램은 운영체제 실행 파일을 자동 실행할 수 없으므로 이 설치 스크립트 실행은 한 번 필요합니다.

### 4. 확장 프로그램 빌드

```powershell
python .\scripts\generate_chrome_manifest_key.py
python .\scripts\build_extensions.py
```

빌드 결과는 `outputs/`에 생깁니다. 이 폴더는 로컬 설치용 산출물이므로 GitHub에 올리지 않습니다.

### 5. Native Host 실행 파일 빌드

```powershell
pyinstaller --onefile --clean --name bookmark-agent-native --distpath outputs --workpath work\pyinstaller-build --specpath work\pyinstaller-spec scripts\native_host_launcher.py
```

### 6. Native Host 등록

Chrome:

```powershell
bookmark-agent --config .\config.toml install-native-host --browser chrome --host-path .\outputs\bookmark-agent-native.exe --manifest-dir .\outputs --chrome-extension-id mgeldlpcgoloifmglhedpdiejgaejbda
```

Firefox:

```powershell
bookmark-agent --config .\config.toml install-native-host --browser firefox --host-path .\outputs\bookmark-agent-native.exe --manifest-dir .\outputs
```

### 7. 브라우저 확장 프로그램 설치

설치 페이지를 열려면 다음 명령을 실행합니다.

```powershell
bookmark-agent --config .\config.toml open-extension-setup
```

Chrome:

1. `chrome://extensions`를 엽니다.
2. Developer Mode를 켭니다.
3. `Load unpacked`를 누릅니다.
4. `outputs\chrome-extension` 폴더를 선택합니다.
5. 확장 프로그램 ID가 Native Host 등록 ID와 같은지 확인합니다.
6. 확장 프로그램 팝업에서 `Test connection`을 누릅니다.

Firefox:

1. `about:debugging#/runtime/this-firefox`를 엽니다.
2. `Load Temporary Add-on`을 누릅니다.
3. `outputs\firefox-extension\manifest.json`을 선택합니다.
4. 확장 프로그램 팝업에서 `Test connection`을 누릅니다.

팝업에 `Native host: Connected`가 뜨면 브라우저와 로컬 에이전트 연결이 된 상태입니다.

### 8. Worker 실행

실시간으로 요약을 처리하려면 worker를 켜 둡니다.

```powershell
bookmark-agent --config .\config.toml worker
```

한 번만 처리하려면 다음처럼 실행합니다.

```powershell
bookmark-agent --config .\config.toml worker --once
```

Windows 로그인 시 worker를 자동 실행하려면 다음 명령을 사용합니다.

```powershell
bookmark-agent --config .\config.toml create-worker-shim --output .\outputs\bookmark-agent-worker.cmd
bookmark-agent --config .\config.toml install-worker-startup --command-path .\outputs\bookmark-agent-worker.cmd
```

## 명령어 요약

상태 점검:

```powershell
bookmark-agent --config .\config.toml doctor
```

알림과 활동 로그 테스트:

```powershell
bookmark-agent --config .\config.toml test-notification
```

진단 이벤트 넣기:

```powershell
bookmark-agent --config .\config.toml simulate-event --title "Diagnostic Bookmark" --url "https://example.com/?utm_source=test"
```

기존 북마크 일부 요약:

```powershell
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --type youtube --limit 50
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --domain github.com --limit 25
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --folder AI --limit 100
```

Worker 실행:

```powershell
bookmark-agent --config .\config.toml worker
```

## 프로젝트 폴더 구조

```text
.
  README.md
  SPEC.md
  STORE_SUBMISSION.md
  install.ps1
  install.sh
  pyproject.toml
  config.example.toml
  extension/
    background.js
    popup.html
    popup.css
    popup.js
    options.html
    options.css
    options.js
    icon128.png
    manifest.chrome.json
    manifest.firefox.json
  native-host/
    chrome-host.example.json
    firefox-host.example.json
  scripts/
    build_extensions.py
    generate_chrome_manifest_key.py
    native_host_launcher.py
  src/bookmark_agent/
    activity.py
    cli.py
    config.py
    database.py
    canonical.py
    native_host.py
    worker.py
    extraction.py
    summarizer.py
    markdown.py
    bookmark_import.py
```

## 보안과 개인정보

- 확장 프로그램 권한은 `bookmarks`, `nativeMessaging`, `storage`, `notifications`, `alarms` 중심입니다.
- `storage`는 브라우저 프로필별 `profile_id`와 최근 연결 상태를 저장하는 데 사용합니다.
- `notifications`와 `alarms`는 worker 활동 로그를 주기적으로 확인하고 브라우저 알림을 띄우는 데 사용합니다.
- 확장 프로그램은 파일 시스템에 직접 접근하지 않습니다.
- 로컬 에이전트는 Markdown만 설정된 Vault에 쓰고, 상태/큐/활동 로그는 Vault 밖 앱 데이터에 씁니다.
- AI 호출은 기본적으로 localhost Ollama이며, 사용자가 설정한 외부 API도 지원합니다.
- YouTube 영상 파일은 저장하지 않습니다.
- 전체 웹페이지 아카이브를 저장하지 않습니다.
- 사용자 알림은 기본적으로 Chrome/Firefox 확장 알림으로 표시됩니다.
- `config.toml`, `outputs/`, `work/`, SQLite DB, 실행 파일은 GitHub에 올리지 않습니다.

## 문제 해결

### 팝업에서 Connected가 뜨지 않을 때

1. Native Host가 등록되어 있는지 확인합니다.
2. Chrome 확장 프로그램 ID와 Native Host manifest의 `allowed_origins`가 같은지 확인합니다.
3. Firefox는 임시 설치 확장 프로그램 ID와 manifest의 `allowed_extensions`가 맞는지 확인합니다.
4. `bookmark-agent --config .\config.toml doctor`를 실행합니다.

### 노트가 생성되지 않을 때

1. Worker가 실행 중인지 확인합니다.
2. Ollama가 켜져 있는지 확인합니다.
3. `ollama list`에서 설정된 모델이 있는지 확인합니다.
4. OS별 앱 데이터 폴더의 SQLite 큐에 실패 상태가 쌓였는지 확인합니다.

### 작업이 큐에 들어갔는지 확인하고 싶을 때

실시간 북마크 이벤트는 앱 데이터 폴더의 SQLite `resources` 큐에 들어갑니다. 기존 북마크 대량 분석은 Pro 기능입니다. 사용자가 직접 DB를 열지 않아도 처리 시작과 결과는 브라우저 알림과 콘솔에서 확인할 수 있습니다.

```text
%LOCALAPPDATA%\Bookmark Intelligence\<vault-id>\activity.jsonl
```

작업이 들어갔는데 요약이 늦는 경우에는 보통 다음 중 하나입니다.

- worker가 아직 다음 polling 주기를 기다리는 중
- Ollama가 모델을 처음 로드하는 중
- GPU를 쓰지 못해 CPU로 느리게 처리 중
- 이전 실패 작업이 `next_retry_at` 전이라 대기 중
- 같은 canonical URL이 이미 처리되어 새 노트를 만들지 않은 상태

### Ollama 또는 모델 로드가 실패할 때

Ollama가 꺼져 있거나 모델 로드에 실패하면 해당 URL은 바로 버려지지 않습니다. worker는 실패 상태를 기록하고 재시도 시간을 잡습니다.

확인할 위치:

```text
%LOCALAPPDATA%\Bookmark Intelligence\<vault-id>\activity.jsonl
```

해결 순서:

1. 설정된 공급자의 endpoint와 모델을 확인합니다.
2. Ollama라면 `ollama list`로 모델이 있는지 확인하고, 없으면 `ollama pull qwen2.5:7b`로 설치합니다.
3. `bookmark-agent --config .\config.toml doctor`로 연결과 모델 상태를 확인합니다.
4. GPU 문제라면 Ollama 로그를 확인합니다. agent는 GPU를 직접 고르지 않고 런타임의 성공/실패 결과를 따릅니다.

### YouTube 자막이 비어 있을 때

일부 영상은 자막이 없거나 자동 자막 접근이 제한될 수 있습니다. 자막만 실패한 경우에는 제목, 채널, 길이, 설명을 기반으로 요약을 계속 진행합니다. 이 경우 노트는 생성될 수 있지만, 실제 발화 내용이 빠져 요약 정확도가 낮아질 수 있습니다.

반대로 `yt-dlp`가 영상 정보 자체를 가져오지 못하거나 AI 호출이 실패하면 작업은 `processing_failed`로 기록되고 재시도됩니다. 이 상태는 앱 데이터의 `activity.jsonl`과 확장 프로그램 알림에서 확인할 수 있습니다.

## 현재 검증된 동작

- Chrome 확장 프로그램 팝업의 Native Host 연결 확인
- 실제 Chrome 북마크 생성 이벤트 수신
- YouTube 북마크 메타데이터 처리
- Ollama 로컬 요약
- `D:\obsidian\Bookmarks`에 Markdown 노트 생성
- 기존 북마크 대량 분석은 Pro 큐로 제공
- 진단 명령 `doctor` 통과

## 라이선스

초기 프로젝트 골격입니다. 필요하면 이후에 라이선스 파일을 추가하세요.
