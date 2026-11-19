param(
  [string]$Dir = "D:\beeofficeV\_ptmp\analysis\ms-office"
)
$ErrorActionPreference = "Stop"
$report = [ordered]@{ dir=$Dir; items=@() }
function Add-Result($kind, $file, $ok, $detail) {
  $script:report.items += [ordered]@{kind=$kind; file=$file; ok=$ok; detail=$detail}
}
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $word.DisplayAlerts = 0
  $path = Join-Path $Dir "word.docx"
  try {
    $doc = $word.Documents.Open($path, $false, $true)
    $pages = $doc.ComputeStatistics(2)
    $tables = $doc.Tables.Count
    $paras = $doc.Paragraphs.Count
    Add-Result "word" $path $true "pages=$pages tables=$tables paragraphs=$paras version=$($word.Version)"
    $doc.Close($false)
  } catch { Add-Result "word" $path $false $_.Exception.Message }
  try { $word.Quit() } catch {}
} catch { if (-not ($report.items | Where-Object { $_.kind -eq "word" })) { Add-Result "word" "" $false "Word COM unavailable: $($_.Exception.Message)" } }

try {
  $excel = New-Object -ComObject Excel.Application
  $excel.Visible = $false
  $excel.DisplayAlerts = $false
  $path = Join-Path $Dir "excel.xlsx"
  try {
    $wb = $excel.Workbooks.Open($path, 0, $true)
    $sheets = $wb.Worksheets.Count
    $charts = 0
    for ($i=1; $i -le $sheets; $i++) { $charts += $wb.Worksheets.Item($i).ChartObjects().Count }
    Add-Result "excel" $path $true "sheets=$sheets charts=$charts version=$($excel.Version)"
    $wb.Close($false)
  } catch { Add-Result "excel" $path $false $_.Exception.Message }
  try { $excel.Quit() } catch {}
} catch { if (-not ($report.items | Where-Object { $_.kind -eq "excel" })) { Add-Result "excel" "" $false "Excel COM unavailable: $($_.Exception.Message)" } }

try {
  $ppt = New-Object -ComObject PowerPoint.Application
  $ppt.Visible = $true
  $path = Join-Path $Dir "ppt.pptx"
  try {
    $pres = $ppt.Presentations.Open($path, $true, $false, $false)
    $slides = $pres.Slides.Count
    $charts = 0; $tables = 0
    foreach ($slide in $pres.Slides) {
      foreach ($shape in $slide.Shapes) {
        try { if ($shape.HasChart -eq -1) { $charts++ } } catch {}
        try { if ($shape.HasTable -eq -1) { $tables++ } } catch {}
      }
    }
    Add-Result "ppt" $path $true "slides=$slides charts=$charts tables=$tables version=$($ppt.Version)"
    $pres.Close()
  } catch { Add-Result "ppt" $path $false $_.Exception.Message }
  try { $ppt.Quit() } catch {}
} catch { if (-not ($report.items | Where-Object { $_.kind -eq "ppt" })) { Add-Result "ppt" "" $false "PowerPoint COM unavailable: $($_.Exception.Message)" } }

$report | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Dir "ms-office-report.json") -Encoding UTF8
$report.items | ForEach-Object { "{0}: ok={1} {2}" -f $_.kind, $_.ok, $_.detail }
