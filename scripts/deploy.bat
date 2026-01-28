@echo off
REM Deploy AI Hint System to Batocera
REM Usage: deploy.bat <batocera-ip>
REM Example: deploy.bat 192.168.1.100

if "%1"=="" (
    echo Usage: deploy.bat ^<batocera-ip^>
    echo Example: deploy.bat 192.168.1.100
    exit /b 1
)

set BATOCERA_IP=%1
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

echo ========================================
echo   Deploying AI Hint System to Batocera
echo ========================================
echo.
echo Target: root@%BATOCERA_IP%
echo.

echo [1/4] Creating directories on Batocera...
ssh root@%BATOCERA_IP% "mkdir -p /userdata/system/ai-hints/archive /userdata/system/services"

echo [2/5] Copying files...
scp "%PROJECT_ROOT%\src\daemon.py" root@%BATOCERA_IP%:/userdata/system/ai-hints/daemon.py
scp "%PROJECT_ROOT%\src\config.example.json" root@%BATOCERA_IP%:/userdata/system/ai-hints/config.example.json
scp "%PROJECT_ROOT%\service\ai_hint" root@%BATOCERA_IP%:/userdata/system/services/ai_hint
scp "%PROJECT_ROOT%\scripts\install.sh" root@%BATOCERA_IP%:/userdata/system/ai-hints/install.sh
scp "%PROJECT_ROOT%\scripts\test-components.sh" root@%BATOCERA_IP%:/userdata/system/ai-hints/test-components.sh
scp "%PROJECT_ROOT%\scripts\trigger-hint.sh" root@%BATOCERA_IP%:/userdata/system/ai-hints/trigger-hint.sh

echo [3/5] Setting permissions and fixing line endings...
ssh root@%BATOCERA_IP% "chmod +x /userdata/system/ai-hints/daemon.py /userdata/system/ai-hints/*.sh /userdata/system/services/ai_hint && sed -i 's/\r$//' /userdata/system/ai-hints/*.py /userdata/system/ai-hints/*.sh /userdata/system/services/ai_hint"

echo [4/5] Creating config.json from template (if not exists)...
ssh root@%BATOCERA_IP% "test -f /userdata/system/ai-hints/config.json || cp /userdata/system/ai-hints/config.example.json /userdata/system/ai-hints/config.json"

echo [5/5] Enabling RetroArch network commands...
ssh root@%BATOCERA_IP% "grep -q 'global.retroarch.network_cmd_enable=true' /userdata/system/batocera.conf || echo 'global.retroarch.network_cmd_enable=true' >> /userdata/system/batocera.conf"
ssh root@%BATOCERA_IP% "grep -q 'global.retroarch.network_cmd_port=55355' /userdata/system/batocera.conf || echo 'global.retroarch.network_cmd_port=55355' >> /userdata/system/batocera.conf"

echo.
echo ========================================
echo   Deployment Complete!
echo ========================================
echo.
echo Next steps:
echo.
echo 1. SSH into Batocera:
echo    ssh root@%BATOCERA_IP%
echo.
echo 2. Edit config with your API key:
echo    nano /userdata/system/ai-hints/config.json
echo.
echo 3. Run component tests:
echo    /userdata/system/ai-hints/test-components.sh
echo.
echo 4. Start the service:
echo    batocera-services start ai_hint
echo.
