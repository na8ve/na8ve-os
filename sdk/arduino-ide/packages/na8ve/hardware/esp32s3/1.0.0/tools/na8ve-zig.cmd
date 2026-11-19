@echo off
setlocal
set "PY=C:\Espressif\tools\python_env\idf5.5_py3.13_env\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0na8ve_zig.py" %*
