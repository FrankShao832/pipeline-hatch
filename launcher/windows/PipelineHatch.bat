@echo off
rem Pipeline Hatch Windows shell - delegates to the cross-platform launcher.
rem "start" + pythonw: no console window. Only the fallback path below is
rem machine-specific; launch.py derives the env and entry point from itself.
set "LAUNCHER=C:\path\to\pipeline_hatch\launcher\launch.py"
if not exist "%LAUNCHER%" set "LAUNCHER=%~dp0..\launch.py"
start "Pipeline Hatch" /b pythonw "%LAUNCHER%" %*
