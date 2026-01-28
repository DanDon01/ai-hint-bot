# Deploy AI Hint System to Batocera
#
# Usage: .\deploy.ps1 <batocera-ip>
# Example: .\deploy.ps1 192.168.1.100
#
# Requires: SSH access to Batocera (default password: linux)

param(
    [Parameter(Mandatory=$true)]
    [string]$BatoceraIP
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "========================================"
Write-Host "  Deploying AI Hint System to Batocera"
Write-Host "========================================"
Write-Host ""
Write-Host "Target: root@$BatoceraIP"
Write-Host ""

# Files to copy
$Files = @(
    @{Source="$ProjectRoot\src\daemon.py"; Dest="/userdata/system/ai-hints/daemon.py"},
    @{Source="$ProjectRoot\src\config.example.json"; Dest="/userdata/system/ai-hints/config.example.json"},
    @{Source="$ProjectRoot\service\ai_hint"; Dest="/userdata/system/services/ai_hint"},
    @{Source="$ProjectRoot\scripts\install.sh"; Dest="/userdata/system/ai-hints/install.sh"},
    @{Source="$ProjectRoot\scripts\test-components.sh"; Dest="/userdata/system/ai-hints/test-components.sh"},
    @{Source="$ProjectRoot\scripts\trigger-hint.sh"; Dest="/userdata/system/ai-hints/trigger-hint.sh"}
)

Write-Host "[1/4] Creating directories on Batocera..."
ssh root@$BatoceraIP "mkdir -p /userdata/system/ai-hints/archive /userdata/system/services"

Write-Host "[2/4] Copying files..."
foreach ($File in $Files) {
    $SourcePath = $File.Source
    $DestPath = $File.Dest

    if (!(Test-Path $SourcePath)) {
        Write-Host "  SKIP: $SourcePath (not found)"
        continue
    }

    # Check if NoClobber and file exists
    if ($File.NoClobber) {
        $exists = ssh root@$BatoceraIP "test -f $DestPath && echo yes || echo no"
        if ($exists.Trim() -eq "yes") {
            Write-Host "  SKIP: $DestPath (already exists, not overwriting config)"
            continue
        }
    }

    Write-Host "  Copy: $SourcePath -> $DestPath"
    scp $SourcePath "root@${BatoceraIP}:${DestPath}"
}

Write-Host "[3/4] Setting permissions and line endings..."
ssh root@$BatoceraIP @"
chmod +x /userdata/system/ai-hints/daemon.py
chmod +x /userdata/system/ai-hints/*.sh
chmod +x /userdata/system/services/ai_hint
# Fix line endings (remove Windows CR)
sed -i 's/\r$//' /userdata/system/ai-hints/*.py
sed -i 's/\r$//' /userdata/system/ai-hints/*.sh
sed -i 's/\r$//' /userdata/system/services/ai_hint
"@

Write-Host "[4/5] Creating config.json from template (if not exists)..."
ssh root@$BatoceraIP "test -f /userdata/system/ai-hints/config.json || cp /userdata/system/ai-hints/config.example.json /userdata/system/ai-hints/config.json"

Write-Host "[5/5] Enabling RetroArch network commands..."
$NetworkEnabled = ssh root@$BatoceraIP "grep -q 'global.retroarch.network_cmd_enable=true' /userdata/system/batocera.conf && echo yes || echo no"
if ($NetworkEnabled.Trim() -ne "yes") {
    ssh root@$BatoceraIP @"
echo 'global.retroarch.network_cmd_enable=true' >> /userdata/system/batocera.conf
echo 'global.retroarch.network_cmd_port=55355' >> /userdata/system/batocera.conf
"@
    Write-Host "  Network commands enabled in batocera.conf"
} else {
    Write-Host "  Network commands already enabled"
}

Write-Host ""
Write-Host "========================================"
Write-Host "  Deployment Complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "1. SSH into Batocera:"
Write-Host "   ssh root@$BatoceraIP"
Write-Host ""
Write-Host "2. Edit config with your API key:"
Write-Host "   nano /userdata/system/ai-hints/config.json"
Write-Host ""
Write-Host "3. Run component tests:"
Write-Host "   /userdata/system/ai-hints/test-components.sh"
Write-Host ""
Write-Host "4. Start the service:"
Write-Host "   batocera-services start ai_hint"
Write-Host ""
Write-Host "5. Check logs:"
Write-Host "   tail -f /userdata/system/ai-hints/daemon.log"
Write-Host ""
