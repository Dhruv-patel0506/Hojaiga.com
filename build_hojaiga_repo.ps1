# Builds the clean D:\Hojaiga repo from d:\new_automation:
# copies ALL source/docs/small assets; excludes environments, models,
# weights, videos, browser profiles, audit logs, build outputs, and any
# single file >= 95 MB (GitHub hard-caps files at 100 MB).
$ErrorActionPreference = 'Continue'
$src = 'D:\new_automation'
$dst = 'D:\Hojaiga'

if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst | Out-Null }

$excludeDirs = @(
    '.git', '.venv', 'hojaiga_env', 'venv', 'venv_core', 'venv_bin',
    '.chrome_cdp_profile', '.test_chrome_profile', '.test_edge_profile',
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.aider.cache_git', '.aider.tags.cache.v4', '.qoder', '.kilo', '.test_upload',
    'audit_logs', 'audit_logs_*', 'models', 'stable-diffusion-webui',
    'ffmpeg-2026-09-21-git-a9cbcc2bbb-full_clean', 'ffmpeg', 'ffmanage',
    'var', 'tmpdir', 'tmp', 'tmp2', 'checkpoints', '.test_harness_videos',
    'pixel-animation-video', '_stale_top_level_backup_*', 'node_modules',
    '.ipynb_checkpoints', 'xvfb', '.cache', 'Clicky (2) (1)_file',
    'videos', 'screenshots', 'observation', 'observations',
    '.tmp_video_frames', 'kokoro_models', 'ffmeg', 'snapshots', '.claude'
)
$excludeFiles = @(
    '*.dll','*.lib','*.pdb','*.tlog','*.ilk','*.obj','*.o','*.bcf','*.sbr',
    '*.exp','*.iobj','*.ipdb','*.res','*.exe','*.snap','build_hojaiga_repo.ps1',
    '*.zip','*.7z','*.tar','*.gz','*.rar',
    '*.pt','*.pth','*.ckpt','*.onnx','*.engine','*.safetensors','*.pkl','*.joblib','*.xz','*.msi','*.bin','*.log',
    '*.mp4','*.avi','*.mkv','*.mov','*.webm','*.wmv','*.flv','*.wav','*.mp3'
)

$rcArgs = @($src, $dst, '/MIR', '/MAX:95000000', '/NFL', '/NDL', '/NJH', '/NP',
            '/XD') + $excludeDirs + @('/XF') + $excludeFiles
& robocopy @rcArgs | Out-Null
Write-Host "ROBOCOPY_EXIT=$LASTEXITCODE (0-7 = success)"

# fresh git repo
Set-Location $dst
if (-not (Test-Path (Join-Path $dst '.git'))) { git init -b main | Out-Null; Write-Host 'GIT_INIT=ok' }
# /MIR deletes dest-only files: restore the repo-only README/.gitignore from git
if (Test-Path (Join-Path $dst '.git')) {
    git -C $dst checkout -- README.md .gitignore 2>$null
    git -C $dst rm -r --cached -q '.claude' 2>$null
}

$size = (Get-ChildItem $dst -Recurse -File | Measure-Object Length -Sum).Sum
$count = (Get-ChildItem $dst -Recurse -File | Measure-Object).Count
Write-Host ("REPO_TOTAL={0:N1} MB  FILES={1}" -f ($size/1MB), $count)
