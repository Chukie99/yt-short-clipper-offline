param([string]$ScriptPath = "C:\Users\SOPIAN\yt-short-clipper-offline\installer\install.ps1")
$errors = $null
$tokens = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref]$tokens, [ref]$errors)
foreach ($e in $errors) {
    $line = $e.Extent.StartLineNumber
    $text = (Get-Content $ScriptPath)[$line - 1]
    Write-Output ("LINE {0}: {1}" -f $line, $e.Message)
    Write-Output ("  CODE >>> {0}" -f $text)
    Write-Output ("  NEAR >>> {0}" -f $e.Extent.Text)
    Write-Output ""
}
Write-Output "TOTAL: $($errors.Count)"
