Option Explicit

Dim shell, files, folder, appPath
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
appPath = folder & "\cine_azul.py"

On Error Resume Next
shell.Run "pyw """ & appPath & """", 0, False
If Err.Number = 0 Then WScript.Quit

Err.Clear
shell.Run "pythonw.exe """ & appPath & """", 0, False
If Err.Number = 0 Then WScript.Quit

MsgBox "No se encontró Python sin consola. Ejecuta iniciar_cineazul.bat o revisa la instalación de Python.", vbExclamation, "CineAzul"
