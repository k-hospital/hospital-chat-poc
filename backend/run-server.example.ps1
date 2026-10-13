# 사내 PC에서 챗봇 화면과 질문 분류 서버를 함께 실행한다.
# 사용법: 이 파일을 run-server.local.ps1 로 복사해(저장소에 올라가지 않음) <...> 자리를 채운 뒤 실행한다.
#   powershell -ExecutionPolicy Bypass -File .\run-server.local.ps1
# 주소·모델 이름은 사내 정보이므로 이 예시 파일에 실제 값을 적지 않는다.
$ErrorActionPreference = 'Stop'

$env:SITE_DIR = 'C:\chatpoc-site'                        # npm run build:site -- --out 로 만든 폴더
$env:LLM_BASE_URL = 'http://<LLM 서버 주소>:<포트>/v1'    # OpenAI 호환 API 주소
$env:LLM_MODEL = '<모델 이름>'
# (선택) 위 서버가 실패했을 때 쓸 대체 모델
# $env:LLM_FALLBACK_BASE_URL = 'http://<대체 서버 주소>:<포트>/v1'
# $env:LLM_FALLBACK_MODEL = '<대체 모델 이름>'

$port = 8080
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port $port
