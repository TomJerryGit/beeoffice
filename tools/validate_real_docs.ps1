param([string]$Dir = "")
$ErrorActionPreference = "Stop"
if (-not $Dir) { $Dir = (Join-Path (Split-Path $PSScriptRoot -Parent) "..\analysis\real-docs") }
$Dir = (Resolve-Path $Dir).Path
$results = @()

# Word
$wordPath = Join-Path $Dir "real-word.docx"
$wps = New-Object -ComObject KWPS.Application
try {
    $doc = $wps.Documents.Open($wordPath, $false, $true)
    $results += "WORD paragraphs=$($doc.Paragraphs.Count) fields=$($doc.Fields.Count) footnotes=$($doc.Footnotes.Count) endnotes=$($doc.Endnotes.Count)"
    $doc.Close($false)
} finally { $wps.Quit() }

# Excel
$excelPath = Join-Path $Dir "real-excel.xlsx"
$ket = New-Object -ComObject KET.Application
try {
    $wb = $ket.Workbooks.Open($excelPath, 0, $true)
    $ws = $wb.Worksheets.Item(1)
    $results += "EXCEL sheets=$($wb.Worksheets.Count) lastRow=$($ws.UsedRange.Rows.Count) printArea=$($ws.PageSetup.PrintArea)"
    $wb.Close($false)
} finally { $ket.Quit() }

# PowerPoint
$pptPath = Join-Path $Dir "real-ppt.pptx"
$wpp = New-Object -ComObject KWPP.Application
try {
    $pres = $wpp.Presentations.Open($pptPath, $false, $false, $false)
    $anim = 0
    for ($i = 1; $i -le $pres.Slides.Count; $i++) { $anim += $pres.Slides.Item($i).TimeLine.MainSequence.Count }
    $results += "PPT slides=$($pres.Slides.Count) animations=$anim"
    $pres.Close()
} finally { $wpp.Quit() }

$results | ForEach-Object { Write-Host $_ }
Write-Host "REAL_DOCS_VALIDATION_OK"
