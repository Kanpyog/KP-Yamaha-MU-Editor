@echo off
setlocal
if exist "%~dp0work\venv\Scripts\pythonw.exe" (
    start "" "%~dp0work\venv\Scripts\pythonw.exe" "%~dp0run_editor.pyw"
) else (
    start "" pythonw "%~dp0run_editor.pyw"
)
