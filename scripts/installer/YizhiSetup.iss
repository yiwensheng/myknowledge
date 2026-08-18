; 易知 Windows 安装包（Inno Setup 6）

; 由 scripts/build-installer.ps1 调用 ISCC 编译，勿手改 SourceDir/Version 常量



#ifndef MyAppVersion

  #define MyAppVersion "3.0.2"

#endif

#ifndef MyAppVersionFour

  #define MyAppVersionFour "3.0.2.0"

#endif

#ifndef SourceDir

  #define SourceDir "..\..\dist\Yizhi-Staging"

#endif

#ifndef OutputDir

  #define OutputDir "..\..\dist"

#endif

#ifndef MyAppIcon

  ; Relative to this .iss file (scripts/installer/Yizhi.ico). Do NOT pass /DMyAppIcon with
  ; E:\app\... paths — ISPP treats \a in \app as escape and breaks SetupIconFile.
  #define MyAppIcon "Yizhi.ico"

#endif



#define MyAppName "易知"

#define MyAppIconRel "electron\assets\icon.ico"

#define MyAppPublisher "易知"

#define MyAppCopyright "Copyright (C) 2026 易知"

#define MyAppURL "https://www.yzwhysxx.cn/yizhi/purchase.html"

#define MyAppExeName "YizhiStart.vbs"



[Setup]

AppId={{8F3A2B1C-4D5E-6F70-8A9B-0C1D2E3F4051}

AppName={#MyAppName}

AppVersion={#MyAppVersion}

AppVerName={#MyAppName} {#MyAppVersion}

VersionInfoVersion={#MyAppVersionFour}

VersionInfoCompany={#MyAppPublisher}

VersionInfoDescription={#MyAppName} 安装程序

VersionInfoProductName={#MyAppName}

VersionInfoProductVersion={#MyAppVersion}

VersionInfoTextVersion={#MyAppVersion}

VersionInfoCopyright={#MyAppCopyright}

AppPublisher={#MyAppPublisher}

AppPublisherURL={#MyAppURL}

AppSupportURL={#MyAppURL}

AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\Yizhi

DefaultGroupName={#MyAppName}

DisableProgramGroupPage=no

OutputDir={#OutputDir}

OutputBaseFilename=Yizhi-Setup-{#MyAppVersion}

Compression=lzma2/max

; 关闭 solid：解压更快（安装耗时主要瓶颈），安装包体积略增
SolidCompression=no

WizardStyle=modern

PrivilegesRequired=admin

PrivilegesRequiredOverridesAllowed=dialog commandline

ArchitecturesAllowed=x64compatible

ArchitecturesInstallIn64BitMode=x64compatible

MinVersion=10.0.17763

ChangesEnvironment=no

CloseApplications=force

RestartApplications=no

SetupIconFile={#MyAppIcon}

UninstallDisplayIcon={app}\{#MyAppIconRel}

SetupLogging=yes

; 安装前展示产品亮点（UTF-8 BOM 文本）

InfoBeforeFile=installer-highlights.txt

; 内置 Python + Electron + DocuBrowser + VC++ Redist，预留余量（字节）

ExtraDiskSpaceRequired=1250000000



[Languages]

; 简体中文语言包随仓库 scripts/installer/languages/ 分发，不依赖本机 Inno 安装目录

Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"



[CustomMessages]

chinesesimplified.WelcomeLabel1=此向导将引导您在计算机上安装 [name/ver]。%n%n本版亮点：修复外联目录添加、启动自动检查更新、服务闭环与场景模板。易知是本地优先的个人知识库助手，安装后自动享有 30 天免费试用。

chinesesimplified.WelcomeLabel2=继续安装前，建议关闭正在运行的易知。%n%n易知目前仅支持 Windows 64 位（x64）。点击「下一步」查看本版产品亮点并选择安装选项。

chinesesimplified.InfoBeforeLabel=本版产品亮点

chinesesimplified.InfoBeforeClickLabel=继续安装前，请先阅读上述说明：



[Tasks]

Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: unchecked

Name: "startup"; Description: "开机自动启动易知（登录当前 Windows 用户时）"; GroupDescription: "附加选项:"; Flags: unchecked



[Files]

; staging 已由 prune_install_staging.ps1 精简，此处仅兜底排除开发缓存
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.ruff_cache\*,.pytest_cache\*"



[Icons]

; Silent start via .vbs (wscript). Do NOT point shortcuts at .bat — that opens a console.
; Do NOT use wscript //B — it suppresses MsgBox and looks like "shortcut does nothing".
Name: "{group}\{#MyAppName}"; Filename: "{app}\YizhiStart.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconRel}"

Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\YizhiStart.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIconRel}"; Tasks: desktopicon



[Registry]

Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Yizhi"; ValueData: """{app}\YizhiStart.vbs"""; Tasks: startup; Flags: uninsdeletevalue



[Run]

Filename: "{app}\YizhiStart.vbs"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked shellexec



[Code]

var
  InstallQuoteLabel: TNewStaticText;
  InstallQuoteIndex: Integer;
  InstallQuoteLayoutDone: Boolean;

{ 进度页轮播文案：发版前须按本版卖点改写（见发版操作手册 §2.5）。 }
function GetInstallQuote(N: Integer): String;
begin
  case (N mod 10) of
    0: Result := '「外联修复」外联目录写入用户知识库配置，安装目录只读也不再添加失败。';
    1: Result := '「自动更新」有网时启动后检查新版，发现才提示，一次运行只查一次。';
    2: Result := '「服务闭环」顶栏任务条：测通 Key→入库→有出处提问。';
    3: Result := '「场景模板」教师六步、考研、自媒体、职场、一人公司 OPC。';
    4: Result := '「本地优先」笔记与资料保存在您的电脑，内容不上传云端。';
    5: Result := '「有据问答」智能检索您的知识库后再回答，有依据、不瞎编。';
    6: Result := '「自我蒸馏」一次产出可压成可复用技能与原则，越用越懂你。';
    7: Result := '「30 天试用」安装即可体验全部功能，无需提前订阅。';
    8: Result := '「仅 Win64」本安装包支持 Windows 64 位；请完成 VC++ 运行库步骤。';
    9: Result := '「开箱即用」已内置 Python 与 Electron，无需再装运行环境。';
  end;
end;

procedure LayoutInstallQuoteLabel;
begin
  if InstallQuoteLabel = nil then
    Exit;
  if WizardForm.ProgressGauge = nil then
    Exit;
  { 必须与 ProgressGauge 同一 Parent，否则 Left/Top 坐标系不一致会遮住进度条 }
  InstallQuoteLabel.Parent := WizardForm.ProgressGauge.Parent;
  InstallQuoteLabel.Left := WizardForm.ProgressGauge.Left;
  InstallQuoteLabel.Width := WizardForm.ProgressGauge.Width;
  InstallQuoteLabel.Top :=
    WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(8);
  InstallQuoteLabel.Height := ScaleY(40);
  InstallQuoteLayoutDone := True;
end;

procedure EnsureInstallQuoteLabel;
begin
  if InstallQuoteLabel <> nil then
    Exit;
  if WizardForm.ProgressGauge = nil then
    Exit;
  InstallQuoteLabel := TNewStaticText.Create(WizardForm.ProgressGauge.Parent);
  InstallQuoteLabel.Parent := WizardForm.ProgressGauge.Parent;
  InstallQuoteLabel.AutoSize := False;
  InstallQuoteLabel.WordWrap := True;
  InstallQuoteLabel.Font.Style := [fsItalic];
  InstallQuoteLabel.Font.Size := WizardForm.StatusLabel.Font.Size;
  InstallQuoteLabel.Font.Color := WizardForm.StatusLabel.Font.Color;
  InstallQuoteLabel.Caption := GetInstallQuote(0);
  InstallQuoteIndex := 0;
  InstallQuoteLayoutDone := False;
end;

procedure ShowInstallQuoteLabel(Visible: Boolean);
begin
  if InstallQuoteLabel = nil then
    Exit;
  if Visible then
    InstallQuoteLabel.Show
  else
    InstallQuoteLabel.Hide;
end;

procedure UpdateInstallQuote(ProgressPct: Integer);
var
  NewIndex: Integer;
begin
  if InstallQuoteLabel = nil then
    Exit;
  NewIndex := ProgressPct div 10;
  if NewIndex > 7 then
    NewIndex := 7;
  if NewIndex <> InstallQuoteIndex then
  begin
    InstallQuoteIndex := NewIndex;
    InstallQuoteLabel.Caption := GetInstallQuote(InstallQuoteIndex);
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpInstalling then
  begin
    EnsureInstallQuoteLabel;
    InstallQuoteLayoutDone := False;
    LayoutInstallQuoteLabel;
    ShowInstallQuoteLabel(True);
    UpdateInstallQuote(0);
  end
  else
    ShowInstallQuoteLabel(False);
end;

function VCRedistInstalled: Boolean;

begin

  Result :=

    RegKeyExists(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') or

    RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64');

end;



function BundledRuntimeOk: Boolean;

begin

  { A1: 安装版仅要求 runtime\yizhi-backend.exe + Electron }

  Result :=

    FileExists(ExpandConstant('{app}\runtime\yizhi-backend.exe')) and

    FileExists(ExpandConstant('{app}\electron\node_modules\electron\dist\electron.exe'));

end;



procedure SetInstallStatus(const Msg: String);

begin

  WizardForm.StatusLabel.Caption := Msg;

end;



procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);

var

  P: Integer;

begin

  if MaxProgress <= 0 then

    Exit;

  if (InstallQuoteLabel <> nil) and (not InstallQuoteLayoutDone) then
    LayoutInstallQuoteLabel;

  P := (CurProgress * 100) div MaxProgress;

  if P < 20 then

    SetInstallStatus('正在释放内置运行环境（Python / Electron）...')

  else if P < 45 then

    SetInstallStatus('正在安装文档预览与编辑器组件...')

  else if P < 70 then

    SetInstallStatus('正在配置易知知识库与 AI 能力模块...')

  else if P < 90 then

    SetInstallStatus('正在写入启动器与授权配置...')

  else

    SetInstallStatus('即将完成，马上就能开始使用易知...');

  UpdateInstallQuote(P);

end;



function TryInstallVCRedist: Boolean;

var

  ResultCode: Integer;

  RedistPath: String;

begin

  Result := True;

  if VCRedistInstalled then

    Exit;

  if not IsAdminInstallMode then

  begin

    MsgBox(

      '未检测到 Visual C++ 2015-2022 运行库（x64）。' + #13#10 +

      '当前为「无需管理员」安装模式，无法自动安装 VC++。' + #13#10#13#10 +

      '请从微软官网手动安装 VC++ Redistributable x64，' + #13#10 +

      '或使用管理员权限重新安装易知。',

      mbInformation, MB_OK);

    Exit;

  end;

  RedistPath := ExpandConstant('{app}\redist\vc_redist.x64.exe');

  if not FileExists(RedistPath) then

  begin

    MsgBox(

      '安装包缺少 VC++ 运行库组件。' + #13#10 +

      '请重新下载完整安装包或联系客服。',

      mbError, MB_OK);

    Result := False;

    Exit;

  end;

  SetInstallStatus('正在安装 Visual C++ 2015-2022 运行库...');

  if Exec(RedistPath, '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then

    Result := (ResultCode = 0) or (ResultCode = 1638) or (ResultCode = 3010)

  else

    Result := False;

  if not Result then

    MsgBox(

      'Visual C++ 运行库自动安装失败（错误码: ' + IntToStr(ResultCode) + '）。' + #13#10 +

      'Electron 图形界面可能无法启动，请手动安装 VC++ Redistributable x64。',

      mbError, MB_OK);

end;



{ 渠道尾标：JSON + uint32_le + CHNL1
  注意：Unicode Inno 下 TFileStream 对 AnsiString 整块 ReadBuffer 易 AV；
  无尾标的普通安装包必须安静失败，不得中断安装。 }
function ReadSetupChannelTrailer(var OutCode: String; var OutPayload: AnsiString): Boolean;
var
  Stream: TFileStream;
  Size: Integer;
  Magic: AnsiString;
  LenAnsi: AnsiString;
  One: AnsiString;
  N: Cardinal;
  Payload: AnsiString;
  Json: String;
  P, Q, I: Integer;
begin
  Result := False;
  OutCode := '';
  OutPayload := '';
  Stream := nil;
  try
    try
      Stream := TFileStream.Create(ExpandConstant('{srcexe}'), fmOpenRead or fmShareDenyNone);
    except
      Exit;
    end;

    try
      Size := Stream.Size;
      if Size < 13 then
        Exit;

      { 用 Position，避免部分环境下 Seek(负数, soFromEnd) 异常 }
      Stream.Position := Size - 5;
      SetLength(Magic, 5);
      SetLength(One, 1);
      for I := 1 to 5 do
      begin
        if Stream.Read(One, 1) <> 1 then
          Exit;
        Magic[I] := One[1];
      end;
      if Magic <> 'CHNL1' then
        Exit;

      Stream.Position := Size - 9;
      SetLength(LenAnsi, 4);
      for I := 1 to 4 do
      begin
        if Stream.Read(One, 1) <> 1 then
          Exit;
        LenAnsi[I] := One[1];
      end;
      N := Cardinal(Ord(LenAnsi[1])) or (Cardinal(Ord(LenAnsi[2])) shl 8) or
           (Cardinal(Ord(LenAnsi[3])) shl 16) or (Cardinal(Ord(LenAnsi[4])) shl 24);
      if (N = 0) or (N > 4096) or (Size < Integer(N) + 9) then
        Exit;

      Stream.Position := Size - (9 + Integer(N));
      SetLength(Payload, N);
      for I := 1 to Integer(N) do
      begin
        if Stream.Read(One, 1) <> 1 then
          Exit;
        Payload[I] := One[1];
      end;
      OutPayload := Payload;
      Json := String(Payload);
      P := Pos('"c":"', Json);
      if P = 0 then
        Exit;
      P := P + Length('"c":"');
      Q := P;
      while (Q <= Length(Json)) and (Json[Q] <> '"') do
        Inc(Q);
      if Q <= P then
        Exit;
      OutCode := Copy(Json, P, Q - P);
      if (Length(OutCode) < 4) or (Copy(OutCode, 1, 2) <> 'P_') then
        Exit;
      Result := True;
    except
      Result := False;
      OutCode := '';
      OutPayload := '';
    end;
  finally
    if Stream <> nil then
      Stream.Free;
  end;
end;

procedure WriteChannelAttribution;
var
  Code: String;
  Payload: AnsiString;
  DataDir, AppChannel, DataChannel: String;
  JsonOut: String;
begin
  try
    if not ReadSetupChannelTrailer(Code, Payload) then
      Exit;
    AppChannel := ExpandConstant('{app}\channel.dat');
    SaveStringToFile(AppChannel, Code, False);
    DataDir := ExpandConstant('{localappdata}\Yizhi\data');
    ForceDirectories(DataDir);
    DataChannel := DataDir + '\channel.json';
    if FileExists(DataChannel) then
      Exit;
    JsonOut :=
      '{' +
      '"code":"' + Code + '",' +
      '"product":"yizhi",' +
      '"locked":true' +
      '}';
    SaveStringToFile(DataChannel, JsonOut, False);
  except
    { 渠道写入失败不影响主安装 }
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);

begin

  if CurStep = ssInstall then

    SetInstallStatus('正在安装易知，请稍候...')

  else if CurStep = ssPostInstall then

  begin

    TryInstallVCRedist;

    try
      WriteChannelAttribution;
    except
    end;

    { venv leftover breaks relocatable site-packages on customer PCs }
    DeleteFile(ExpandConstant('{app}\python\pyvenv.cfg'));

    if not BundledRuntimeOk then

      MsgBox(

        '安装完成，但未检测到后端引擎或 Electron。' + #13#10 +

        '请确认存在 runtime\yizhi-backend.exe。' + #13#10 +

        '请重新下载完整安装包，或联系客服。',

        mbError, MB_OK);

  end;

end;



function NeedsRestart: Boolean;

begin

  Result := False;

end;


