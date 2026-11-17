param([string]$Dir = "")
$ErrorActionPreference = "Stop"
if (-not $Dir) { $Dir = (Join-Path (Split-Path $PSScriptRoot -Parent) "..\analysis\enterprise-templates") }
$Dir = (Resolve-Path $Dir).Path

# Word
$wps = New-Object -ComObject KWPS.Application
try {
    $doc = $wps.Documents.Open((Join-Path $Dir "enterprise-word-output.docx"), $false, $true)
    Write-Host "WORD paragraphs=$($doc.Paragraphs.Count) tables=$($doc.Tables.Count) header=$($doc.Sections.Item(1).Headers.Item(1).Range.Text.Trim())"
    $doc.Close($false)
} finally { $wps.Quit() }

# Excel
$ket = New-Object -ComObject KET.Application
try {
    $wb = $ket.Workbooks.Open((Join-Path $Dir "enterprise-excel-output.xlsx"), 0, $true)
    $ws = $wb.Worksheets.Item(1)
    $formulaCount = 0
    try { $formulaCount = $ws.Cells.SpecialCells(-4123).Count } catch {}
    Write-Host "EXCEL sheets=$($wb.Worksheets.Count) merged=$($ws.UsedRange.MergeCells) printArea=$($ws.PageSetup.PrintArea) formulas=$formulaCount"
    $wb.Close($false)
} finally { $ket.Quit() }

# PowerPoint
$wpp = New-Object -ComObject KWPP.Application
try {
    $pres = $wpp.Presentations.Open((Join-Path $Dir "enterprise-ppt-output.pptx"), $false, $false, $false)
    $anim = 0
    for ($i = 1; $i -le $pres.Slides.Count; $i++) { $anim += $pres.Slides.Item($i).TimeLine.MainSequence.Count }
    Write-Host "PPT slides=$($pres.Slides.Count) animations=$anim"
    $pres.Close()
} finally { $wpp.Quit() }

Write-Host "ENTERPRISE_TEMPLATE_VALIDATION_OK"
