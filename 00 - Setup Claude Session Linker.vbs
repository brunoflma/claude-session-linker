' ============================================================================
' Setup Claude Session Linker.vbs - Instalador de primeiro uso v1.5
' ============================================================================
' Clique único para preparar o projeto: localiza o PowerShell do Windows,
' executa .app\setup.ps1 na pasta correta, espera terminar e mostra o
' resultado final. Não pede administrador e não usa o venv em execução.
' ============================================================================
Set objShell = WScript.CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

Dim rootDir, appDir, setupPs1, launcherVbs, resultTxt
rootDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
appDir = rootDir & "\.app"
setupPs1 = appDir & "\setup.ps1"
launcherVbs = rootDir & "\Claude Session Linker.vbs"
resultTxt = appDir & "\logs\setup-result.txt"

If Not objFSO.FileExists(setupPs1) Then
    MsgBox "Setup não encontrado:" & vbCrLf & setupPs1, vbCritical, "Claude Session Linker - Setup"
    WScript.Quit 1
End If

Dim psExe
psExe = FindPowerShell()
If psExe = "" Then
    MsgBox "PowerShell não encontrado nesta máquina." & vbCrLf & vbCrLf & _
           "O PowerShell já vem com Windows 10 e 11. Verifique a instalação do Windows e tente novamente.", _
           vbCritical, "Claude Session Linker - Setup"
    WScript.Quit 1
End If

Dim cmd, exitCode
cmd = Quote(psExe) & " -NoLogo -NoProfile -ExecutionPolicy Bypass -File " & Quote(setupPs1)
exitCode = objShell.Run(cmd, 1, True)

Dim message
message = ReadSetupResult(resultTxt)
If message = "" Then
    message = "Setup finalizado com código " & CStr(exitCode) & "."
End If

If exitCode = 0 Then
    Dim openNow
    openNow = MsgBox(message & vbCrLf & vbCrLf & "Abrir o Claude Session Linker agora?", _
                     vbInformation + vbYesNo, "Claude Session Linker - Setup")
    If openNow = vbYes And objFSO.FileExists(launcherVbs) Then
        objShell.Run Quote(launcherVbs), 1, False
    End If
ElseIf exitCode = 2 Then
    Dim openPython
    openPython = MsgBox(message & vbCrLf & vbCrLf & "Abrir a página de download do Python?", _
                        vbExclamation + vbYesNo, "Claude Session Linker - Python necessário")
    If openPython = vbYes Then objShell.Run "https://www.python.org/downloads/", 1, False
Else
    MsgBox message & vbCrLf & vbCrLf & _
           "Veja detalhes em:" & vbCrLf & resultTxt, _
           vbCritical, "Claude Session Linker - Setup"
End If

WScript.Quit exitCode

Function FindPowerShell()
    Dim winDir, candidates(3), i
    winDir = objShell.ExpandEnvironmentStrings("%WINDIR%")
    candidates(0) = winDir & "\System32\WindowsPowerShell\v1.0\powershell.exe"
    candidates(1) = winDir & "\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
    candidates(2) = winDir & "\SystemWOW64\WindowsPowerShell\v1.0\powershell.exe"
    candidates(3) = "powershell.exe"

    For i = 0 To 2
        If objFSO.FileExists(candidates(i)) Then
            FindPowerShell = candidates(i)
            Exit Function
        End If
    Next

    FindPowerShell = candidates(3)
End Function

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function

Function ReadSetupResult(path)
    On Error Resume Next
    If Not objFSO.FileExists(path) Then
        ReadSetupResult = ""
        Exit Function
    End If

    Dim file, text
    Set file = objFSO.OpenTextFile(path, 1, False)
    text = file.ReadAll
    file.Close
    If Err.Number <> 0 Then
        Err.Clear
        ReadSetupResult = ""
        Exit Function
    End If
    On Error GoTo 0

    text = Replace(text, "STATUS=0" & vbCrLf, "")
    text = Replace(text, "STATUS=2" & vbCrLf, "")
    text = Replace(text, "STATUS=3" & vbCrLf, "")
    text = Replace(text, "STATUS=4" & vbCrLf, "")
    text = Replace(text, "STATUS=5" & vbCrLf, "")
    text = Replace(text, "STATUS=6" & vbCrLf, "")
    ReadSetupResult = Trim(text)
End Function
