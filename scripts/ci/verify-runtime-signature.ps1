param([Parameter(Mandatory = $true)][string]$Path)
$ErrorActionPreference = 'Stop'
$signature = Get-AuthenticodeSignature -LiteralPath $Path
if ($signature.Status -ne 'Valid') {
    throw "Python Authenticode signature is not valid: $($signature.Status)"
}
$signer = $signature.SignerCertificate.GetNameInfo(
    [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
if ($signer -ne 'Python Software Foundation') {
    throw "Unexpected Python Authenticode signer: $signer"
}
[pscustomobject]@{
    status = $signature.Status.ToString()
    signer = $signer
    certificate_sha1 = $signature.SignerCertificate.Thumbprint
} | ConvertTo-Json -Compress
