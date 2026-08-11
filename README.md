# Obsidian Bookmark Intelligence

Chrome과 Firefox 북마크를 로컬에서 감지하고, 중복을 정리한 뒤, 핵심 요약만 Obsidian Markdown 노트로 남기는 로컬 우선 북마크 정리 도구입니다.

광고가 붙은 북마크 서비스나 일일 사용량 제한이 있는 클라우드 요약 서비스를 기본값으로 쓰지 않습니다. 브라우저 확장 프로그램, 로컬 에이전트, SQLite 작업 큐, Ollama, Obsidian Vault를 조합합니다.

## 목표

- Chrome과 Firefox에서 북마크 생성, 수정, 이동, 삭제 이벤트를 실시간 감지합니다.
- Chrome/Firefox 공용 WebExtension 코드베이스를 사용합니다.
- 기존 북마크 수천 개는 한 번에 색인화하고, 필요한 것만 골라 요약할 수 있습니다.
- 웹페이지 본문 추출은 `trafilatura`를 재사용합니다.
- YouTube는 `yt-dlp`로 메타데이터와 자막만 가져오며 영상 파일은 저장하지 않습니다.
- 요약은 기본적으로 로컬 Ollama 모델을 사용합니다.
- Obsidian에는 읽기 좋은 핵심 Markdown만 저장합니다.
- SQLite는 Obsidian을 대체하는 DB가 아니라, 중복 방지와 재시도를 위한 내부 작업 큐로만 사용합니다.
- 처리 과정과 완료 결과를 Obsidian 활동 노트, JSONL 로그, Windows 알림으로 보여줍니다.

## 현재 기본 구성

이 프로젝트는 Vault 경로를 하드코딩하지 않고 `config.toml`에서 지정합니다. Windows D: 드라이브 Vault 예시는 다음과 같습니다.

```toml
[vault]
path = "D:\\obsidian"
notes_dir = "Bookmarks"
state_dir = ".bookmark-agent"
```

기본 결과 위치는 다음 구조입니다.

```text
D:\obsidian
  Bookmarks\
    _Index.md
    _Inbox.md
    by-domain\
    요약된 북마크 노트.md
  .bookmark-agent\
    bookmark-agent.sqlite3
    events.jsonl
    activity.jsonl
```

`Bookmarks` 폴더는 사용자가 Obsidian에서 읽고 관리하는 최종 결과입니다. `Bookmarks\_Activity.md`에는 처리 단계가 누적됩니다. `.bookmark-agent` 폴더는 프로그램이 실패 재시도, 중복 제거, 처리 상태를 기억하기 위한 내부 상태입니다.

## 전체 작동 방식

```text
Chrome / Firefox
  -> WebExtension
  -> Native Messaging
  -> 로컬 Python 에이전트
  -> URL 정규화와 중복 제거
  -> SQLite 작업 큐
  -> Worker
  -> trafilatura 또는 yt-dlp
  -> Ollama 로컬 요약
  -> Obsidian Markdown
```

브라우저 확장 프로그램은 북마크 이벤트를 감지해서 로컬 에이전트에 전달하는 역할만 합니다. 웹페이지를 긁거나 파일을 쓰거나 요약을 만들지 않습니다.

로컬 에이전트는 URL을 정규화하고 중복을 제거한 뒤, 처리할 작업을 큐에 넣습니다. Worker는 큐를 읽어 웹 본문이나 YouTube 자막을 가져오고, Ollama로 요약한 뒤, Obsidian 노트를 만듭니다.

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

### 기존 북마크 수천 개 가져오기

실시간 이벤트와 별도로, 기존 Chrome/Firefox 북마크를 한 번에 가져올 수 있습니다.

기본 권장 방식은 바로 전부 요약하지 않고 먼저 가벼운 색인을 만드는 것입니다.

```powershell
bookmark-agent --config .\config.toml import-bookmarks --mode index
```

색인 모드는 다음 파일을 만듭니다.

```text
D:\obsidian\Bookmarks\_Index.md
D:\obsidian\Bookmarks\_Inbox.md
D:\obsidian\Bookmarks\by-domain\*.md
```

이 방식은 수천 개 북마크를 Obsidian 노트 수천 개로 바로 쪼개지 않습니다. 대신 도메인별 목록, 전체 인덱스, 처리 후보 목록을 만듭니다. 용량과 파일 수를 작게 유지하면서 전체 북마크 지도를 먼저 확보하는 목적입니다.

필요한 북마크만 요약하려면 `summarize` 모드를 사용합니다.

```powershell
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --type youtube --limit 50
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --domain github.com --limit 25
bookmark-agent --config .\config.toml import-bookmarks --mode summarize --folder AI --limit 100
```

수천 개를 한꺼번에 요약하는 것도 가능하게 `--all` 옵션을 둘 수 있지만, 기본값은 제한을 요구합니다. 이유는 간단합니다. 로컬 요약은 돈은 안 들지만 시간이 들고, 일부 사이트는 본문 추출이나 자막 요청이 실패할 수 있기 때문입니다.

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
  -> browser + bookmark_id 기준
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
  -> Ollama에 요약 요청
  -> 추천 폴더와 태그 산출
  -> Obsidian Markdown 저장
```

본문 전체를 Obsidian에 저장하지 않습니다. 요약, 핵심 포인트, 추천 폴더, 추천 태그, 원본 링크만 남깁니다.

### YouTube 요약 과정

YouTube URL은 영상 파일을 받지 않고 `yt-dlp`로 메타데이터와 자막만 가져옵니다.

```text
YouTube URL
  -> yt-dlp 메타데이터 조회
  -> 제목, 채널, 길이, 설명 추출
  -> 사용 가능한 자막 또는 자동 자막 조회
  -> Ollama에 요약 요청
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

### Ollama 로컬 요약

기본 요약기는 Ollama입니다.

```toml
[summarizer]
provider = "ollama"
model = "qwen2.5:7b"
endpoint = "http://localhost:11434/api/generate"
```

Ollama가 꺼져 있거나 모델이 없으면 작업은 실패로 기록되고 재시도 대상이 됩니다. 클라우드 API 사용량, 광고, 일일 제한이 기본 구조에 들어가지 않습니다.

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

모델이 없다면 먼저 내려받습니다.

```powershell
ollama pull qwen2.5:7b
```

### 작업 진행 알림

worker는 처리 과정을 다음 위치에 기록합니다.

```text
D:\obsidian\Bookmarks\_Activity.md
D:\obsidian\.bookmark-agent\activity.jsonl
```

기록되는 단계는 다음과 같습니다.

```text
worker_started
batch_started
processing_started
extraction_started
extraction_completed
ollama_started
ollama_completed
processing_succeeded
processing_failed
```

특히 `ollama_started`와 `ollama_completed`에는 사용한 Ollama 모델명이 들어갑니다.

Ollama 호출에 실패하면 `processing_failed`에 실패 이유가 남습니다. 예를 들어 모델이 없거나, Ollama가 꺼져 있거나, timeout이 발생하면 `_Activity.md`와 `activity.jsonl`에서 확인할 수 있습니다.

예시:

```markdown
## 2026-08-11T04:20:00Z - ollama_started

- Title: Ollama summary started
- Message: Calling local Ollama model qwen2.5:7b.
- URL: https://example.com/article
- Ollama model: qwen2.5:7b
```

Windows에서는 성공/실패 시 데스크톱 알림도 표시합니다. 시작 알림은 기본적으로 꺼져 있습니다. 북마크를 대량 처리할 때 너무 많은 알림이 뜨는 것을 피하기 위해서입니다.

알림 설정은 `config.toml`에서 조정합니다.

```toml
[notifications]
enabled = true
desktop = true
activity_log = true
activity_note = true
print_to_console = true
notify_on_start = false
notify_on_success = true
notify_on_failure = true
```

모든 과정을 Obsidian에서 보고 싶으면 `activity_note = true`를 유지하면 됩니다. Windows 알림이 불편하면 `desktop = false`로 끄면 됩니다.

### 추천 폴더와 태그

초기 기본값은 자동 이동이 아닙니다.

노트 안에 다음처럼 추천만 남깁니다.

```markdown
## Recommendation

- Suggested folder: AI/Agents
- Suggested tags: bookmark, ai, browser
```

자동으로 브라우저 북마크 폴더를 옮기는 기능은 나중에 옵션으로 켤 수 있게 설계합니다. 처음부터 자동 이동을 켜면 기존 북마크 구조를 예상 밖으로 바꿀 수 있기 때문입니다.

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
recommended_folder: "AI/Reading"
tags:
  - bookmark
  - ai
---

# Example Article

## Summary

짧은 핵심 요약입니다.

## Key Points

- 중요한 포인트 1
- 중요한 포인트 2
- 중요한 포인트 3

## Recommendation

- Suggested folder: AI/Reading
- Suggested tags: bookmark, ai

## Source

- Original: https://example.com/article
```

## 설치

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

알림과 활동 노트 테스트:

```powershell
bookmark-agent --config .\config.toml test-notification
```

진단 이벤트 넣기:

```powershell
bookmark-agent --config .\config.toml simulate-event --title "Diagnostic Bookmark" --url "https://example.com/?utm_source=test"
```

기존 북마크 미리보기:

```powershell
bookmark-agent --config .\config.toml import-bookmarks --mode index --dry-run
```

기존 북마크 색인 생성:

```powershell
bookmark-agent --config .\config.toml import-bookmarks --mode index
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
  pyproject.toml
  config.example.toml
  extension/
    background.js
    popup.html
    popup.css
    popup.js
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

- 확장 프로그램 권한은 `bookmarks`와 `nativeMessaging` 중심입니다.
- 확장 프로그램은 파일 시스템에 직접 접근하지 않습니다.
- 로컬 에이전트는 설정된 Vault 경로 아래에만 상태와 Markdown을 씁니다.
- Ollama 호출은 `localhost` 기준입니다.
- YouTube 영상 파일은 저장하지 않습니다.
- 전체 웹페이지 아카이브를 저장하지 않습니다.
- Windows 알림은 로컬 데스크톱 알림만 사용합니다.
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
4. `.bookmark-agent`의 SQLite 큐에 실패 상태가 쌓였는지 확인합니다.

### 작업이 큐에 들어갔는지 확인하고 싶을 때

실시간 북마크 이벤트나 `import-bookmarks --mode summarize`로 선택된 URL은 SQLite의 `resources` 큐에 들어갑니다. 사용자가 직접 DB를 열지 않아도, 처리 시작과 결과는 다음 파일에서 확인할 수 있습니다.

```text
D:\obsidian\Bookmarks\_Activity.md
D:\obsidian\.bookmark-agent\activity.jsonl
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
D:\obsidian\Bookmarks\_Activity.md
D:\obsidian\.bookmark-agent\activity.jsonl
```

해결 순서:

1. `ollama list`로 모델이 있는지 확인합니다.
2. 없으면 `ollama pull qwen2.5:7b`로 설치합니다.
3. Ollama가 실행 중인지 확인합니다.
4. `bookmark-agent --config .\config.toml doctor`로 연결과 모델 상태를 확인합니다.
5. GPU 문제라면 Ollama 로그를 확인합니다. agent는 GPU를 직접 고르지 않고 Ollama의 성공/실패 결과를 따릅니다.

### YouTube 자막이 비어 있을 때

일부 영상은 자막이 없거나 자동 자막 접근이 제한될 수 있습니다. 자막만 실패한 경우에는 제목, 채널, 길이, 설명을 기반으로 요약을 계속 진행합니다. 이 경우 노트는 생성될 수 있지만, 실제 발화 내용이 빠져 요약 정확도가 낮아질 수 있습니다.

반대로 `yt-dlp`가 영상 정보 자체를 가져오지 못하거나 Ollama 호출이 실패하면 작업은 `processing_failed`로 기록됩니다. 이 상태는 `D:\obsidian\Bookmarks\_Activity.md`와 `D:\obsidian\.bookmark-agent\activity.jsonl`에서 확인할 수 있습니다.

## 현재 검증된 동작

- Chrome 확장 프로그램 팝업의 Native Host 연결 확인
- 실제 Chrome 북마크 생성 이벤트 수신
- YouTube 북마크 메타데이터 처리
- Ollama 로컬 요약
- `D:\obsidian\Bookmarks`에 Markdown 노트 생성
- 기존 북마크 대량 색인 생성
- 진단 명령 `doctor` 통과

## 라이선스

초기 프로젝트 골격입니다. 필요하면 이후에 라이선스 파일을 추가하세요.
