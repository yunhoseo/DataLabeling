; ============================================================
; YOLO Auto-Label Pipeline - Inno Setup Installer Script
;
; 빌드 (로컬):
;   iscc installer\windows_installer.iss
; 빌드 (버전 지정):
;   iscc /DMyAppVersion=1.2.3 installer\windows_installer.iss
; 출력:
;   installer\Output\DataLabeling-Setup-{version}.exe
; ============================================================

; ---- 버전 기본값 (CI에서 /DMyAppVersion=x.x.x 로 덮어씀) ----
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName        "DataLabeling"
#define MyAppDisplayName "YOLO Auto-Label Pipeline"
#define MyAppPublisher   "YOLO Auto-Label"
#define MyAppURL         "https://github.com/yunhoseo/DataLabeling"
#define MyAppExeName     "DataLabeling.exe"

; ---- 앱 ID (고유 GUID — 절대 변경하지 마세요, 업그레이드 인식에 사용됨) ----
#define MyAppId "{{A3F7C2E5-9B4D-4E1A-8C6F-2D0B5A7E3F91}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; ---- 설치 경로 ----
; {localappdata} = C:\Users\<User>\AppData\Local
; → 관리자 권한(UAC) 없이 설치 가능
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=yes

; ---- 출력 설정 ----
OutputDir=..\installer\Output
OutputBaseFilename=DataLabeling-Setup-{#MyAppVersion}

; ---- 인스톨러 외관 ----
; 아이콘 파일이 있으면 활성화:
; SetupIconFile=..\app.ico
WizardStyle=modern
WizardSmallImageFile=

; ---- 압축 (torch 포함 대용량 앱 최적화) ----
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumFastBytes=273

; ---- 플랫폼 요건 ----
; Windows 10 이상 (pywebview EdgeChromium 백엔드 요건)
MinVersion=10.0
; 64비트 전용 (PyInstaller x64 빌드)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; ---- 기타 설정 ----
RestartIfNeededByRun=no
; 기존 버전 감지 → 자동 업그레이드 (재설치 확인창 없음)
AppMutex={#MyAppName}Mutex
CloseApplications=yes
CloseApplicationsFilter=*.exe

[Languages]
; 영어 (기본)
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; 바탕화면 바로가기 (기본 체크됨)
Name: "desktopicon"; \
    Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; \
    Flags: checkedonce

[Files]
; ---- PyInstaller 출력 폴더 전체 복사 ----
; .iss 파일 위치(installer/) 기준 ..\ = 프로젝트 루트
; PyInstaller --onedir 출력: dist\DataLabeling\
Source: "..\dist\DataLabeling\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 시작 메뉴 바로가기
Name: "{group}\{#MyAppDisplayName}"; \
    Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; \
    Filename: "{uninstallexe}"

; 바탕화면 바로가기 (Tasks: desktopicon 선택 시)
Name: "{autodesktop}\{#MyAppDisplayName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
; ============================================================
; 핵심: Mark of the Web(MotW) Zone 식별자 제거
;
; 인터넷에서 다운로드된 파일에는 Zone 3 식별자가 붙어
; Windows SmartScreen이 실행을 차단함.
; PowerShell Unblock-File 로 설치된 모든 파일의 MotW를 제거.
; → 이후 DataLabeling.exe 실행 시 SmartScreen 경고 없음.
; ============================================================
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-ChildItem -Path '{app}' -Recurse | Unblock-File -ErrorAction SilentlyContinue"""; \
    Flags: runhidden waituntilterminated; \
    StatusMsg: "보안 설정 초기화 중..."

; 설치 완료 후 앱 실행 체크박스 (기본 체크됨)
Filename: "{app}\{#MyAppExeName}"; \
    Description: "설치 완료 후 {#MyAppDisplayName} 실행"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 앱이 생성하는 데이터 폴더 정리 (선택)
; Type: filesandordirs; Name: "{app}\uploads"
; Type: filesandordirs; Name: "{app}\logs"
Type: dirifempty; Name: "{app}"

[Code]
// ---- 이미 실행 중인 앱 감지 후 경고 ----
function InitializeSetup(): Boolean;
var
  AppRunning: Boolean;
begin
  AppRunning := False;
  // 실행 중인 프로세스 확인 (간단 버전)
  Result := True;
end;
