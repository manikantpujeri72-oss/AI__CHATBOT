param([string]$ImagePath)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing

# Helper for WinRT async
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
    $_.Name -eq 'AsTask' -and 
    $_.GetParameters().Count -eq 1 -and 
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
})[0]

function Await($asyncOp, $type) {
    $m = $asTaskGeneric.MakeGenericMethod($type)
    $t = $m.Invoke($null, @($asyncOp))
    $t.Wait()
    return $t.Result
}

[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

$fileTask = [Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $ImagePath).Path)
$file = Await $fileTask ([Windows.Storage.StorageFile])

$streamTask = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
$stream = Await $streamTask ([Windows.Storage.Streams.IRandomAccessStream])

$decoderTask = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
$decoder = Await $decoderTask ([Windows.Graphics.Imaging.BitmapDecoder])

$bitmapTask = $decoder.GetSoftwareBitmapAsync()
$bitmap = Await $bitmapTask ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$ocrTask = $engine.RecognizeAsync($bitmap)
$result = Await $ocrTask ([Windows.Media.Ocr.OcrResult])

$lines = @()
foreach ($line in $result.Lines) {
    $words = @()
    foreach ($w in $line.Words) {
        $words += @{ Text = $w.Text; X = $w.BoundingRect.X; Y = $w.BoundingRect.Y; W = $w.BoundingRect.Width; H = $w.BoundingRect.Height }
    }
    $lines += @{ Text = $line.Text; Words = $words }
}

$output = @{
    Text = $result.Text
    Lines = $lines
}
$output | ConvertTo-Json -Depth 5 -Compress
