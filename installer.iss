[Setup]
AppName=ترجمان
AppVersion=1.0
DefaultDirName={autopf}\Tarjim
DefaultGroupName=Tarjim
OutputBaseFilename=Tarjim-Setup
LicenseFile=terms.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\Tarjim\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\ترجمان"; Filename: "{app}\Tarjim.exe"
Name: "{autodesktop}\ترجمان"; Filename: "{app}\Tarjim.exe"

[Run]
Filename: "{app}\Tarjim.exe"; Description: "تشغيل ترجمان"; Flags: nowait postinstall skipifsilent
