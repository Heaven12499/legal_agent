@echo off
rem 一键启动后端，固定使用项目 .venv 的 Python 3.12，无需手动 conda activate
cd /d "%~dp0"
.venv\python.exe -m backend.app.api
