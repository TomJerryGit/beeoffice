param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Path)) { throw "文件不存在: $Path" }
$wps = New-Object -ComObject KWPP.Application
try {
    $pres = $wps.Presentations.Open((Resolve-Path $Path), $false, $false, $false)
    $ok = $true
    Write-Host "Slides: $($pres.Slides.Count)"
    for ($i = 1; $i -le $pres.Slides.Count; $i++) {
        $slide = $pres.Slides.Item($i)
        $trans = $slide.SlideShowTransition.EntryEffect
        $anim = $slide.TimeLine.MainSequence.Count
        Write-Host "Slide $i transition=$trans animations=$anim"
        if ($anim -le 0) { $ok = $false }
    }
    $pres.Close()
    if (-not $ok) { throw "至少一页没有识别到动画" }
    Write-Host "WPS_VALIDATION_OK"
} finally {
    $wps.Quit()
}
