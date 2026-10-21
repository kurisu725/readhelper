Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
Name "研读助手"
OutFile "${OUTDIR}/ResearchDesk-${VERSION}-windows-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\ResearchDesk"
InstallDirRegKey HKCU "Software\ResearchDesk" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "研读助手"
VIAddVersionKey /LANG=2052 "FileDescription" "研读助手安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "ResearchDesk contributors"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

!macro CheckRunning
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\ResearchDesk") p.r0'
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION "研读助手正在运行。请在程序的“插件与更新”中退出本地阅读服务，然后重新运行安装程序。"
    Abort
  ${EndIf}
!macroend

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "此安装包需要 64 位 Windows 10 或 Windows 11。"
    Abort
  ${EndIf}
  !insertmacro CheckRunning
FunctionEnd

Function un.onInit
  !insertmacro CheckRunning
FunctionEnd

Section "研读助手" SEC_MAIN
  SetShellVarContext current
  !insertmacro CheckRunning
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}/*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\研读助手"
  CreateShortCut "$SMPROGRAMS\研读助手\研读助手.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\server\desktop_windows.pyw"'
  CreateShortCut "$DESKTOP\研读助手.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\server\desktop_windows.pyw"'
  WriteRegStr HKCU "Software\ResearchDesk" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk" "DisplayName" "研读助手"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\研读助手.lnk"
  Delete "$SMPROGRAMS\研读助手\研读助手.lnk"
  RMDir "$SMPROGRAMS\研读助手"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\server"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResearchDesk"
  DeleteRegKey HKCU "Software\ResearchDesk"
  ; User data and API configuration in LOCALAPPDATA\ResearchDesk are intentionally preserved.
SectionEnd
