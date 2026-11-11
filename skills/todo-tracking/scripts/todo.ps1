#Requires -Version 5.1
<#
.SYNOPSIS
  TODO.md 的簡易 CRUD 工具。

.DESCRIPTION
  在專案根目錄維護 TODO.md。每個項目佔一個區塊：
    標題行：- [ ] TODO-0001 [P1] 標題
    說明行：  - 位置: path:line
              - 說明: ...
              - 影響: ...
              - 建議: ...
              - 發現: yyyy-MM-dd

.EXAMPLE
  .\todo.ps1 init
  .\todo.ps1 add -Title "匯入端點缺稽核策略" -Priority P1 -Location "src/main/java/com/pollex/fm/web/rest/ExcelDataExchangeResource.java:33" -Note "factory 回傳 null，aspect 未檢查空值"
  .\todo.ps1 list
  .\todo.ps1 list -Status all -Json
  .\todo.ps1 show TODO-0001
  .\todo.ps1 update TODO-0001 -Priority P0 -Fix "新增 DataExchangeImportLoggingStrategy"
  .\todo.ps1 done TODO-0001
  .\todo.ps1 reopen TODO-0001
  .\todo.ps1 remove TODO-0001
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('init', 'add', 'list', 'show', 'update', 'done', 'reopen', 'remove', 'path', 'help')]
    [string]$Command = 'help',

    [Parameter(Position = 1)]
    [string]$Id,

    [string]$Title,

    [ValidateSet('P0', 'P1', 'P2', 'P3')]
    [string]$Priority,

    [string]$Location,
    [string]$Note,
    [string]$Impact,
    [string]$Fix,

    [ValidateSet('open', 'done', 'all')]
    [string]$Status = 'open',

    [string]$TodoFile,

    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$FieldOrder = @('位置', '說明', '影響', '建議', '發現', '完成')
$HeaderPattern = '^- \[( |x|X)\] (TODO-\d+) \[([A-Za-z0-9]+)\] (.*)$'
$DetailPattern = '^\s+-\s*(位置|說明|影響|建議|發現|完成)\s*[:：]\s*(.*)$'
$Template = @(
    '# TODO'
    ''
    '> 未處理問題清單。翻閱程式碼發現問題時記錄於此，與當前任務無關者不修正。'
    '> 請使用 `scripts/todo.ps1` 增刪改；沒有 PowerShell 時，直接依下列格式手動編輯。'
    '>'
    '> 格式：'
    '> 標題行   - [ ] TODO-<NNNN> [P<n>] 一句話描述問題'
    '> 說明行     - 位置: 相對路徑:行號'
    '>            - 說明: 現象與原因'
    '>            - 影響: 不修的後果（選填）'
    '>            - 建議: 建議做法（選填）'
    '>            - 發現: yyyy-MM-dd'
    '>            - 完成: yyyy-MM-dd（標記完成時填）'
    '>'
    '> 完成時把 [ ] 改成 [x]。項目依 ID 排序，項目之間空一行。'
    ''
)

# 專案根目錄標記；順序只決定哪個標記命中，不影響結果路徑。
$MarkerNames = @('.git', 'package.json', 'pyproject.toml', 'setup.py', 'go.mod', 'Cargo.toml', 'pom.xml', 'build.gradle', 'composer.json', 'Gemfile')
$MarkerSuffixes = @('.sln', '.csproj')

function Test-MarkerDirectory {
    param([string]$Directory)

    foreach ($name in $MarkerNames) {
        if (Test-Path -LiteralPath (Join-Path $Directory $name)) { return $true }
    }
    try {
        foreach ($file in [System.IO.Directory]::GetFiles($Directory)) {
            $leaf = [System.IO.Path]::GetFileName($file)
            foreach ($suffix in $MarkerSuffixes) {
                if ($leaf.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
            }
        }
    } catch {
        # 目錄不可列舉時（例如權限不足），glob 標記視為未命中，不中斷整體流程。
    }
    return $false
}

# 解析順序：
#   -TodoFile > TODO_FILE > TODO_ROOT > 標記向上尋找 > 目前目錄
function Resolve-TodoPath {
    param([string]$Override)

    $candidate = $Override
    if ([string]::IsNullOrWhiteSpace($candidate)) { $candidate = $env:TODO_FILE }
    if (-not [string]::IsNullOrWhiteSpace($candidate)) {
        if ([System.IO.Path]::IsPathRooted($candidate)) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
        return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $candidate))
    }

    if (-not [string]::IsNullOrWhiteSpace($env:TODO_ROOT)) {
        $rootPath = $env:TODO_ROOT
        if (-not [System.IO.Path]::IsPathRooted($rootPath)) {
            $rootPath = Join-Path (Get-Location).Path $rootPath
        }
        return [System.IO.Path]::GetFullPath((Join-Path $rootPath 'TODO.md'))
    }

    $start = (Get-Location).Path
    $probe = $start
    while (-not [string]::IsNullOrWhiteSpace($probe)) {
        if (Test-MarkerDirectory -Directory $probe) {
            return (Join-Path $probe 'TODO.md')
        }
        $parent = [System.IO.Path]::GetDirectoryName($probe)
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $probe) {
            break
        }
        $probe = $parent
    }
    return (Join-Path $start 'TODO.md')
}

# 統一寫入：UTF-8（無 BOM）、LF、原子替換（同目錄暫存檔 + Replace/Move）。
function Write-TodoText {
    param([string]$Path, [string]$Text)

    $directory = [System.IO.Path]::GetDirectoryName($Path)
    if (-not [string]::IsNullOrWhiteSpace($directory) -and -not (Test-Path -LiteralPath $directory)) {
        [void](New-Item -ItemType Directory -Path $directory -Force)
    }

    $encoding = New-Object System.Text.UTF8Encoding($false)
    $tmp = Join-Path $directory ([System.IO.Path]::GetRandomFileName())
    $backup = Join-Path $directory ([System.IO.Path]::GetRandomFileName())
    try {
        [System.IO.File]::WriteAllText($tmp, $Text, $encoding)
        if (Test-Path -LiteralPath $Path) {
            # 3 參數 Replace 需要實際的備份檔名（$null 會被轉成空字串而失敗）。
            [System.IO.File]::Replace($tmp, $Path, $backup)
        }
        else {
            [System.IO.File]::Move($tmp, $Path)
        }
    }
    finally {
        foreach ($leftover in @($tmp, $backup)) {
            if (Test-Path -LiteralPath $leftover) {
                Remove-Item -LiteralPath $leftover -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Read-TodoFile {
    param([string]$Path)

    $data = [pscustomobject]@{
        Before = New-Object System.Collections.ArrayList
        Items  = New-Object System.Collections.ArrayList
        After  = New-Object System.Collections.ArrayList
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        return $data
    }

    $lines = [System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8)
    $current = $null
    $phase = 'before'

    foreach ($line in $lines) {
        if ($line -match $HeaderPattern) {
            if ($null -ne $current) {
                [void]$data.Items.Add($current)
            }
            $current = [pscustomobject]@{
                Id       = $Matches[2]
                Done     = ($Matches[1] -ne ' ')
                Priority = $Matches[3]
                Title    = $Matches[4].Trim()
                Fields   = [ordered]@{}
                Extra    = New-Object System.Collections.ArrayList
            }
            $phase = 'items'
            continue
        }

        if ($null -ne $current) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                [void]$data.Items.Add($current)
                $current = $null
                continue
            }
            if ($line -match $DetailPattern) {
                $current.Fields[$Matches[1]] = $Matches[2].Trim()
                continue
            }
            [void]$current.Extra.Add($line.TrimEnd())
            continue
        }

        if ($phase -eq 'items' -and -not [string]::IsNullOrWhiteSpace($line)) {
            $phase = 'after'
        }
        if ($phase -eq 'after') {
            [void]$data.After.Add($line.TrimEnd())
        }
        else {
            [void]$data.Before.Add($line.TrimEnd())
        }
    }

    if ($null -ne $current) {
        [void]$data.Items.Add($current)
    }
    return $data
}

function Write-TodoFile {
    param([string]$Path, $Data)

    $out = New-Object System.Collections.ArrayList

    while ($Data.Before.Count -gt 0 -and [string]::IsNullOrWhiteSpace([string]$Data.Before[$Data.Before.Count - 1])) {
        $Data.Before.RemoveAt($Data.Before.Count - 1)
    }
    foreach ($line in $Data.Before) {
        [void]$out.Add($line)
    }
    if ($out.Count -gt 0) {
        [void]$out.Add('')
    }

    $ordered = @($Data.Items | Sort-Object { [int](($_.Id -split '-')[1]) })
    foreach ($item in $ordered) {
        $mark = ' '
        if ($item.Done) {
            $mark = 'x'
        }
        [void]$out.Add("- [$mark] $($item.Id) [$($item.Priority)] $($item.Title)")
        foreach ($key in $FieldOrder) {
            if ($item.Fields.Contains($key) -and -not [string]::IsNullOrWhiteSpace([string]$item.Fields[$key])) {
                [void]$out.Add("  - ${key}: $($item.Fields[$key])")
            }
        }
        foreach ($extra in $item.Extra) {
            [void]$out.Add($extra)
        }
    }

    while ($Data.After.Count -gt 0 -and [string]::IsNullOrWhiteSpace([string]$Data.After[0])) {
        $Data.After.RemoveAt(0)
    }
    if ($Data.After.Count -gt 0) {
        [void]$out.Add('')
        foreach ($line in $Data.After) {
            [void]$out.Add($line)
        }
    }

    if ($out.Count -gt 0) {
        Write-TodoText -Path $Path -Text (($out -join "`n") + "`n")
    }
    else {
        Write-TodoText -Path $Path -Text ''
    }
}

function Get-TodoItem {
    param($Data, [string]$TargetId)

    if ([string]::IsNullOrWhiteSpace($TargetId)) {
        throw '需要指定項目 ID，例如 TODO-0001。'
    }
    $normalized = $TargetId.Trim().ToUpperInvariant()
    $item = @($Data.Items | Where-Object { $_.Id -eq $normalized })
    if ($item.Count -eq 0) {
        throw "找不到項目 $normalized。使用 list 查看現有 ID。"
    }
    return $item[0]
}

function Format-TodoItem {
    param($Item)

    $state = 'open'
    if ($Item.Done) {
        $state = 'done'
    }
    $lines = New-Object System.Collections.ArrayList
    $mark = ' '
    if ($Item.Done) {
        $mark = 'x'
    }
    [void]$lines.Add("- [$mark] $($Item.Id) [$($Item.Priority)] $($Item.Title)")
    foreach ($key in $FieldOrder) {
        if ($Item.Fields.Contains($key) -and -not [string]::IsNullOrWhiteSpace([string]$Item.Fields[$key])) {
            [void]$lines.Add("  - ${key}: $($Item.Fields[$key])")
        }
    }
    foreach ($extra in $Item.Extra) {
        [void]$lines.Add($extra)
    }
    [void]$lines.Add("  (狀態: $state)")
    return ($lines -join [Environment]::NewLine)
}

$path = Resolve-TodoPath -Override $TodoFile

try {
    switch ($Command) {
        'path' {
            Write-Output $path
        }

        'help' {
            Get-Help $PSCommandPath -Detailed
        }

        'init' {
            if (Test-Path -LiteralPath $path) {
                Write-Output "已存在: $path"
            }
            else {
                Write-TodoText -Path $path -Text (($Template -join "`n") + "`n")
                Write-Output "已建立: $path"
            }
        }

        'add' {
            if ([string]::IsNullOrWhiteSpace($Title)) {
                throw 'add 需要 -Title。'
            }
            $data = Read-TodoFile -Path $path
            $next = 1
            if ($data.Items.Count -gt 0) {
                $max = ($data.Items | ForEach-Object { [int](($_.Id -split '-')[1]) } | Measure-Object -Maximum).Maximum
                $next = [int]$max + 1
            }
            $newPriority = 'P1'
            if (-not [string]::IsNullOrWhiteSpace($Priority)) {
                $newPriority = $Priority
            }
            $item = [pscustomobject]@{
                Id       = ('TODO-{0:D4}' -f $next)
                Done     = $false
                Priority = $newPriority
                Title    = $Title.Trim()
                Fields   = [ordered]@{}
                Extra    = New-Object System.Collections.ArrayList
            }
            if (-not [string]::IsNullOrWhiteSpace($Location)) { $item.Fields['位置'] = $Location.Trim() }
            if (-not [string]::IsNullOrWhiteSpace($Note)) { $item.Fields['說明'] = $Note.Trim() }
            if (-not [string]::IsNullOrWhiteSpace($Impact)) { $item.Fields['影響'] = $Impact.Trim() }
            if (-not [string]::IsNullOrWhiteSpace($Fix)) { $item.Fields['建議'] = $Fix.Trim() }
            $item.Fields['發現'] = (Get-Date -Format 'yyyy-MM-dd')

            [void]$data.Items.Add($item)
            Write-TodoFile -Path $path -Data $data
            Write-Output "已新增 $($item.Id): $($item.Title)"
        }

        'list' {
            $data = Read-TodoFile -Path $path
            $items = @($data.Items)
            if ($Status -ne 'all') {
                $wantDone = ($Status -eq 'done')
                $items = @($items | Where-Object { $_.Done -eq $wantDone })
            }
            if (-not [string]::IsNullOrWhiteSpace($Priority)) {
                $items = @($items | Where-Object { $_.Priority -eq $Priority })
            }

            if ($items.Count -eq 0) {
                Write-Output '沒有符合條件的項目。'
                return
            }

            if ($Json) {
                $objects = @($items | ForEach-Object {
                        [pscustomobject]@{
                            id       = $_.Id
                            status   = $(if ($_.Done) { 'done' } else { 'open' })
                            priority = $_.Priority
                            title    = $_.Title
                            location = $_.Fields['位置']
                            note     = $_.Fields['說明']
                            impact   = $_.Fields['影響']
                            fix      = $_.Fields['建議']
                            found    = $_.Fields['發現']
                            closed   = $_.Fields['完成']
                        }
                    })
                $jsonParts = @($objects | ForEach-Object { ConvertTo-Json -InputObject $_ -Depth 4 -Compress })
                Write-Output ('[' + ($jsonParts -join ',') + ']')
                return
            }

            foreach ($item in $items) {
                $state = 'open'
                if ($item.Done) {
                    $state = 'done'
                }
                Write-Output ("{0}  [{1}]  [{2}]  {3}" -f $item.Id, $item.Priority, $state, $item.Title)
            }
        }

        'show' {
            $data = Read-TodoFile -Path $path
            $item = Get-TodoItem -Data $data -TargetId $Id
            Write-Output (Format-TodoItem -Item $item)
        }

        'update' {
            $data = Read-TodoFile -Path $path
            $item = Get-TodoItem -Data $data -TargetId $Id
            $changed = New-Object System.Collections.ArrayList

            if ($PSBoundParameters.ContainsKey('Title')) {
                if ([string]::IsNullOrWhiteSpace($Title)) { throw 'Title 不可為空。' }
                $item.Title = $Title.Trim()
                [void]$changed.Add('Title')
            }
            if ($PSBoundParameters.ContainsKey('Priority')) {
                $item.Priority = $Priority
                [void]$changed.Add('Priority')
            }
            if ($PSBoundParameters.ContainsKey('Location')) {
                $item.Fields['位置'] = $Location
                [void]$changed.Add('Location')
            }
            if ($PSBoundParameters.ContainsKey('Note')) {
                $item.Fields['說明'] = $Note
                [void]$changed.Add('Note')
            }
            if ($PSBoundParameters.ContainsKey('Impact')) {
                $item.Fields['影響'] = $Impact
                [void]$changed.Add('Impact')
            }
            if ($PSBoundParameters.ContainsKey('Fix')) {
                $item.Fields['建議'] = $Fix
                [void]$changed.Add('Fix')
            }

            if ($changed.Count -eq 0) {
                throw 'update 需要至少一個欄位: -Title、-Priority、-Location、-Note、-Impact、-Fix。'
            }

            Write-TodoFile -Path $path -Data $data
            Write-Output "已更新 $($item.Id): $($changed -join ', ')"
        }

        'done' {
            $data = Read-TodoFile -Path $path
            $item = Get-TodoItem -Data $data -TargetId $Id
            $item.Done = $true
            $item.Fields['完成'] = (Get-Date -Format 'yyyy-MM-dd')
            Write-TodoFile -Path $path -Data $data
            Write-Output "已標記完成 $($item.Id)"
        }

        'reopen' {
            $data = Read-TodoFile -Path $path
            $item = Get-TodoItem -Data $data -TargetId $Id
            $item.Done = $false
            if ($item.Fields.Contains('完成')) {
                $item.Fields.Remove('完成')
            }
            Write-TodoFile -Path $path -Data $data
            Write-Output "已重新開啟 $($item.Id)"
        }

        'remove' {
            $data = Read-TodoFile -Path $path
            $item = Get-TodoItem -Data $data -TargetId $Id
            [void]$data.Items.Remove($item)
            Write-TodoFile -Path $path -Data $data
            Write-Output "已刪除 $($item.Id)"
        }
    }
}
catch {
    [Console]::Error.WriteLine("錯誤: $($_.Exception.Message)")
    exit 1
}
