# DealForge AI — Backend Docker Restart Script
# Run this from the 'backend/' directory after updating the values below

# ========================
# SET YOUR API KEYS HERE
# ========================
$GEMINI_API_KEY = "AIzaSyCQGw_LRs4-0ydMx4U-B8ZLbrGbWLenTHY"
$MISTRAL_API_KEY = "CWk7JOnTh3YZJc1l1lVuzqI1aCE0RNed "
# Optional:
$OPENAI_API_KEY = ""

# ========================
# STOP & REMOVE OLD CONTAINER
# ========================
Write-Host "Stopping old container..." -ForegroundColor Yellow
docker stop dealforge-backend 2>&1 | Out-Null
docker rm dealforge-backend 2>&1 | Out-Null

# ========================
# START WITH ENVIRONMENT VARIABLES
# ========================
Write-Host "Starting DealForge backend..." -ForegroundColor Green
docker run -d `
  --name dealforge-backend `
  -p 8000:8000 `
  -e DATABASE_URL="sqlite+aiosqlite:///./dealforge.db" `
  -e DEBUG=true `
  -e DEFAULT_LLM_PROVIDER=gemini `
  -e PAGEINDEX_MODE=local `
  -e GEMINI_API_KEY=$GEMINI_API_KEY `
  -e MISTRAL_API_KEY=$MISTRAL_API_KEY `
  -e OPENAI_API_KEY=$OPENAI_API_KEY `
  dealforge-backend:latest

Write-Host "Waiting for startup..." -ForegroundColor Yellow
Start-Sleep 8

# ========================
# HEALTH CHECK
# ========================
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5
    Write-Host "Backend is UP! Health: $($response.Content)" -ForegroundColor Green
} catch {
    Write-Host "Backend may still be starting. Check logs with: docker logs dealforge-backend" -ForegroundColor Red
}

Write-Host ""
Write-Host "QUICK COMMANDS:" -ForegroundColor Cyan
Write-Host "  Logs: docker logs dealforge-backend -f"
Write-Host "  Stop: docker stop dealforge-backend"
Write-Host "  Shell: docker exec -it dealforge-backend bash"
