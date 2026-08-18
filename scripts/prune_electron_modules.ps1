#Requires -Version 5.1
<#
.SYNOPSIS
  删除已同步到 renderer/vendor 的 npm 包，安装包内仅保留 electron 运行时及其传递依赖。
#>
param(
    [Parameter(Mandatory)]
    [string]$ElectronDir
)

$ErrorActionPreference = "Stop"
$nm = Join-Path $ElectronDir "node_modules"
if (-not (Test-Path $nm)) {
    Write-Warning "无 node_modules: $nm"
    return
}

function Get-PackageDeps([string]$PkgDir) {
    $pkgJson = Join-Path $PkgDir "package.json"
    if (-not (Test-Path $pkgJson)) { return @() }
    try {
        $j = Get-Content $pkgJson -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return @()
    }
    $names = @()
    foreach ($section in @("dependencies", "optionalDependencies")) {
        $obj = $j.$section
        if (-not $obj) { continue }
        $obj.PSObject.Properties | ForEach-Object { $names += $_.Name }
    }
    return $names
}

# 已由 sync-*.mjs 拷入 renderer/vendor，运行时不再需要这些包及其依赖树
$dropExact = @(
    "@file-viewer",
    "@toast-ui",
    "d3",
    "marked"
)

foreach ($name in $dropExact) {
    $p = Join-Path $nm $name
    if (Test-Path $p) {
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  drop $name"
    }
}

# file-viewer / 编辑器传递依赖（vendor IIFE 已自包含，electron 本体不需要）
# 例外：mermaid / pdfjs-dist / three — 开发与预览链路仍可能直接引用，安装包亦保留
$keepHeavy = @("mermaid", "pdfjs-dist", "three")
$dropHeavyOrphans = @(
    "sql.js", "ag-psd", "epubjs",
    "maplibre-gl", "cytoscape", "cytoscape-fcose", "billboard.js",
    "highlight.js", "katex", "lodash", "lodash-es", "core-js",
    "dayjs", "hls.js", "jszip", "pako", "proj4", "rtf.js",
    "styled-exceljs", "diff", "diff2html", "e-virt-table",
    "dagre-d3-es", "khroma", "uuid", "comlink", "global-agent",
    "es-toolkit", "es5-ext", "type", "codepage", "iconv-lite",
    "dompurify", "isomorphic-dompurify", "parse5",
    "prosemirror-commands", "prosemirror-history", "prosemirror-inputrules",
    "prosemirror-keymap", "prosemirror-model", "prosemirror-state",
    "prosemirror-transform", "prosemirror-view",
    "orderedmap", "w3c-keyname", "rope-sequence", "crelt",
    "domino", "html-encoding-sniffer",
    "whatwg-mimetype", "whatwg-url", "tr46", "webidl-conversions", "entities",
    "cssom", "cssstyle", "nwsapi", "symbol-tree", "saxes", "xmlchars",
    "safer-buffer", "commander", "mdurl", "uc.micro", "linkify-it",
    "punycode", "internmap", "delaunator", "robust-predicates"
)

foreach ($name in $dropHeavyOrphans) {
    if ($keepHeavy -contains $name) { continue }
    $p = Join-Path $nm $name
    if (Test-Path $p) {
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  drop $name"
    }
}

# 作用域包：file-viewer 生态，非 electron 运行时
$dropScopedPrefixes = @(
    "@napi-rs", "@myriaddreamin", "@mlightcad", "@maplibre",
    "@iconify", "@profoundlogic", "@types"
)

Get-ChildItem -Path $nm -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $n = $_.Name
    if ($n -like "d3-*") {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  drop $n"
        return
    }
    if ($n.StartsWith("@")) {
        foreach ($prefix in $dropScopedPrefixes) {
            if ($n -eq $prefix -or $n.StartsWith("$prefix\")) {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  drop $n"
                break
            }
        }
        # 也删整个 scope 目录下的子包（npm 扁平：@scope 是目录）
        if ($dropScopedPrefixes -contains $n) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "  drop scope $n"
        }
    }
}

# 仅保留 electron 及其 package.json 声明的依赖闭包（BFS）
$keep = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$queue = New-Object System.Collections.Generic.Queue[string]
[void]$keep.Add("electron")
$queue.Enqueue("electron")
# 显式保留预览链路常用包（勿被 orphan 清扫删掉）
foreach ($k in @("mermaid", "pdfjs-dist", "three")) {
    [void]$keep.Add($k)
}

while ($queue.Count -gt 0) {
    $cur = $queue.Dequeue()
    $rel = $cur -replace "/", [IO.Path]::DirectorySeparatorChar
    $dir = Join-Path $nm $rel
    if (-not (Test-Path $dir)) {
        continue
    }
    foreach ($dep in (Get-PackageDeps $dir)) {
        if ($keep.Add($dep)) {
            $queue.Enqueue($dep)
        }
    }
}

Get-ChildItem -Path $nm -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $n = $_.Name
    if ($keep.Contains($n)) { return }
    # scoped packages live as @scope/name — keep if full name in set
    if ($n.StartsWith("@")) {
        $scopedKeep = $false
        Get-ChildItem -Path $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $full = "$n/$($_.Name)"
            if ($keep.Contains($full)) {
                $scopedKeep = $true
            } else {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  drop orphan $full"
            }
        }
        # 若 scope 下已空则删 scope 目录
        $left = @(Get-ChildItem -Path $_.FullName -Force -ErrorAction SilentlyContinue)
        if (-not $scopedKeep -or $left.Count -eq 0) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "  drop scope $n"
        }
        return
    }
    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  drop orphan $n"
}

# Electron 语言包：只留中英
$locales = Join-Path $nm "electron\dist\locales"
if (Test-Path $locales) {
    Get-ChildItem $locales -Filter "*.pak" -File -ErrorAction SilentlyContinue | ForEach-Object {
        $keepLocales = @("en-US.pak", "zh-CN.pak", "zh-TW.pak")
        if ($keepLocales -notcontains $_.Name) {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "  electron locales → en/zh only"
}

# 开发脚本与类型定义
# 注意：不可删除 electron\dist\resources\default_app.asar
foreach ($d in @("@types")) {
    $p = Join-Path $nm $d
    if (Test-Path $p) {
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "electron node_modules 精简完成（A5：仅保留 electron 依赖闭包）"
