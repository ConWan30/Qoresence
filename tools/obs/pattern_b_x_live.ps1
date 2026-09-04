<#
.SYNOPSIS
  Pattern B X Live launcher — Deck HDMI glass + Lens, no dshow dual-open.

.DESCRIPTION
  - Points Untitled collection scene LIVE pixels Browser Source at
    http://127.0.0.1:8765/obs-live.html (Lens overlay stays /overlay.html on top).
  - Clears SafeMode=false in %APPDATA%\obs-studio\global.ini without corrupting lines.
  - Starts obs64 --disable-shutdown-check --profile Untitled --collection Untitled --startstreaming.
  - Never prints service.json stream keys.
  - Reports OBS_NORMAL_MODE vs SAFE_MODE and STREAM_MARK_OK vs MISSING from latest log.

  Hard laws: no USB3.0 Video / dshow in OBS, no --x-glass, no secrets in git.
#>
[CmdletBinding()]
param(
    [string]$DeckLiveUrl = "http://127.0.0.1:8765/obs-live.html",
    [string]$LensUrl = "http://127.0.0.1:8765/overlay.html",
    [string]$Profile = "Untitled",
    [string]$Collection = "Untitled",
    [string]$SceneName = "LIVE",
    [string]$PixelsSourceName = "Qoresence HDMI",
    [string]$LensSourceName = "Clutch Lens",
    [string]$ObsPath = "",
    [switch]$SkipStart,
    [int]$LogWaitSeconds = 12
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Msg) { Write-Host "[pattern-b] $Msg" }

function Get-ObsAppData {
    $root = Join-Path $env:APPDATA "obs-studio"
    if (-not (Test-Path -LiteralPath $root)) {
        throw "OBS appdata missing: $root (launch OBS once, then re-run)"
    }
    return $root
}

function Clear-ObsSafeMode([string]$AppData) {
    $ini = Join-Path $AppData "global.ini"
    if (-not (Test-Path -LiteralPath $ini)) {
        Write-Info "global.ini missing — creating with SafeMode=false"
        @(
            "[General]"
            "SafeMode=false"
        ) | Set-Content -LiteralPath $ini -Encoding utf8
        return
    }
    # Line-preserving rewrite: only flip SafeMode*, never rewrite unrelated keys.
    $lines = Get-Content -LiteralPath $ini -Encoding utf8
    $out = New-Object System.Collections.Generic.List[string]
    $sawGeneral = $false
    $wroteSafe = $false
    $inGeneral = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*\[General\]\s*$') {
            $sawGeneral = $true
            $inGeneral = $true
            $out.Add($line) | Out-Null
            continue
        }
        if ($line -match '^\s*\[.+\]\s*$') {
            if ($inGeneral -and -not $wroteSafe) {
                $out.Add("SafeMode=false") | Out-Null
                $wroteSafe = $true
            }
            $inGeneral = $false
            $out.Add($line) | Out-Null
            continue
        }
        if ($inGeneral -and $line -match '^\s*SafeMode\s*=') {
            $out.Add("SafeMode=false") | Out-Null
            $wroteSafe = $true
            continue
        }
        $out.Add($line) | Out-Null
    }
    if (-not $sawGeneral) {
        $out.Insert(0, "[General]") | Out-Null
        $out.Insert(1, "SafeMode=false") | Out-Null
        $wroteSafe = $true
    } elseif ($inGeneral -and -not $wroteSafe) {
        $out.Add("SafeMode=false") | Out-Null
        $wroteSafe = $true
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($ini, $out.ToArray(), $utf8NoBom)
    Write-Info "SafeMode=false written cleanly in global.ini"
}

function New-BrowserSource([string]$Name, [string]$Url, [int]$Width = 1920, [int]$Height = 1080, [int]$Fps = 60) {
    $uuid = [guid]::NewGuid().ToString().ToLowerInvariant()
    return [ordered]@{
        prev_ver           = 520
        name               = $Name
        uuid               = $uuid
        id                 = "browser_source"
        versioned_id       = "browser_source"
        settings           = [ordered]@{
            css                         = ""
            fps                         = $Fps
            height                      = $Height
            width                       = $Width
            url                         = $Url
            shutdown                    = $false
            restart_when_active         = $true
            webpage_control_level       = 1
        }
        mix_and_match      = $false
        mixers             = 0
        sync               = 0
        flags              = 0
        volume             = 1.0
        balance            = 0.5
        enabled            = $true
        muted              = $false
        "push-to-mute"     = $false
        "push-to-mute-delay" = 0
        "push-to-talk"     = $false
        "push-to-talk-delay" = 0
        hotkeys            = [ordered]@{}
        deinterlace_mode   = 0
        deinterlace_field_order = 0
        monitoring_type    = 0
        private_settings   = [ordered]@{}
    }
}

function Ensure-LiveScene([string]$AppData, [string]$Collection, [string]$SceneName, [string]$PixelsUrl, [string]$LensUrl, [string]$PixelsName, [string]$LensName) {
    $scenesDir = Join-Path $AppData "basic\scenes"
    if (-not (Test-Path -LiteralPath $scenesDir)) {
        New-Item -ItemType Directory -Path $scenesDir -Force | Out-Null
    }
    $jsonPath = Join-Path $scenesDir ($Collection + ".json")
    if (-not (Test-Path -LiteralPath $jsonPath)) {
        Write-Info "Creating scene collection $Collection with scene $SceneName"
        $pixels = New-BrowserSource -Name $PixelsName -Url $PixelsUrl -Fps 60
        $lens = New-BrowserSource -Name $LensName -Url $LensUrl -Fps 30
        $sceneUuid = [guid]::NewGuid().ToString().ToLowerInvariant()
        $doc = [ordered]@{
            current_scene  = $SceneName
            current_program_scene = $SceneName
            scene_order    = @(@{ name = $SceneName })
            name           = $Collection
            sources        = @(
                [ordered]@{
                    prev_ver = 520
                    name     = $SceneName
                    uuid     = $sceneUuid
                    id       = "scene"
                    versioned_id = "scene"
                    settings = [ordered]@{
                        id_counter = 2
                        custom_size = $false
                        items = @(
                            [ordered]@{
                                name = $PixelsName
                                source_uuid = $pixels.uuid
                                visible = $true
                                locked = $false
                                rot = 0
                                scale_x = 1.0
                                scale_y = 1.0
                                align = 5
                                bounds_type = 0
                                bounds_align = 0
                                bounds_width = 1.0
                                bounds_height = 1.0
                                crop_left = 0
                                crop_top = 0
                                crop_right = 0
                                crop_bottom = 0
                                id = 1
                                group_item_backup = $false
                                pos = @{ x = 0.0; y = 0.0 }
                                private_settings = @{}
                            },
                            [ordered]@{
                                name = $LensName
                                source_uuid = $lens.uuid
                                visible = $true
                                locked = $false
                                rot = 0
                                scale_x = 1.0
                                scale_y = 1.0
                                align = 5
                                bounds_type = 0
                                bounds_align = 0
                                bounds_width = 1.0
                                bounds_height = 1.0
                                crop_left = 0
                                crop_top = 0
                                crop_right = 0
                                crop_bottom = 0
                                id = 2
                                group_item_backup = $false
                                pos = @{ x = 0.0; y = 0.0 }
                                private_settings = @{}
                            }
                        )
                    }
                    mixers = 0
                    sync = 0
                    flags = 0
                    volume = 1.0
                    balance = 0.5
                    enabled = $true
                    muted = $false
                    "push-to-mute" = $false
                    "push-to-mute-delay" = 0
                    "push-to-talk" = $false
                    "push-to-talk-delay" = 0
                    hotkeys = @{}
                    deinterlace_mode = 0
                    deinterlace_field_order = 0
                    monitoring_type = 0
                    private_settings = @{}
                },
                $pixels,
                $lens
            )
        }
        $json = $doc | ConvertTo-Json -Depth 40
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($jsonPath, $json, $utf8NoBom)
        Write-Info "Wrote $jsonPath"
        return
    }

    # Patch existing collection: set pixel browser URL; keep / avoid dshow.
    $raw = Get-Content -LiteralPath $jsonPath -Raw -Encoding utf8
    $doc = $raw | ConvertFrom-Json

    function Set-BrowserUrl($sources, [string]$WantName, [string]$Url, [int]$Fps) {
        $hit = $false
        foreach ($src in $sources) {
            if ($null -eq $src) { continue }
            $id = [string]$src.id
            $name = [string]$src.name
            if ($id -ne "browser_source") { continue }
            $isPixels = ($name -eq $WantName) -or ($name -match '(?i)hdmi|pixels|qoresence|video|live feed')
            $isLens = ($name -match '(?i)lens|overlay|clutch')
            if ($WantName -eq $PixelsName -and ($isPixels -and -not $isLens)) {
                if (-not $src.settings) { $src | Add-Member -NotePropertyName settings -NotePropertyValue ([pscustomobject]@{}) -Force }
                $src.settings.url = $Url
                $src.settings.width = 1920
                $src.settings.height = 1080
                $src.settings.fps = $Fps
                $src.settings.shutdown = $false
                $src.settings.restart_when_active = $true
                $hit = $true
            }
            if ($WantName -eq $LensName -and $isLens) {
                if (-not $src.settings) { $src | Add-Member -NotePropertyName settings -NotePropertyValue ([pscustomobject]@{}) -Force }
                $src.settings.url = $Url
                $src.settings.width = 1920
                $src.settings.height = 1080
                $hit = $true
            }
            # Migrate anyone still pointed at raw /video → obs-live.html
            if ($WantName -eq $PixelsName -and $src.settings -and [string]$src.settings.url -match '/video(\?|$)') {
                $src.settings.url = $Url
                $hit = $true
                Write-Info "Migrated browser '$name' off raw /video → $Url"
            }
        }
        return $hit
    }

    $sources = @($doc.sources)
    $pixelsOk = Set-BrowserUrl $sources $PixelsName $PixelsUrl 60
    $lensOk = Set-BrowserUrl $sources $LensName $LensUrl 30

    if (-not $pixelsOk) {
        $pixels = New-BrowserSource -Name $PixelsName -Url $PixelsUrl -Fps 60
        $doc.sources = @($doc.sources) + @($pixels)
        Write-Info "Added browser source '$PixelsName' → $PixelsUrl"
        # Attach to LIVE scene if present
        foreach ($src in $doc.sources) {
            if ([string]$src.id -eq "scene" -and [string]$src.name -eq $SceneName) {
                if (-not $src.settings.items) {
                    $src.settings | Add-Member -NotePropertyName items -NotePropertyValue @() -Force
                }
                $items = @($src.settings.items)
                $items = @(
                    [pscustomobject]@{
                        name = $PixelsName
                        source_uuid = $pixels.uuid
                        visible = $true
                        locked = $false
                        id = ([int]($items | Measure-Object).Count + 1)
                        pos = @{ x = 0.0; y = 0.0 }
                        scale_x = 1.0; scale_y = 1.0; rot = 0
                        align = 5; bounds_type = 0; bounds_align = 0
                        bounds_width = 1.0; bounds_height = 1.0
                        crop_left = 0; crop_top = 0; crop_right = 0; crop_bottom = 0
                        group_item_backup = $false
                        private_settings = @{}
                    }
                ) + $items  # bottom layer first in some OBS versions; operator can reorder
                $src.settings.items = $items
            }
        }
    } else {
        Write-Info "Pixels browser URL → $PixelsUrl"
    }

    if (-not $lensOk) {
        Write-Info "Lens browser '$LensName' not found — leave existing overlay sources untouched (expected URL $LensUrl)"
    } else {
        Write-Info "Lens browser URL → $LensUrl"
    }

    # Refuse to leave dshow dual-open hints uncommented in operator output; warn only.
    foreach ($src in $doc.sources) {
        if ([string]$src.id -match 'dshow|wasapi' -or [string]$src.name -match '(?i)USB3\.0\s*Video') {
            Write-Info "WARN: source '$($src.name)' id=$($src.id) looks like capture-card dual-open — disable it for Pattern B"
        }
    }

    $json = $doc | ConvertTo-Json -Depth 60
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($jsonPath, $json, $utf8NoBom)
    Write-Info "Patched $jsonPath"
}

function Find-Obs64([string]$Hint) {
    if ($Hint -and (Test-Path -LiteralPath $Hint)) { return $Hint }
    $candidates = @(
        "${env:ProgramFiles}\obs-studio\bin\64bit\obs64.exe",
        "${env:ProgramFiles(x86)}\obs-studio\bin\64bit\obs64.exe",
        "$env:LOCALAPPDATA\Programs\obs-studio\bin\64bit\obs64.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    $cmd = Get-Command obs64.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "obs64.exe not found — pass -ObsPath"
}

function Get-LatestObsLog([string]$AppData) {
    $logDir = Join-Path $AppData "logs"
    if (-not (Test-Path -LiteralPath $logDir)) { return $null }
    return Get-ChildItem -LiteralPath $logDir -Filter "*.txt" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Report-ObsLog([string]$AppData) {
    $log = Get-LatestObsLog $AppData
    if (-not $log) {
        Write-Info "MODE=UNKNOWN STREAM=MISSING (no log yet)"
        Write-Host "OBS_SAFE_OR_NORMAL=UNKNOWN"
        Write-Host "STREAM_MARK=MISSING"
        return
    }
    # Never open or print service.json. Scan log only; redact key-looking tokens.
    $text = Get-Content -LiteralPath $log.FullName -Raw -Encoding utf8
    $safe = $false
    if ($text -match '(?i)safe\s*mode' -and $text -match '(?i)(enabled|active|starting in safe)') {
        $safe = $true
    }
    if ($text -match '(?i)SafeModeEnabled|\[Safe Mode\]') { $safe = $true }

    $streamOk = $false
    if ($text -match '(?i)Starting stream output|Stream started|successfully connected to|Connect to RTMPS?://') {
        $streamOk = $true
    }
    # Extra: "obs-outputs" / "rtmp-stream" success lines without echoing URLs/keys
    if ($text -match '(?i)\[rtmp-stream:.*\] Connecting to RTMP' -and $text -match '(?i)Connection to .* successful') {
        $streamOk = $true
    }

    if ($safe) {
        Write-Host "OBS_SAFE_OR_NORMAL=SAFE_MODE"
        Write-Info "SAFE_MODE — --startstreaming will not push RTMP; clear SafeMode and relaunch"
    } else {
        Write-Host "OBS_SAFE_OR_NORMAL=OBS_NORMAL_MODE"
        Write-Info "OBS_NORMAL_MODE"
    }
    if ($streamOk) {
        Write-Host "STREAM_MARK=STREAM_MARK_OK"
        Write-Info "STREAM_MARK_OK (latest log: $($log.Name))"
    } else {
        Write-Host "STREAM_MARK=MISSING"
        Write-Info "STREAM_MARK MISSING (latest log: $($log.Name))"
    }
}

# ---- main ----
Write-Info "Pattern B X Live — pixels=$DeckLiveUrl lens=$LensUrl"
Write-Info "Never dual-open USB3.0 Video / dshow. No stream keys printed."

$appData = Get-ObsAppData
Clear-ObsSafeMode $appData
Ensure-LiveScene -AppData $appData -Collection $Collection -SceneName $SceneName `
    -PixelsUrl $DeckLiveUrl -LensUrl $LensUrl -PixelsName $PixelsSourceName -LensName $LensSourceName

if ($SkipStart) {
    Write-Info "SkipStart set — not launching OBS"
    Report-ObsLog $appData
    exit 0
}

$obs = Find-Obs64 $ObsPath
$obsDir = Split-Path -Parent $obs
Write-Info "Starting $obs"
$args = @(
    "--disable-shutdown-check",
    "--profile", $Profile,
    "--collection", $Collection,
    "--startstreaming"
)
Start-Process -FilePath $obs -ArgumentList $args -WorkingDirectory $obsDir | Out-Null
Write-Info "Waiting ${LogWaitSeconds}s for log marks…"
Start-Sleep -Seconds $LogWaitSeconds
Report-ObsLog $appData
