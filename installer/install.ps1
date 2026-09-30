<#
    install.ps1 — Installer YT Short Clipper Pro (Windows 10/11 64-bit)

    Jalankan: klik dua kali install.bat, atau
              powershell -ExecutionPolicy Bypass -File install.ps1

    Yang dilakukan installer ini:
      1. Cek prasyarat (Python, versi, disk, ffmpeg)
      2. Buat virtual environment di folder aplikasi
      3. pip install dari requirements.txt
      4. Pre-cache model whisper (besar —iya, ini butuh beberapa GB)
      5. Tulis shortcut ke Start Menu

    Yang SENGAJA tidak dilakukan installer ini:
      - Tidak menaruh API key user di disk. Key dimasukkan lewat Settings
        aplikasi dan disimpan terenkripsi (DPAPI) di %LOCALAPPDATA%.
      - Tidak membuat folder temp/ atau output/ di dalam folder aplikasi.
      - Tidak installer ffmpeg otomatis tanpa persetujuan — unduhan executable
        dari internet tanpa ditanya adalah hal yang tidak boleh dilakukan
        installer. User diberi pilihan, default-nya winget (sumber resmi).

    Idempoten: dijalankan dua kali tidak merusak apa pun.
#>

$ErrorActionPreference = "Stop"
$script:LogFile = $null

# --------------------------------------------------------------------------
# Infrastruktur
# --------------------------------------------------------------------------
function Write-Banner {
    param([string]$Text)
    Write-Host ""
    Write-Host "==============================================" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "==============================================" -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Text)
    Write-Host "  -> $Text" -ForegroundColor Yellow
}

function Write-Ok {
    param([string]$Text)
    Write-Host "  [OK] $Text" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Text)
    Write-Host "  [!] $Text" -ForegroundColor Yellow
}

function Fail {
    param([string]$Text)
    Write-Host ""
    Write-Host "  [GAGAL] $Text" -ForegroundColor Red
    if ($script:LogFile -and (Test-Path $script:LogFile)) {
        Write-Host "  Log: $script:LogFile" -ForegroundColor Red
    }
    exit 1
}

# --------------------------------------------------------------------------
# Lokasi
# --------------------------------------------------------------------------
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $AppDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogDir = Join-Path $env:LOCALAPPDATA "YTShortClipperPro"
$script:LogFile = Join-Path $LogDir "install-$timestamp.log"

# Module-modul aplikasi membaca versi minimum dari satu tempat; jangan tulis
# angka Python di sini secara terpisah — itu bagaimana README dan installer
# pernah tidak sinkron.
$RequiredPythonMajor = 3
$RequiredPythonMinor = 10
$RequiredPythonPatch = 0
# Bentuk tampil. Dipakai sebagai satu string, bukan "$Major.$Minor" — PowerShell
# membaca titik setelah variabel sebagai akses properti dan gagal parse.
$RequiredPython = "$RequiredPythonMajor.$RequiredPythonMinor"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Start-Transcript -Path $script:LogFile -Force | Out-Null

# --------------------------------------------------------------------------
Write-Banner "YT Short Clipper Pro — Installer"
Write-Host "  Versi   : 2.0.0-pro"
Write-Host "  Folder  : $AppDir"
Write-Host "  Log     : $script:LogFile"
Write-Host "  Data    : $env:LOCALAPPDATA\YTShortClipperPro"
Write-Host "  Output  : $env:USERPROFILE\Videos\YTShortClipperPro"
Write-Host ""
Write-Host "  Konfigurasi API key TIDAK dilakukan di sini."
Write-Host "  Aplikasi akan meminta sendiri, dan menyimpannya terenkripsi."
Write-Host ""

# --------------------------------------------------------------------------
# 1. Prasyarat
# --------------------------------------------------------------------------
Write-Banner "1/5  Cek Prasyarat"

# --- Python ---
$pyExe = $null
$pyVersion = $null

function Test-PythonCandidate {
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path $Exe)) { return $false }
    $out = & $Exe -c "import sys; v = sys.version_info; print(str(v[0]) + '.' + str(v[1]) + '.' + str(v[2]))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $false }
    $parts = $out.Trim().Split('.')
    if ([int]$parts[0] -ne $RequiredPythonMajor) { return $false }
    if ([int]$parts[1] -lt $RequiredPythonMinor) { return $false }
    if ([int]$parts[1] -eq $RequiredPythonMinor -and [int]$parts[2] -lt $RequiredPythonPatch) {
        return $false
    }
    return $true
}

$found = $false
foreach ($candidate in @("python", "python3")) {
    $resolved = (Get-Command $candidate -ErrorAction SilentlyContinue)
    if ($resolved -and (Test-PythonCandidate $resolved.Source)) {
        $pyExe = $resolved.Source
        $pyVersion = (& $pyExe -c "import sys; v = sys.version_info; print(str(v[0]) + '.' + str(v[1]) + '.' + str(v[2]))").Trim()
        $found = $true
        break
    }
}

if (-not $found) {
    Write-Warn "Python $RequiredPython tidak ditemukan."
    $installed = Get-Command python -ErrorAction SilentlyContinue
    if ($installed) {
        $installedExe = $installed.Source
        $ver = & $installedExe -c "import sys; print(sys.version.split()[0])"
        Write-Host "      Python yang terpasang: $ver - terlalu lama"
    }
    Write-Host ""
    Write-Host "  Unduh Python dari https://www.python.org/downloads/"
    Write-Host "  Saat instalasi, CENTANG 'Add python.exe to PATH'."
    Write-Host ""
    $open = Read-Host "  Buka halaman unduhan sekarang? (y/N)"
    if ($open -eq "y" -or $open -eq "Y") {
        Start-Process "https://www.python.org/downloads/"
    }
    Fail "Python $RequiredPython dibutuhkan. Instal ulang lalu jalankan installer ini lagi."
}
Write-Ok "Python $pyVersion di $pyExe"

# --- ffmpeg ---
$ffmpegOk = $null -ne (Get-Command ffmpeg -ErrorAction SilentlyContinue)
if ($ffmpegOk) {
    Write-Ok "ffmpeg ditemukan di PATH"
} else {
    Write-Warn "ffmpeg tidak ditemukan. Aplikasi butuh ffmpeg untuk render video."
    Write-Host ""
    Write-Host "  Opsi 1 (disarankan, sumber resmi):"
    Write-Host "      winget install Gyan.FFmpeg"
    Write-Host ""
    Write-Host "  Opsi 2: unduh dari https://www.gyan.dev/ffmpeg/builds/"
    Write-Host "           lalu taruh ffmpeg.exe di folder install aplikasi ini."
    Write-Host ""
    $install = Read-Host "  Installer ffmpeg sekarang via winget? (y/N)"
    if ($install -eq "y" -or $install -eq "Y") {
        Write-Step "Menjalankan winget install Gyan.FFmpeg (butuh sebentar)"
        & winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
        if ($null -ne (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Ok "ffmpeg berhasil diinstal"
            $ffmpegOk = $true
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") +
                        ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        } else {
            Write-Warn "ffmpeg masih belum terdeteksi. Aplikasi akan gagal saat render."
        }
    }
}

# --- Disk ---
$free = (Get-PSDrive -Name (Split-Path $AppDir -Qualifier).TrimEnd(':') -ErrorAction SilentlyContinue).Free
if ($free) {
    $freeGB = [math]::Round($free / 1GB, 1)
    if ($freeGB -lt 6) {
        Write-Warn "Disk tersisa ${freeGB} GB. Instalasi butuh ~6 GB (venv + model whisper)."
        $cont = Read-Host "  Lanjutkan? (y/N)"
        if ($cont -ne "y" -and $cont -ne "Y") { Fail "Dibatalkan oleh user." }
    } else {
        Write-Ok "Disk tersedia $freeGB GB"
    }
}

# --------------------------------------------------------------------------
# 2. Virtual environment
# --------------------------------------------------------------------------
Write-Banner "2/5  Menyiapkan Virtual Environment"

if (Test-Path $VenvPython) {
    Write-Ok "venv sudah ada — dilewati (installer idempoten)"
} else {
    Write-Step "Membuat venv di .venv\ (bukan di folder aplikasi ke system Python)"
    & $pyExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "Gagal membuat virtual environment." }
    Write-Ok "venv dibuat"
}

Write-Step "Memastikan pip versi terbaru"
& $VenvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null

# --------------------------------------------------------------------------
# 3. Dependensi
# --------------------------------------------------------------------------
Write-Banner "3/5  Memasang Dependensi (butuh 5-15 menit)"
Write-Host "  Layar akan terlihat diam untuk sementara. Itu normal."
Write-Host ""

$RequirementsFile = Join-Path $AppDir "requirements.txt"
if (-not (Test-Path $RequirementsFile)) {
    Fail "requirements.txt tidak ditemukan. Installer harus dijalankan dari folder aplikasi."
}

Write-Step "pip install -r requirements.txt"
& $VenvPython -m pip install -r $RequirementsFile --prefer-binary
if ($LASTEXITCODE -ne 0) {
    Fail "pip install gagal. Lihat log: $script:LogFile"
}
Write-Ok "Dependensi terpasang"

Write-Step "Verifikasi paket kunci"
$checkCode = @'
import importlib, sys
mods = ["customtkinter", "cv2", "mediapipe", "faster_whisper", "numpy", "PIL", "google.genai"]
missing = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        missing.append(f"{m}: {type(e).__name__}")
if missing:
    print("MISSING " + " | ".join(missing))
    sys.exit(1)
print("ALL_OK")
'@
$checkResult = & $VenvPython -c $checkCode 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Ada paket yang belum bisa di-import:"
    Write-Host "      $checkResult"
    Write-Host ""
    Write-Host "  Aplikasi mungkin gagal start. Coba:"
    Write-Host "      .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
} else {
    Write-Ok "Semua paket kunci berhasil di-import"
}

# --------------------------------------------------------------------------
# 4. Model whisper
# --------------------------------------------------------------------------
Write-Banner "4/5  Menyiapkan Model Transkripsi"
Write-Host "  Model diunduh sekali (~1.5 GB untuk 'small', ~3 GB untuk 'medium')."
Write-Host "  Lewati dengan Ctrl+C kalau ingin pilih model lain nanti di Settings."
Write-Host ""

$prefetchCode = @'
import sys
try:
    from faster_whisper import WhisperModel
except Exception as e:
    print(f"SKIP: faster_whisper tidak tersedia ({e})")
    sys.exit(0)
try:
    WhisperModel("small", device="cpu", compute_type="int8")
    print("MODEL_OK")
except Exception as e:
    print(f"MODEL_FAIL: {e}")
    sys.exit(0)
'@
Write-Step "Mengunduh model 'small' ke cache user (bukan ke folder aplikasi)"
& $VenvPython -c $prefetchCode
Write-Host "  (model juga bisa dipilih/ganti nanti di tab Settings aplikasi)"

# --------------------------------------------------------------------------
# 5. Shortcut
# --------------------------------------------------------------------------
Write-Banner "5/5  Membuat Shortcut"

$ExePath = Join-Path $AppDir "YTShortClipper\YTShortClipper.exe"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = Join-Path $StartMenu "YT Short Clipper Pro.lnk"

if (Test-Path $ExePath) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($ShortcutPath)
    $lnk.TargetPath = $ExePath
    $lnk.WorkingDirectory = Split-Path $ExePath
    $lnk.Description = "YT Short Clipper Pro"
    $lnk.Save()
    Write-Ok "Shortcut dibuat di $ShortcutPath"
} else {
    $RunScript = Join-Path $AppDir "run_gui.bat"
    if (Test-Path $RunScript) {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($ShortcutPath)
        $lnk.TargetPath = $RunScript
        $lnk.WorkingDirectory = $AppDir
        $lnk.Description = "YT Short Clipper Pro"
        $lnk.Save()
        Write-Ok "Shortcut dibuat di $ShortcutPath - mode dev, tanpa EXE"
    } else {
        Write-Warn "EXE tidak ditemukan — shortcut tidak dibuat."
        Write-Host "      Jalankan dulu: python build_exe.py"
    }
}

# --------------------------------------------------------------------------
Stop-Transcript | Out-Null

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  INSTALASI SELESAI" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""
if ($ffmpegOk) {
    Write-Host "  Buka aplikasi dari Start Menu:"
    Write-Host "      YT Short Clipper Pro"
} else {
    Write-Host "  BELUM SIAP DIPAKAI — ffmpeg belum ada."
    Write-Host "  Pasang dulu:"
    Write-Host "      winget install Gyan.FFmpeg"
    Write-Host "  lalu jalankan aplikasi."
}
Write-Host ""
Write-Host "  Konfigurasi pertama (API key) dilakukan di dalam aplikasi."
Write-Host "  Key disimpan terenkripsi, tidak di file biasa."
Write-Host ""
Write-Host "  Log: $script:LogFile"
Write-Host ""
Write-Host "  Data aplikasi : $env:LOCALAPPDATA\YTShortClipperPro"
Write-Host "  Hasil video   : $env:USERPROFILE\Videos\YTShortClipperPro"
Write-Host ""
Write-Host "  Menghapus aplikasi:"
Write-Host "    1. hapus folder install aplikasi"
Write-Host "    2. hapus $env:LOCALAPPDATA\YTShortClipperPro (opsional, ada API key di sana)"
Write-Host ""
