Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Запуск через pythonw.exe без всплывающего окна консоли
WshShell.CurrentDirectory = currentDir
WshShell.Run "pythonw.exe main.py", 0, False
