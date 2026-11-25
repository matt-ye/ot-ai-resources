# validate_md_write.ps1 - PostToolUse hook: validate .md files after Write/Edit.
# ASCII-only by design (PS 5.1 parses BOM-less files as ANSI; Chinese vocab lives in md_schema.json).
# Exit 0 = pass or not applicable. Exit 2 = validation issues (stderr is fed back to the agent).
# On internal script errors: fail-open (exit 0) so a validator bug never blocks vault work.

param(
    [string]$TestJson = '',
    [string]$VaultRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# Report in UTF-8 too: PS 5.1 writes stderr in the OEM code page (cp950), so Chinese paths in the
# messages fed back to the agent showed up garbled. AutoFlush because we exit right after writing.
$utf8Err = New-Object IO.StreamWriter([Console]::OpenStandardError(), (New-Object Text.UTF8Encoding($false)))
$utf8Err.AutoFlush = $true
[Console]::SetError($utf8Err)

try {
    # ---- 1. Get tool payload (stdin JSON from the hook, or -TestJson for self-test) ----
    if ($TestJson) { $raw = $TestJson } else {
        # Claude Code sends UTF-8; Windows PowerShell 5.1 would decode stdin with the OEM code page
        # (cp950), garbling non-ASCII paths so every card in a Chinese folder silently passed.
        $reader = New-Object IO.StreamReader([Console]::OpenStandardInput(), (New-Object Text.UTF8Encoding($false)))
        $raw = $reader.ReadToEnd()
    }
    if (-not $raw) { exit 0 }
    # Harness bug guard (claude-code#20015 / plugins#1211): on Windows the hook payload
    # occasionally arrives with unescaped backslash paths = malformed JSON. That is
    # expected environmental noise, not a validator bug - swallow it silently
    # (no stderr; a skipped validation is better than error spam in every session).
    try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }
    $fp = $payload.tool_input.file_path
    if (-not $fp) { exit 0 }
    if ($fp -notmatch '\.md$') { exit 0 }

    # Only validate files inside the vault
    $fpFull = [IO.Path]::GetFullPath($fp)
    $rootFull = [IO.Path]::GetFullPath($VaultRoot)
    if (-not $fpFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) { exit 0 }
    if (-not (Test-Path -LiteralPath $fpFull)) { exit 0 }

    $rel = $fpFull.Substring($rootFull.Length).TrimStart('\')
    $segments = $rel -split '\\'

    # Skip vault-internal machinery entirely
    foreach ($skipDir in @('.obsidian', '.git', '.trash', '.claude')) {
        if ($segments -contains $skipDir) { exit 0 }
    }
    # Archive/snapshot dirs (leading underscore): only basic hygiene checks, no schema/wikilink checks
    $isArchive = $false
    foreach ($seg in $segments) { if ($seg.StartsWith('_')) { $isArchive = $true } }

    $issues = New-Object System.Collections.Generic.List[string]

    # ---- 2. Byte-level checks ----
    $bytes = [IO.File]::ReadAllBytes($fpFull)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $issues.Add('BOM detected. Vault rule: .md files must be UTF-8 WITHOUT BOM.')
    }
    $text = [Text.Encoding]::UTF8.GetString($bytes)
    if ($bytes.Length -gt 0 -and -not $text.EndsWith("`n")) {
        $issues.Add('File does not end with a newline.')
    }

    # ---- 2b. Invisible control characters ----
    # Root cause seen in practice: a Python writer used a non-raw string containing a
    # Windows path, so '\b' in '.local\bin' became BACKSPACE and '\v' in 'scripts\vram'
    # became VERTICAL TAB. The file looks almost correct on screen but the path is broken.
    # TAB/LF/CR are legitimate in Markdown and are NOT flagged.
    $ctrlNames = @{
        0 = 'NUL'; 1 = 'SOH'; 2 = 'STX'; 3 = 'ETX'; 4 = 'EOT'; 5 = 'ENQ'; 6 = 'ACK'
        7 = 'BEL (\a)'; 8 = 'BACKSPACE (\b)'; 11 = 'VERTICAL TAB (\v)'; 12 = 'FORM FEED (\f)'
        14 = 'SO'; 15 = 'SI'; 16 = 'DLE'; 17 = 'DC1'; 18 = 'DC2'; 19 = 'DC3'; 20 = 'DC4'
        21 = 'NAK'; 22 = 'SYN'; 23 = 'ETB'; 24 = 'CAN'; 25 = 'EM'; 26 = 'SUB'
        27 = 'ESC (\e)'; 28 = 'FS'; 29 = 'GS'; 30 = 'RS'; 31 = 'US'; 127 = 'DEL'
    }
    $ctrlHits = [regex]::Matches($text, '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
    if ($ctrlHits.Count -gt 0) {
        $shown = 0
        foreach ($ch in $ctrlHits) {
            if ($shown -ge 5) { break }
            $code = [int][char]$ch.Value
            $name = $ctrlNames[$code]
            if (-not $name) { $name = 'control char' }
            $lineNo = ($text.Substring(0, $ch.Index) -split "`n").Count
            # Show the surrounding text so the broken path is easy to spot
            $from = [Math]::Max(0, $ch.Index - 25)
            $len = [Math]::Min(50, $text.Length - $from)
            $ctx = $text.Substring($from, $len) -replace '[\x00-\x1F\x7F]', '?'
            # NOTE: the -f expression MUST be wrapped in its own parentheses. Inside a
            # method call, PowerShell treats commas as argument separators, so
            # $list.Add("..." -f $a, $b) would pass $b to Add() and starve the format string.
            $msg = ('Invisible control character 0x{0:X2} {1} at line {2}. Context: ...{3}... -- almost always a non-raw Python string containing a Windows path; rewrite with r"..." or double the backslashes (see the decision log).' -f $code, $name, $lineNo, $ctx.Trim())
            $issues.Add($msg)
            $shown++
        }
        if ($ctrlHits.Count -gt $shown) {
            $issues.Add("... and $($ctrlHits.Count - $shown) more control character(s) in this file.")
        }
    }

    # ---- 3. Conflict markers ('=======' alone is skipped: setext headings look the same) ----
    if ($text -match '(?m)^(<{7}( |$)|>{7}( |$))') {
        $issues.Add('Git conflict markers (<<<<<<< or >>>>>>>) found in file.')
    }

    $lines = $text -replace "`r`n", "`n" -split "`n"

    # ---- 4. Frontmatter parse + duplicate top-level keys ----
    $fmKeys = @()
    $hasFrontmatter = $false
    if ($lines.Length -gt 0 -and $lines[0].TrimEnd() -eq '---') {
        $closed = $false
        for ($i = 1; $i -lt $lines.Length; $i++) {
            $t = $lines[$i].TrimEnd()
            if ($t -eq '---' -or $t -eq '...') { $closed = $true; break }
            if ($lines[$i] -match '^([A-Za-z_][A-Za-z0-9_-]*)\s*:') { $fmKeys += $Matches[1] }
        }
        if (-not $closed) {
            $issues.Add('Frontmatter block opened with --- but never closed.')
        } else {
            $hasFrontmatter = $true
            $dups = $fmKeys | Group-Object | Where-Object { $_.Count -gt 1 }
            foreach ($d in $dups) { $issues.Add("Duplicate frontmatter key: '$($d.Name)'.") }
        }
    }

    # ---- 5. Card schema (cards/ only, non-archive) ----
    if (-not $isArchive -and $segments[0] -eq 'cards') {
        $schemaPath = Join-Path $rootFull 'scripts\md_schema.json'
        if (Test-Path -LiteralPath $schemaPath) {
            $schema = [IO.File]::ReadAllText($schemaPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
            if (-not $hasFrontmatter) {
                $issues.Add('Card has no frontmatter. Required keys: ' + ($schema.card_required_keys -join ', ') + '.')
            } else {
                foreach ($k in $schema.card_required_keys) {
                    if ($fmKeys -notcontains $k) { $issues.Add("Card frontmatter missing required key: '$k'.") }
                }
                # ip value must be in controlled vocabulary
                foreach ($ln in $lines) {
                    if ($ln -match '^ip\s*:\s*(.+)$') {
                        $val = $Matches[1].Trim().Trim('"').Trim("'")
                        if ($schema.ip_values -notcontains $val) {
                            $issues.Add("Card 'ip' value '$val' is not in the controlled vocabulary: " + ($schema.ip_values -join ' | ') + '.')
                        }
                        break
                    }
                }
            }
        }
    }

    # ---- 6. Wikilink resolution (non-archive vault files) ----
    if (-not $isArchive) {
        # Build filename index (basenames, and full names with extension for attachments)
        $mdIndex = @{}
        $anyIndex = @{}
        Get-ChildItem -LiteralPath $rootFull -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\(\.git|\.obsidian|\.trash|node_modules)\\' } |
            ForEach-Object {
                $anyIndex[$_.Name.ToLowerInvariant()] = $true
                if ($_.Extension -eq '.md' -or $_.Extension -eq '.base' -or $_.Extension -eq '.canvas') {
                    $mdIndex[[IO.Path]::GetFileNameWithoutExtension($_.Name).ToLowerInvariant()] = $true
                }
            }

        $inFence = $false
        $broken = New-Object System.Collections.Generic.List[string]
        foreach ($ln in $lines) {
            if ($ln -match '^\s*(```|~~~)') { $inFence = -not $inFence; continue }
            if ($inFence) { continue }
            foreach ($m in [regex]::Matches($ln, '\[\[([^\[\]]+?)\]\]')) {
                $target = $m.Groups[1].Value
                $target = ($target -split '\|')[0]
                $target = ($target -split '#')[0]
                $target = ($target -split '\^')[0]
                $target = $target.Trim()
                if (-not $target) { continue }
                $leaf = ($target -split '/')[-1].Trim()
                if ($leaf -match '\.[A-Za-z0-9]{2,5}$') {
                    if (-not $anyIndex.ContainsKey($leaf.ToLowerInvariant())) { $broken.Add($target) }
                } else {
                    if (-not $mdIndex.ContainsKey($leaf.ToLowerInvariant())) { $broken.Add($target) }
                }
            }
        }
        $brokenUnique = $broken | Sort-Object -Unique
        foreach ($b in $brokenUnique) {
            $issues.Add("Broken wikilink: [[${b}]] (no matching file in vault). Fix the link, or if it is an intentional future link, state so explicitly.")
        }
    }

    # ---- 7. Verdict ----
    if ($issues.Count -gt 0) {
        [Console]::Error.WriteLine("md-validator: $rel has $($issues.Count) issue(s):")
        foreach ($it in $issues) { [Console]::Error.WriteLine(' - ' + $it) }
        exit 2
    }
    exit 0
}
catch {
    # Fail-open: a validator bug must never block vault work.
    [Console]::Error.WriteLine('md-validator internal error (fail-open, not blocking): ' + $_.Exception.Message)
    exit 0
}
