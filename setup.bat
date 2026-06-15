@echo off
echo Setting up Banking Migration System...
echo.

echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Setup complete!
echo.
echo Next steps:
echo 1. Copy .env.example to .env
echo 2. Edit .env with your database credentials
echo 3. Run: streamlit run app.py
echo.
pause
