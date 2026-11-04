; BeeOffice Inno Setup 安装脚本
; 构建：ISCC.exe /DMyAppVersion=5.3.2 BeeOffice.iss
; 依赖：先运行 python beeoffice/build_release.py 生成 dist\BeeOffice

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "BeeOffice"
#define MyAppExeName "BeeOffice.exe"

[Setup]
AppId={{BEE0FF1C-5EF3-4B7A-9E42-6A0F0D6B9C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\Programs\BeeOffice
DefaultGroupName=BeeOffice
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=..\release-archive
OutputBaseFilename=BeeOffice-Setup-v{#MyAppVersion}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "..\dist\BeeOffice\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\BeeOffice"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 BeeOffice"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BeeOffice"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 BeeOffice"; Flags: nowait postinstall skipifsilent

[Registry]
; .beshow 演示文稿关联（仅当用户已有该扩展名时也可覆盖，安装器不强制）
Root: HKCU; Subkey: "Software\Classes\.beshow"; ValueType: string; ValueName: ""; ValueData: "BeeOffice.Show"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\BeeOffice.Show"; ValueType: string; ValueName: ""; ValueData: "BeeOffice 演示文稿"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\BeeOffice.Show\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\BeeOffice.Show\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
