# Smoke-test vendored Spec Kit scripts without modifying the working repository.
$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
$previousFeature = $env:SPECIFY_FEATURE
$previousDirectory = $env:SPECIFY_FEATURE_DIRECTORY
$tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$scratch = Join-Path $tempParent ('espresense-specify-test-' + [guid]::NewGuid().ToString('N'))
$fixtureRepo = Join-Path $scratch 'repo'
$fixtureWorktree = Join-Path $scratch 'worktree'

function Assert-True([bool]$condition, [string]$message) {
    if (-not $condition) { throw $message }
}

New-Item -ItemType Directory $fixtureRepo | Out-Null
Copy-Item (Join-Path $source '.specify') (Join-Path $fixtureRepo '.specify') -Recurse
# A developer's ignored active-feature selector must not affect this fixture.
Remove-Item (Join-Path $fixtureRepo '.specify/feature.json') -ErrorAction SilentlyContinue
Push-Location $fixtureRepo
try {
    git init -q
    Assert-True ($LASTEXITCODE -eq 0) 'git init failed'
    git config core.autocrlf false
    git add .specify
    git -c user.name='Fixture Author' -c user.email='fixture@example.invalid' commit -qm 'Fixture baseline'
    Assert-True ($LASTEXITCODE -eq 0) 'fixture commit failed'
    git worktree add -q -b feat/smoke $fixtureWorktree
    Assert-True ($LASTEXITCODE -eq 0) 'fixture worktree failed'
    Set-Location $fixtureWorktree
    Remove-Item Env:SPECIFY_FEATURE, Env:SPECIFY_FEATURE_DIRECTORY -ErrorAction SilentlyContinue

    $output = pwsh -NoProfile -File .specify/scripts/powershell/create-new-feature.ps1 -DryRun -Json -Number 9 -ShortName smoke 'Fixture feature'
    Assert-True ($LASTEXITCODE -eq 0) 'create-feature dry run failed'
    $dryRun = $output | ConvertFrom-Json
    Assert-True ($dryRun.DRY_RUN -and $dryRun.HAS_GIT) 'dry run did not recognize worktree'
    Assert-True (-not (Test-Path specs/009-smoke)) 'dry run wrote feature files'
    Assert-True ((git branch --show-current) -eq 'feat/smoke') 'dry run switched branch'

    $output = pwsh -NoProfile -File .specify/scripts/powershell/create-new-feature.ps1 -Json -Number 9 -ShortName smoke 'Fixture feature'
    Assert-True ($LASTEXITCODE -eq 0) 'create-feature failed'
    $created = $output | ConvertFrom-Json
    Assert-True ($created.HAS_GIT -and $created.BRANCH_NAME -eq '009-smoke') 'worktree feature creation failed'
    Assert-True (Test-Path specs/009-smoke/spec.md) 'spec template was not created'

    $output = pwsh -NoProfile -File .specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks
    Assert-True ($LASTEXITCODE -ne 0 -and "$output" -match 'plan.md not found') 'missing plan accepted'
    $output = pwsh -NoProfile -File .specify/scripts/powershell/setup-plan.ps1 -Json
    Assert-True ($LASTEXITCODE -eq 0) 'setup-plan failed'
    $plan = $output | ConvertFrom-Json
    Assert-True ($plan.HAS_GIT -and $plan.SPECS_DIR -like '*009-smoke') 'wrong worktree plan'
    Add-Content specs/009-smoke/plan.md 'REVIEWED PLAN MARKER'
    $reviewedHash = (Get-FileHash specs/009-smoke/plan.md).Hash
    $output = pwsh -NoProfile -File .specify/scripts/powershell/setup-plan.ps1 -Json
    Assert-True ($LASTEXITCODE -eq 0) 'resuming plan failed'
    Assert-True ((Get-FileHash specs/009-smoke/plan.md).Hash -eq $reviewedHash) 'existing plan overwritten'

    $output = pwsh -NoProfile -File .specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks
    Assert-True ($LASTEXITCODE -ne 0 -and "$output" -match 'tasks.md not found') 'missing tasks accepted'
    $output = pwsh -NoProfile -File .specify/scripts/powershell/setup-tasks.ps1 -Json
    Assert-True ($LASTEXITCODE -eq 0) 'setup-tasks failed'
    Assert-True (($output | ConvertFrom-Json).TASKS_TEMPLATE -like '*tasks-template.md') 'tasks template unresolved'
    Set-Content specs/009-smoke/tasks.md '# Fixture tasks'
    git checkout -qb feat/resume
    Assert-True ($LASTEXITCODE -eq 0) 'fixture resume branch failed'
    $env:SPECIFY_FEATURE = '009-smoke'
    $env:SPECIFY_FEATURE_DIRECTORY = 'specs/009-smoke'
    Set-Content .specify/feature.json '{"feature_directory":"specs/stale-selector"}'
    $output = pwsh -NoProfile -File .specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
    Assert-True ($LASTEXITCODE -eq 0) 'explicit existing feature selection failed'
    $found = $output | ConvertFrom-Json
    Assert-True ($found.FEATURE_DIR -like '*009-smoke' -and $found.AVAILABLE_DOCS -contains 'tasks.md') 'wrong feature or missing task discovery'
    $paths = pwsh -NoProfile -File .specify/scripts/powershell/check-prerequisites.ps1 -Json -PathsOnly | ConvertFrom-Json
    Assert-True ($paths.REPO_ROOT -eq $fixtureWorktree) 'parent repo selected instead of worktree'
    Write-Output 'PASS: Spec Kit dry run, feature creation, worktree discovery, missing artifacts, plan preservation, task template, and explicit feature selection.'
} finally {
    Pop-Location
    $env:SPECIFY_FEATURE = $previousFeature
    $env:SPECIFY_FEATURE_DIRECTORY = $previousDirectory
    # Only remove the exact uniquely-created fixture under the system temp directory.
    $resolvedScratch = [IO.Path]::GetFullPath($scratch)
    $expectedPrefix = $tempParent.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar + 'espresense-specify-test-'
    if (-not $resolvedScratch.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing cleanup outside the temporary test fixture'
    }
    Remove-Item -LiteralPath $resolvedScratch -Recurse -Force
}