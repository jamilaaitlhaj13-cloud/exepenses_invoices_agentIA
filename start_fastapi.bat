@echo off
echo Demarrage du backend FastAPI - SmartExpenseAgent
echo ================================================

cd /d "%~dp0"

REM Activer le venv si present
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

cd backend_fastapi

echo Serveur disponible sur : http://localhost:8000
echo Documentation Swagger  : http://localhost:8000/docs
echo Appuyez sur Ctrl+C pour arreter.
echo.

uvicorn main:app --reload --host 0.0.0.0 --port 8000
