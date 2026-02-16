# FINAL PowerShell script to grant SharePoint access using correct Object ID

$SiteUrl = "https://honnimar.sharepoint.com/sites/DemoISM"
$AppObjectId = "ee2feebc-97c2-4bf1-9665-4a55caec9bb5"  # Service Principal Object ID
$AppDisplayName = "HM-SharepointBackup"

Write-Host "🔧 FINAL SharePoint Access Grant Script" -ForegroundColor Cyan
Write-Host "="*80 -ForegroundColor Cyan
Write-Host "Site: $SiteUrl" -ForegroundColor Yellow
Write-Host "App Object ID: $AppObjectId" -ForegroundColor Yellow
Write-Host "App Display Name: $AppDisplayName" -ForegroundColor Yellow

Write-Host "`n📋 MANUAL STEPS (Try in Order):" -ForegroundColor Green
Write-Host "="*80 -ForegroundColor Green

Write-Host "1. Try this EXACT format in SharePoint 'Grant Permissions':" -ForegroundColor White
Write-Host "   i:0#.f|membership|3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9" -ForegroundColor Yellow

Write-Host "`n2. If that fails, try just the Object ID:" -ForegroundColor White
Write-Host "   ee2feebc-97c2-4bf1-9665-4a55caec9bb5" -ForegroundColor Yellow

Write-Host "`n3. If that fails, try the App Display Name:" -ForegroundColor White
Write-Host "   HM-SharepointBackup" -ForegroundColor Yellow

Write-Host "`n4. Last resort: Use SharePoint Admin Center" -ForegroundColor White
Write-Host "   Go to: https://honnimar-admin.sharepoint.com" -ForegroundColor Yellow
Write-Host "   → Sites → Active sites → DemoISM" -ForegroundColor Yellow
Write-Host "   → Permissions → Add members" -ForegroundColor Yellow
Write-Host "   → Enter: 3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9" -ForegroundColor Yellow

Write-Host "`n" + "="*80 -ForegroundColor Cyan
Write-Host "⚠️  TROUBLESHOOTING:" -ForegroundColor Red
Write-Host "="*80 -ForegroundColor Red

Write-Host "If NOTHING works, the site might be:" -ForegroundColor White
Write-Host "1. A Private Teams channel site" -ForegroundColor Yellow
Write-Host "2. Not accessible via app-only auth" -ForegroundColor Yellow
Write-Host "3. Requires user delegation instead of app-only" -ForegroundColor Yellow

Write-Host "`n" + "="*80 -ForegroundColor Cyan
Write-Host "WORKAROUND SOLUTION:" -ForegroundColor Green
Write-Host "="*80 -ForegroundColor Green

Write-Host "Create a test user and use user credentials instead:" -ForegroundColor White
Write-Host "1. Create user in Azure AD: 'sharepoint-backup-user@honnimar.onmicrosoft.com'" -ForegroundColor Yellow
Write-Host "2. Grant user access to SharePoint site" -ForegroundColor Yellow
Write-Host "3. Update .env.sharepoint with user credentials:" -ForegroundColor Yellow
Write-Host "   SHAREPOINT_USERNAME=sharepoint-backup-user@honnimar.onmicrosoft.com" -ForegroundColor Yellow
Write-Host "   SHAREPOINT_PASSWORD=YourPassword123" -ForegroundColor Yellow
Write-Host "4. Update sharepoint_backup.py to use user auth" -ForegroundColor Yellow

Write-Host "`n" + "="*80 -ForegroundColor Cyan
Write-Host "TEST COMMAND AFTER FIX:" -ForegroundColor Green
Write-Host "="*80 -ForegroundColor Green
Write-Host "uv run --env-file .env.sharepoint python quick_sharepoint_test.py" -ForegroundColor Yellow