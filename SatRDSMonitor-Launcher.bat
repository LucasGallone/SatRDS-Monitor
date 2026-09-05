@echo off
setlocal
cd /d "%~dp0"
title SatRDS Monitor Launcher

echo ==============================================
echo(
echo      ____        _   ____  ____  ____    
echo     / ___^|  __ _^| ^|_^|  _ \^|  _ \/ ___^|   
echo     \___ \ / _` ^| __^| ^|_) ^| ^| ^| \___ \   
echo      ___) ^| (_^| ^| ^|_^|  _ ^<^| ^|_^| ^|___) ^|  
echo     ^|____/ \__,_^|\__^|_^| \_\____/^|____/   
echo(
echo                              M o n i t o r
echo(
echo ==============================================
echo(

:: 1. Checking Python
echo [1/3] Checking Python 3.8+ installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo(
    echo [ERROR] Python is not installed, or the "Add Python to PATH" feature was not enabled.
    echo Please install Python, and make sure to check the "Add Python to PATH" box during the installation process.
    echo Go to https://www.python.org/downloads/ to download the latest version.
    echo(
    pause
    exit /b
)

for /f "delims=" %%v in ('python --version 2^>^&1') do echo        - [OK] %%v found.

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo(
    echo [ERROR] Your Python version is too old. Python 3.8 or higher is required.
    echo Go to https://www.python.org/downloads/ to download the latest version.
	echo Make sure to check the "Add Python to PATH" box during the installation process.
    echo(
    pause
    exit /b
)
echo(

:: 2. Verification of required modules (PyQt5, requests, Flask)
echo [2/3] Checking Python dependencies...
python -c "import PyQt5, requests, flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo        - [INFO] At least one dependency is missing. Installing now, please wait...
    echo(
    python -m pip install --upgrade pip
    python -m pip install PyQt5 requests Flask
    if %errorlevel% neq 0 (
        echo(
        echo [ERROR] Installation failed. Please check your connection.
        echo If the error persists, please report it in the "Issues" section on the GitHub project page.
        echo(
        pause
        exit /b
    )
    echo(
    echo        - [OK] All dependencies are now installed.
) else (
    echo        - [OK] Verification successful. All dependencies are present.
)
echo(

:: 3. Checking script file presence
echo [3/3] Checking core application files...
if not exist "SatRDSMonitor.py" (
    echo(
    echo [ERROR] 'SatRDSMonitor.py' was not found in the current folder.
    echo Please make sure this launcher is placed in the exact same directory as the Python file.
    echo(
    pause
    exit /b
)
echo        - [OK] 'SatRDSMonitor.py' was successfully found.
echo(

:: 4. Launching the software
echo =============================================
echo    Starting SatRDS Monitor, please wait...
echo =============================================
echo(

start "" pythonw SatRDSMonitor.py
if %errorlevel% neq 0 (
    echo(
    echo [ERROR] The software could not start correctly.
    echo If the error persists, please report it in the "Issues" section on the GitHub project page.
    echo(
    pause
    exit /b
)

echo [OK] Application launched successfully.
echo This window will close automatically in 3 seconds.
timeout /t 3 /nobreak >nul
exit /b