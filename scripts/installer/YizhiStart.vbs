' Yizhi silent launcher: no console, Electron bootstrap + splash in main.js
' Must stay ASCII-only (UTF-8 CJK breaks wscript). Soft errors use MsgBox (call WITHOUT //B).
' A1: installed build requires runtime\yizhi-backend.exe only (no python\ fallback).
Option Explicit

Dim gShell, gFso, gWikiRoot

Sub WriteLauncherLog(line)
  On Error Resume Next
  Dim f, logPath
  logPath = gWikiRoot & "\launcher.log"
  Set f = gFso.OpenTextFile(logPath, 8, True)
  f.WriteLine Now & " " & line
  f.Close
  Err.Clear
End Sub

Function LaunchViaWmi(cmdLine, workDir, ByRef outPid, ByRef outRc)
  Dim wmi, proc
  outPid = 0
  outRc = -1
  On Error Resume Next
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  Set proc = wmi.Get("Win32_Process")
  outRc = proc.Create(cmdLine, workDir, Nothing, outPid)
  LaunchViaWmi = (outRc = 0 And outPid <> 0)
  If LaunchViaWmi Then
    WriteLauncherLog "WMI Create ok pid=" & outPid
  Else
    WriteLauncherLog "WMI Create rc=" & outRc & " pid=" & outPid
  End If
  Err.Clear
End Function

Function CountElectronProcesses()
  Dim wmi, col
  CountElectronProcesses = 0
  On Error Resume Next
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  Set col = wmi.ExecQuery("Select ProcessId from Win32_Process Where Name='electron.exe'")
  If Not col Is Nothing Then CountElectronProcesses = col.Count
  Err.Clear
End Function

Function ResolveBackendRuntime(installDir)
  Dim frozen
  frozen = installDir & "\runtime\yizhi-backend.exe"
  If gFso.FileExists(frozen) Then
    ResolveBackendRuntime = frozen
  Else
    ResolveBackendRuntime = ""
  End If
End Function

Dim installDir, electronExe, electronDir, pathExtra, runtimeExe
Dim prevDir, runCmd, wmiRc, pid, beforeCount, afterCount

Set gShell = CreateObject("WScript.Shell")
Set gFso = CreateObject("Scripting.FileSystemObject")

installDir = gFso.GetParentFolderName(WScript.ScriptFullName)
gWikiRoot = gShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Yizhi"
electronDir = installDir & "\electron"
electronExe = electronDir & "\node_modules\electron\dist\electron.exe"
runtimeExe = ResolveBackendRuntime(installDir)

If Not gFso.FolderExists(gWikiRoot) Then
  gFso.CreateFolder gWikiRoot
End If

WriteLauncherLog "start installDir=" & installDir

If runtimeExe = "" Then
  WriteLauncherLog "backend runtime missing (runtime\yizhi-backend.exe)"
  MsgBox "Yizhi backend engine was not found." & vbCrLf & _
    "Expected: " & installDir & "\runtime\yizhi-backend.exe" & vbCrLf & _
    "Please reinstall Yizhi." & vbCrLf & _
    "Log: " & gWikiRoot & "\launcher.log", vbCritical, "Yizhi"
  WScript.Quit 1
End If

If Not gFso.FileExists(electronExe) Then
  WriteLauncherLog "electron.exe missing: " & electronExe
  MsgBox "Yizhi Electron runtime not found." & vbCrLf & electronExe & vbCrLf & _
    "Log: " & gWikiRoot & "\launcher.log", vbCritical, "Yizhi"
  WScript.Quit 1
End If

Dim env, sysPath
Set env = gShell.Environment("PROCESS")
env("MYK_ROOT") = installDir
env("YIZHI_INSTALLED") = "1"
env("PYTHONIOENCODING") = "utf-8"
env("WIKI_ROOT") = gWikiRoot
env("MYKNOWLEDGE_ROOT") = gWikiRoot
env("ELECTRON_NO_ATTACH_CONSOLE") = "1"
env("YIZHI_BACKEND_FROZEN") = "1"
sysPath = gShell.ExpandEnvironmentStrings("%PATH%")
pathExtra = installDir & "\third_party\ffmpeg\bin;" & _
  installDir & "\third_party\bun;" & _
  installDir & "\third_party\yt-dlp;"
env("PATH") = pathExtra & sysPath

WriteLauncherLog "runtime=" & runtimeExe

runCmd = Chr(34) & electronExe & Chr(34) & " ."
prevDir = gShell.CurrentDirectory
gShell.CurrentDirectory = electronDir

beforeCount = CountElectronProcesses()
On Error Resume Next
gShell.Run runCmd, 0, False
If Err.Number <> 0 Then
  WriteLauncherLog "Shell.Run err " & Err.Number & ": " & Err.Description
  Err.Clear
  If Not LaunchViaWmi(runCmd, electronDir, pid, wmiRc) Then
    gShell.CurrentDirectory = prevDir
    MsgBox "Failed to start Yizhi (WMI " & wmiRc & ", pid " & pid & ")." & vbCrLf & _
      "Log: " & gWikiRoot & "\launcher.log", vbCritical, "Yizhi"
    WScript.Quit 1
  End If
Else
  WriteLauncherLog "Shell.Run ok cmd=" & runCmd
End If
Err.Clear

WScript.Sleep 2000
afterCount = CountElectronProcesses()
WriteLauncherLog "electron count before=" & beforeCount & " after=" & afterCount
If afterCount <= beforeCount Then
  gShell.CurrentDirectory = prevDir
  MsgBox "Yizhi exited immediately after start (often missing VC++ runtime)." & vbCrLf & _
    "Run redist\vc_redist.x64.exe under the install folder, then retry." & vbCrLf & _
    "Backend: " & runtimeExe & vbCrLf & _
    "Electron: " & electronExe & vbCrLf & _
    "Log: " & gWikiRoot & "\launcher.log", vbCritical, "Yizhi"
  WScript.Quit 1
End If

gShell.CurrentDirectory = prevDir
WScript.Quit 0
