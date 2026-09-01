Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

scriptPath = FSO.GetParentFolderName(WScript.ScriptFullName) & "\chrome_monitor.py"

' Auto-detect Python from PATH
pythonPath = ""
On Error Resume Next
Set oExec = WshShell.Exec("cmd /c where python")
pythonPath = Trim(oExec.StdOut.ReadLine())
On Error GoTo 0

' Fallback to known install location if detection fails
If pythonPath = "" Or InStr(pythonPath, "INFO:") > 0 Or InStr(pythonPath, "ERROR") > 0 Then
    pythonPath = "C:\Users\chkam\AppData\Local\Programs\Python\Python314\python.exe"
End If

cmd = """" & pythonPath & """ """ & scriptPath & """"
WshShell.Run cmd, 0, false
