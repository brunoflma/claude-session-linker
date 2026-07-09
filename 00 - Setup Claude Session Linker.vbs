' ============================================================================
' Setup Claude Session Linker.vbs - Instalador visual de primeiro uso v1.7.0
' ============================================================================
' Abre o instalador visual (.app\setup_gui.py), que cria o venv isolado e
' instala as dependencias com progresso ao vivo. Este VBS localiza um Python
' do sistema para rodar a GUI do setup. Nunca usa o Python do venv.
' ============================================================================
Set objShell = WScript.CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

Dim rootDir, appDir, guiPy, pywExe
rootDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
appDir = rootDir & "\.app"
guiPy = appDir & "\setup_gui.py"

If Not objFSO.FileExists(guiPy) Then
    MsgBox "Instalador não encontrado:" & vbCrLf & guiPy, vbCritical, "Claude Session Linker - Setup"
    WScript.Quit 1
End If

pywExe = FindPythonw()

If pywExe = "" Then
    Dim r
    r = MsgBox("O Python não foi encontrado nesta máquina." & vbCrLf & vbCrLf & _
        "Instale o Python 3.10 ou superior (marque 'Add python.exe to PATH')" & vbCrLf & _
        "e depois rode este instalador novamente." & vbCrLf & vbCrLf & _
        "Abrir a página de download agora?", _
        vbExclamation + vbYesNo, "Claude Session Linker - Python necessário")
    If r = vbYes Then objShell.Run "https://www.python.org/downloads/", 1, False
    WScript.Quit 1
End If

objShell.Run Chr(34) & pywExe & Chr(34) & " " & Chr(34) & guiPy & Chr(34), 1, False

Function FindPythonw()
    Dim bases(1), vers(11), b, v, dir, cand
    bases(0) = "HKLM\SOFTWARE\Python\PythonCore\"
    bases(1) = "HKCU\SOFTWARE\Python\PythonCore\"
    vers(0)="3.14" : vers(1)="3.13" : vers(2)="3.12" : vers(3)="3.11"
    vers(4)="3.10" : vers(5)="3.14-64" : vers(6)="3.13-64" : vers(7)="3.12-64"
    vers(8)="3.11-64" : vers(9)="3.10-64" : vers(10)="3.9" : vers(11)="3.9-64"

    For b = 0 To 1
        For v = 0 To 11
            On Error Resume Next
            dir = objShell.RegRead(bases(b) & vers(v) & "\InstallPath\")
            If Err.Number = 0 And Len(Trim(dir)) > 0 Then
                If Right(dir, 1) = "\" Then dir = Left(dir, Len(dir) - 1)
                cand = dir & "\pythonw.exe"
                If objFSO.FileExists(cand) Then
                    FindPythonw = cand
                    On Error GoTo 0
                    Exit Function
                End If
            End If
            Err.Clear
            On Error GoTo 0
        Next
    Next

    Dim fb(9), i
    fb(0) = "C:\Python314\pythonw.exe"
    fb(1) = "C:\Python313\pythonw.exe"
    fb(2) = "C:\Python312\pythonw.exe"
    fb(3) = "C:\Python311\pythonw.exe"
    fb(4) = "C:\Python310\pythonw.exe"
    fb(5) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe"
    fb(6) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe"
    fb(7) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
    fb(8) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe"
    fb(9) = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python310\pythonw.exe"

    For i = 0 To 9
        If objFSO.FileExists(fb(i)) Then
            FindPythonw = fb(i)
            Exit Function
        End If
    Next

    Dim localPython
    localPython = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Python"
    If objFSO.FolderExists(localPython) Then
        Dim folder, exe
        For Each folder In objFSO.GetFolder(localPython).SubFolders
            exe = folder.Path & "\pythonw.exe"
            If objFSO.FileExists(exe) Then
                FindPythonw = exe
                Exit Function
            End If
        Next
    End If

    FindPythonw = ""
End Function
