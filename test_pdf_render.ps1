param([string]$PdfPath, [int]$PageIndex, [string]$OutPath)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
    $_.Name -eq 'AsTask' -and 
    $_.GetParameters().Count -eq 1 -and 
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
})[0]

$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
    $_.Name -eq 'AsTask' -and 
    $_.GetParameters().Count -eq 1 -and 
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' 
})[0]

function AwaitOp($asyncOp, $type) {
    $m = $asTaskGeneric.MakeGenericMethod($type)
    $t = $m.Invoke($null, @($asyncOp))
    $t.Wait()
    return $t.Result
}

function AwaitAct($asyncAct) {
    $t = $asTaskAction.Invoke($null, @($asyncAct))
    $t.Wait()
}

[Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.FileAccessMode, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

$fileTask = [Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $PdfPath).Path)
$file = AwaitOp $fileTask ([Windows.Storage.StorageFile])

$docTask = [Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)
$doc = AwaitOp $docTask ([Windows.Data.Pdf.PdfDocument])
Write-Host "PDF Pages: $($doc.PageCount)"

$page = $doc.GetPage($PageIndex)
$outFile = [Windows.Storage.StorageFile]::GetFileFromPathAsync((New-Item -Path $OutPath -ItemType File -Force).FullName)
$outStorage = AwaitOp $outFile ([Windows.Storage.StorageFile])

$streamTask = $outStorage.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)
$stream = AwaitOp $streamTask ([Windows.Storage.Streams.IRandomAccessStream])

$renderTask = $page.RenderToStreamAsync($stream)
AwaitAct $renderTask

$flushTask = $stream.FlushAsync()
AwaitOp $flushTask ([bool])
$stream.Dispose()

Write-Host "Successfully rendered page $PageIndex to $OutPath"
