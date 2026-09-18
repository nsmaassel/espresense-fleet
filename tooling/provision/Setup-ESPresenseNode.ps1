<#
.SYNOPSIS
  Join a node's setup AP, save settings, restart, and reconnect to an existing home Wi-Fi profile.
.NOTES
  Run locally in the operator's Windows terminal. Passwords are prompted without echo.
  The PC must already have a saved Wi-Fi profile named HomeSsid (or pass HomeProfile).
#>
param(
    [Parameter(Mandatory)] [ValidateLength(1,32)] [string]$ApSsid,
    [Parameter(Mandatory)] [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')] [string]$RoomName,
    [Parameter(Mandatory)] [ValidateLength(1,32)] [string]$HomeSsid,
    [Parameter(Mandatory)] [ValidateNotNullOrEmpty()] [string]$MqttHost,
    [ValidateRange(1,65535)] [int]$MqttPort = 1883,
    [string]$MqttUser = "",
    [ValidatePattern('^[a-zA-Z0-9.-]+(?::[0-9]+)?$')] [string]$PortalIp = "192.168.4.1",
    [string]$HomeProfile = $HomeSsid
)

$ErrorActionPreference = "Stop"
$portalUri = "http://$PortalIp/wifi/main"

function Invoke-Netsh([string[]]$NetshArguments) {
    & netsh @NetshArguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Windows Wi-Fi command failed (exit $LASTEXITCODE)." }
}

function Connect-OpenWifi([string]$Ssid) {
    if ([Text.Encoding]::UTF8.GetByteCount($Ssid) -gt 32) { throw "SSID exceeds 32 bytes." }
    $safeSsid = [Security.SecurityElement]::Escape($Ssid)
    $xml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$safeSsid</name>
    <SSIDConfig><SSID><name>$safeSsid</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType><connectionMode>manual</connectionMode>
    <MSM><security><authEncryption><authentication>open</authentication><encryption>none</encryption><useOneX>false</useOneX></authEncryption></security></MSM>
</WLANProfile>
"@
    $tmp = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmp, $xml)
        Invoke-Netsh -NetshArguments @('wlan', 'add', 'profile', "filename=$tmp", 'user=current')
    } finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
    Invoke-Netsh -NetshArguments @('wlan', 'connect', "name=$Ssid", "ssid=$Ssid")
}

function Read-LocalSecret([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secure.Dispose() }
}

$values = @{}
$wifiPassword = $mqttPass = $body = $pairs = $null
try {
    Write-Host "Connecting to the node setup AP ..."
    Connect-OpenWifi $ApSsid
    # netsh reports a queued connection, not a completed association. Wait for the portal.
    $current = $null
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $current = Invoke-RestMethod -Uri $portalUri -Method Get -TimeoutSec 3
            break
        } catch { if ($attempt -eq 11) { throw "Node portal did not become reachable." } }
    }
    if ($current.defaults -isnot [pscustomobject] -or $current.values -isnot [pscustomobject]) {
        throw "Node returned an incomplete configuration."
    }
    foreach ($src in @($current.defaults, $current.values)) {
        foreach ($p in $src.PSObject.Properties) {
            if ($null -eq $p.Value -or $p.Value -is [array] -or $p.Value -is [pscustomobject]) {
                throw "Node returned an unsupported setting."
            }
            $values[$p.Name] = $p.Value
        }
    }
    # The firmware omits empty strings and passwords from both response objects.
    foreach ($key in @('wifi-ssid', 'wifi-password', 'mqtt_host', 'mqtt_user', 'mqtt_pass')) {
        if (-not $values.ContainsKey($key)) { $values[$key] = '' }
    }
    $required = @('room', 'wifi-ssid', 'wifi-password', 'mqtt_host', 'mqtt_port')
    if ($MqttUser) { $required += @('mqtt_user', 'mqtt_pass') }
    foreach ($key in $required) {
        if (-not $values.ContainsKey($key)) { throw "Node configuration is missing a required setting." }
    }
    $wifiPassword = Read-LocalSecret "Wi-Fi password"
    $values['room'] = $RoomName
    $values['wifi-ssid'] = $HomeSsid
    $values['wifi-password'] = $wifiPassword
    $values['mqtt_host'] = $MqttHost
    $values['mqtt_port'] = $MqttPort
    if ($MqttUser) {
        $mqttPass = Read-LocalSecret "MQTT password"
        $values['mqtt_user'] = $MqttUser
        $values['mqtt_pass'] = $mqttPass
    }
    $pairs = foreach ($kv in $values.GetEnumerator()) {
        if ($kv.Value -is [bool]) {
            if ($kv.Value) { "$([uri]::EscapeDataString($kv.Key))=1" }
        } else {
            "$([uri]::EscapeDataString($kv.Key))=$([uri]::EscapeDataString([string]$kv.Value))"
        }
    }
    $body = $pairs -join '&'
    Write-Host "Saving settings ..."
    Invoke-RestMethod -Uri $portalUri -Method Post -Body $body -ContentType 'application/x-www-form-urlencoded' -TimeoutSec 10 | Out-Null
    try { Invoke-RestMethod -Uri "http://$PortalIp/restart" -Method Post -TimeoutSec 2 | Out-Null }
    catch { Write-Warning "Restart response not confirmed; the node may already be reconnecting." }
} catch {
    # HTTP errors can contain submitted credentials. Never echo the remote error body.
    throw "Provisioning failed. Check the setup AP and node settings before retrying; a save may already have completed."
} finally {
    $values.Clear()
    $wifiPassword = $mqttPass = $body = $pairs = $null
    Write-Host "Reconnecting this PC to its saved home Wi-Fi profile ..."
    Invoke-Netsh -NetshArguments @('wlan', 'connect', "name=$HomeProfile", "ssid=$HomeSsid")
}
Write-Host "DONE when: espresense/rooms/$RoomName/status reports online and fresh telemetry arrives on the configured broker."
Write-Host "Then move the node to a wall adapter."
