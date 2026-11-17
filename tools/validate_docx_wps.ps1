param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = "Stop"
$full = (Resolve-Path $Path).Path
$wps = New-Object -ComObject KWPS.Application
$doc = $null
try {
    $doc = $wps.Documents.Open($full, $false, $true)
    $foot = $doc.Footnotes.Count
    $end = $doc.Endnotes.Count
    Write-Host "Footnotes: $foot Endnotes: $end"
    if ($foot -le 0) { throw "未识别到脚注" }
    if ($end -le 0) { throw "未识别到尾注" }
    Write-Host "WPS_DOCX_VALIDATION_OK"
    $doc.Close($false)
    $doc = $null
} finally {
    if ($doc -ne $null) { try { $doc.Close($false) } catch {} }
    $wps.Quit()
}
