# PowerShell script to grant SharePoint access to app
# Run this in PowerShell with SharePoint PnP module installed

$SiteUrl = "https://honnimar.sharepoint.com/sites/DemoISM"
$AppId = "3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9"

Write-Host "Granting SharePoint access to app..." -ForegroundColor Cyan
Write-Host "Site: $SiteUrl" -ForegroundColor Yellow
Write-Host "App ID: $AppId" -ForegroundColor Yellow

# First, connect to SharePoint
try {
    Connect-PnPOnline -Url $SiteUrl -Interactive
    Write-Host "✅ Connected to SharePoint" -ForegroundColor Green
    
    # Grant full control to the app
    Set-PnPAzureADAppSitePermission -AppId $AppId -Permissions FullControl
    Write-Host "✅ Granted Full Control permission to app" -ForegroundColor Green
    
    # Verify the permission
    $permissions = Get-PnPAzureADAppSitePermission
    Write-Host "`n📋 Current app permissions:" -ForegroundColor Cyan
    $permissions | Format-Table DisplayName, AppId, Permissions
    
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
    Write-Host "`nManual steps:" -ForegroundColor Yellow
    Write-Host "1. Go to: $SiteUrl/_layouts/15/user.aspx"
    Write-Host "2. Click 'Grant Permissions'"
    Write-Host "3. Enter: $AppId"
    Write-Host "4. Select 'Full Control'"
    Write-Host "5. Click 'Share'"
}