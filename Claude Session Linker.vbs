' ============================================================================
' Claude Session Linker.vbs - Launcher v1.0
' ============================================================================
Set objShell = WScript.CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

Dim rootDir, appDir, pythonDir, pythonExe, guiScript

rootDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
appDir = rootDir & "\.app"
pythonExe = ""
pythonDir = ""
guiScript = appDir & "\session_linker.py"

' --- 0. Project venv (.app\venv) — self-contained, preferred ----------------
Dim venvExe : venvExe = appDir & "\venv\Scripts\pythonw.exe"
If objFSO.FileExists(venvExe) Then
    pythonExe = venvExe
    pythonDir = appDir & "\venv\Scripts"
End If

' --- 1. Embedded python bundled inside .app\python (optional) ---------------
If pythonExe = "" Then
    Dim embeddedExe : embeddedExe = appDir & "\python\pythonw.exe"
    If objFSO.FileExists(embeddedExe) Then
        pythonExe = embeddedExe
        pythonDir = appDir & "\python"
    End If
End If

' --- 2. Windows Registry (PATH-independent, works from any launch context) --
If pythonExe = "" Then
    Dim regBases(1), regVers(11)
    regBases(0) = "HKLM\SOFTWARE\Python\PythonCore\"
    regBases(1) = "HKCU\SOFTWARE\Python\PythonCore\"
    regVers(0)  = "3.14"    : regVers(1)  = "3.13"
    regVers(2)  = "3.12"    : regVers(3)  = "3.11"
    regVers(4)  = "3.10"    : regVers(5)  = "3.9"
    regVers(6)  = "3.14-64" : regVers(7)  = "3.13-64"
    regVers(8)  = "3.12-64" : regVers(9)  = "3.11-64"
    regVers(10) = "3.10-64" : regVers(11) = "3.9-64"

    Dim b, v, regVal, regCandidate
    For b = 0 To 1
        For v = 0 To 11
            On Error Resume Next
            regVal = objShell.RegRead(regBases(b) & regVers(v) & "\InstallPath\")
            If Err.Number = 0 And Len(Trim(regVal)) > 0 Then
                regCandidate = Trim(regVal)
                If Right(regCandidate, 1) = "\" Then
                    regCandidate = Left(regCandidate, Len(regCandidate) - 1)
                End If
                regCandidate = regCandidate & "\pythonw.exe"
                If objFSO.FileExists(regCandidate) Then
                    pythonExe = regCandidate
                    pythonDir = objFSO.GetParentFolderName(regCandidate)
                    On Error GoTo 0
                    Exit For
                End If
            End If
            Err.Clear
            On Error GoTo 0
        Next
        If pythonExe <> "" Then Exit For
    Next
End If

' --- 3. Common installation paths as last resort ----------------------------
If pythonExe = "" Then
    Dim fallbacks(7)
    fallbacks(0) = "C:\Python314\pythonw.exe"
    fallbacks(1) = "C:\Python313\pythonw.exe"
    fallbacks(2) = "C:\Python312\pythonw.exe"
    fallbacks(3) = "C:\Python311\pythonw.exe"
    fallbacks(4) = "C:\Python310\pythonw.exe"
    fallbacks(5) = "C:\Python39\pythonw.exe"
    fallbacks(6) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe"
    fallbacks(7) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe"
    Dim f
    For f = 0 To 7
        If objFSO.FileExists(fallbacks(f)) Then
            pythonExe = fallbacks(f)
            pythonDir = objFSO.GetParentFolderName(fallbacks(f))
            Exit For
        End If
    Next
End If

' --- Guards ------------------------------------------------------------------
If pythonExe = "" Then
    MsgBox "Ambiente Python não encontrado." & vbCrLf & vbCrLf & _
           "Instale o Python 3.10+ em C:\Python3XX\ ou pelo instalador oficial, " & _
           "ou rode 'powershell -File .app\setup.ps1' para criar o venv isolado.", _
           vbCritical, "Claude Session Linker - inicialização"
    WScript.Quit 1
End If
If Not objFSO.FileExists(guiScript) Then
    MsgBox "Interface do Claude Session Linker não encontrada." & vbCrLf & vbCrLf & _
           "Pasta esperada:" & vbCrLf & appDir, vbCritical, "Claude Session Linker - inicialização"
    WScript.Quit 1
End If

' --- TCL/TK paths (only when embedded/venv python has bundled tcl) ----------
Dim tclDir : tclDir = pythonDir & "\tcl"
If objFSO.FolderExists(tclDir) Then
    Dim env : Set env = objShell.Environment("Process")
    env("TCL_LIBRARY") = tclDir & "\tcl8.6"
    env("TK_LIBRARY") = tclDir & "\tk8.6"
End If

' --- Launch --------------------------------------------------------------
objShell.Run Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & guiScript & Chr(34), 1, False
