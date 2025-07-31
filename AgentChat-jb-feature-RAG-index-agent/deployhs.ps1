# Azure App Service Deployment Script with Custom Pip Repository Support
# PowerShell version for Windows with High Security (HS) requirements

param(
    [string]$AppName = "",
    [string]$ResourceGroup = "",
    [string]$Location = "East US",
    [string]$PythonVersion = "3.13",
    [string]$CustomPipIndex = "",
    [string[]]$TrustedHosts = @(),
    [string]$CustomPipConfig = "",
    [switch]$UseCustomSSLRoots = $false,
    [string]$SSLCertPath = ""
)

# Color functions for output
function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Blue }
function Write-Success { param([string]$Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warning { param([string]$Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-Error { param([string]$Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# Function to check prerequisites
function Test-Prerequisites {
    Write-Info "Checking prerequisites for High Security deployment..."
    
    # Check if Angular CLI is installed
    if (!(Get-Command ng -ErrorAction SilentlyContinue)) {
        Write-Error "Angular CLI is not installed. Please install it with: npm install -g @angular/cli"
        exit 1
    }
    
    # Check if Azure CLI is installed
    if (!(Get-Command az -ErrorAction SilentlyContinue)) {
        Write-Error "Azure CLI is not installed. Please install it from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
        exit 1
    }
    
    # Check if user is logged in to Azure
    try {
        az account show --query "name" --output tsv | Out-Null
    }
    catch {
        Write-Error "You are not logged in to Azure. Please run: az login"
        exit 1
    }
    
    # Check for SSL certificate if specified
    if ($UseCustomSSLRoots -and $SSLCertPath) {
        if (!(Test-Path $SSLCertPath)) {
            Write-Error "SSL certificate path not found: $SSLCertPath"
            exit 1
        }
        Write-Success "Custom SSL certificate found at: $SSLCertPath"
    }
    
    # Check for running processes that might interfere with npm
    $nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue
    $esbuildProcesses = Get-Process -Name "esbuild" -ErrorAction SilentlyContinue
    
    if ($nodeProcesses -or $esbuildProcesses) {
        Write-Warning "Found running Node.js or esbuild processes that might interfere with npm install."
        $response = Read-Host "Do you want to stop these processes? (y/N)"
        if ($response -eq "y" -or $response -eq "Y") {
            Write-Info "Stopping interfering processes..."
            $nodeProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
            $esbuildProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    }
    
    Write-Success "Prerequisites check passed!"
}

# Function to get deployment configuration with HS requirements
function Get-DeploymentConfigHS {
    Write-Info "Setting up High Security deployment configuration..."
    
    if ([string]::IsNullOrEmpty($AppName)) {
        $AppName = Read-Host "Enter your Azure App Service name"
    }
    
    if ([string]::IsNullOrEmpty($ResourceGroup)) {
        $ResourceGroup = Read-Host "Enter your Azure Resource Group name"
    }
    
    # Get custom pip configuration if not provided
    if ([string]::IsNullOrEmpty($CustomPipIndex)) {
        Write-Info "Custom pip index configuration:"
        $hasCustomRepo = Read-Host "Do you use a custom pip repository? (y/N)"
        if ($hasCustomRepo -eq "y" -or $hasCustomRepo -eq "Y") {
            $CustomPipIndex = Read-Host "Enter your custom pip index URL (e.g., https://pypi.company.com/simple/)"
            
            # Get trusted hosts
            if ($TrustedHosts.Count -eq 0) {
                Write-Info "Enter trusted hosts (comma-separated, press Enter when done):"
                $trustedInput = Read-Host "Trusted hosts"
                if (![string]::IsNullOrEmpty($trustedInput)) {
                    $TrustedHosts = $trustedInput.Split(',') | ForEach-Object { $_.Trim() }
                }
            }
            
            # Ask about SSL certificates
            $sslResponse = Read-Host "Do you need custom SSL root certificates? (y/N)"
            if ($sslResponse -eq "y" -or $sslResponse -eq "Y") {
                $UseCustomSSLRoots = $true
                if ([string]::IsNullOrEmpty($SSLCertPath)) {
                    $SSLCertPath = Read-Host "Enter path to SSL certificate bundle (optional)"
                }
            }
        }
    }
    
    Write-Host ""
    Write-Info "High Security Deployment Configuration:"
    Write-Host "  App Name: $AppName"
    Write-Host "  Resource Group: $ResourceGroup"
    Write-Host "  Location: $Location"
    Write-Host "  Python Version: $PythonVersion"
    Write-Host "  Custom Pip Index: $CustomPipIndex"
    Write-Host "  Trusted Hosts: $($TrustedHosts -join ', ')"
    Write-Host "  Use Custom SSL: $UseCustomSSLRoots"
    Write-Host "  SSL Cert Path: $SSLCertPath"
    Write-Host ""
    
    $confirm = Read-Host "Continue with deployment? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Warning "Deployment cancelled by user"
        exit 0
    }
    
    return @{
        AppName = $AppName
        ResourceGroup = $ResourceGroup
        Location = $Location
        PythonVersion = $PythonVersion
        CustomPipIndex = $CustomPipIndex
        TrustedHosts = $TrustedHosts
        UseCustomSSLRoots = $UseCustomSSLRoots
        SSLCertPath = $SSLCertPath
    }
}

# Function to create pip configuration for high security deployment
function New-PipConfiguration {
    param([hashtable]$Config)
    
    Write-Info "Creating pip configuration for high security deployment..."
    
    # Create pip.conf content
    $pipConfContent = @"
[global]
"@
    
    # Add custom index if specified
    if (![string]::IsNullOrEmpty($Config.CustomPipIndex)) {
        $pipConfContent += @"
index-url = $($Config.CustomPipIndex)
"@
    }
    
    # Add trusted hosts
    if ($Config.TrustedHosts.Count -gt 0) {
        $trustedHostsString = $Config.TrustedHosts -join ' '
        $pipConfContent += @"
trusted-host = $trustedHostsString
"@
    }
    
    # Create pip.conf file in PythonAPI directory
    $pipConfPath = "PythonAPI\pip.conf"
    $pipConfContent | Out-File -FilePath $pipConfPath -Encoding UTF8 -Force
    
    Write-Success "Created pip configuration at: $pipConfPath"
    Write-Info "Pip configuration content:"
    Get-Content $pipConfPath | ForEach-Object { Write-Host "  $_" }
    
    return $pipConfPath
}

# Function to create custom requirements.txt with pip arguments
function New-CustomRequirements {
    param([hashtable]$Config)
    
    Write-Info "Creating deployment requirements.txt with custom pip settings..."
    
    # Read original requirements
    $originalReqs = Get-Content "PythonAPI\requirements.txt"
    
    # Create deployment-specific requirements
    $deployReqsPath = "PythonAPI\requirements-deploy.txt"
    $deployContent = @()
    
    # Add pip upgrade commands with trusted hosts
    if ($Config.TrustedHosts.Count -gt 0) {
        $trustedArgs = $Config.TrustedHosts | ForEach-Object { "--trusted-host $_" }
        $trustedString = $trustedArgs -join ' '
        
        # Add comment explaining the deployment requirements
        $deployContent += "# Deployment requirements with custom pip configuration"
        $deployContent += "# Use: pip install $trustedString -r requirements-deploy.txt"
        if (![string]::IsNullOrEmpty($Config.CustomPipIndex)) {
            $deployContent += "# Custom index: $($Config.CustomPipIndex)"
        }
        $deployContent += ""
    }
    
    # Copy original requirements
    $deployContent += $originalReqs
    
    # Write deployment requirements
    $deployContent | Out-File -FilePath $deployReqsPath -Encoding UTF8 -Force
    
    Write-Success "Created deployment requirements at: $deployReqsPath"
    
    return $deployReqsPath
}

# Function to build Angular application
function Build-Angular {
    Write-Info "Building Angular application..."
    
    # Check if node_modules exists and try to clean it if npm ci fails
    Write-Info "Preparing npm environment..."
    
    # First attempt: npm ci (fastest, uses existing package-lock.json)
    Write-Info "Installing npm dependencies..."
    npm ci
    
    # If npm ci fails, try alternative approaches
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "npm ci failed, trying alternative approaches..."
        
        # Try to kill any running node processes
        Write-Info "Stopping any running Node.js processes..."
        Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Get-Process -Name "esbuild" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        
        # Wait a moment for processes to stop
        Start-Sleep -Seconds 2
        
        # Try npm ci again
        Write-Info "Retrying npm ci..."
        npm ci
        
        # If still failing, try npm install with force
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "npm ci still failing, trying npm install --force..."
            npm install --force
            
            if ($LASTEXITCODE -ne 0) {
                Write-Error "All npm install attempts failed. Please resolve npm issues manually."
                exit 1
            }
        }
    }
    
    Write-Success "npm dependencies installed successfully!"
    
    # Build Angular for production
    Write-Info "Building Angular for production..."
    ng build --configuration=production
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Angular build failed"
        exit 1
    }
    
    # Check for build output
    if (Test-Path "dist\rude-chat-app\browser") {
        Write-Info "Angular build found in: dist\rude-chat-app\browser\"
    }
    elseif (Test-Path "dist\rude-chat-app") {
        Write-Info "Angular build found in: dist\rude-chat-app\"
    }
    else {
        Write-Error "Angular build failed - no dist directory found"
        exit 1
    }
    
    Write-Success "Angular build completed successfully!"
}

# Function to copy Angular files to Flask static directory
function Copy-AngularToFlask {
    Write-Info "Copying Angular files to Flask static directory..."
    
    # Create static directory in PythonAPI
    if (!(Test-Path "PythonAPI\static")) {
        New-Item -ItemType Directory -Path "PythonAPI\static" -Force | Out-Null
    }
    
    # Determine Angular build path
    $angularBuildPath = ""
    if (Test-Path "dist\rude-chat-app\browser") {
        $angularBuildPath = "dist\rude-chat-app\browser\*"
        Write-Info "Using newer Angular build structure: dist\rude-chat-app\browser\"
    }
    elseif (Test-Path "dist\rude-chat-app") {
        $angularBuildPath = "dist\rude-chat-app\*"
        Write-Info "Using standard Angular build structure: dist\rude-chat-app\"
    }
    else {
        Write-Error "Angular build directory not found."
        exit 1
    }
    
    # Copy Angular build files
    Copy-Item -Path $angularBuildPath -Destination "PythonAPI\static\" -Recurse -Force
    
    # Verify copy was successful
    if (!(Test-Path "PythonAPI\static\index.html")) {
        Write-Error "Failed to copy Angular files - index.html not found"
        exit 1
    }
    
    Write-Success "Angular files copied to Flask static directory!"
}

# Function to create Azure App Service resources
function New-AzureResourcesHS {
    param([hashtable]$Config)
    
    Write-Info "Creating Azure App Service resources for High Security deployment..."
    
    # Check if resource group exists
    $rgExists = az group show --name $Config.ResourceGroup --query "name" --output tsv 2>$null
    if ([string]::IsNullOrEmpty($rgExists)) {
        Write-Info "Creating resource group: $($Config.ResourceGroup)"
        az group create --name $Config.ResourceGroup --location $Config.Location
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create resource group"
            exit 1
        }
    }
    else {
        Write-Info "Resource group '$($Config.ResourceGroup)' already exists"
    }
    
    # Check if app service exists
    $appExists = az webapp show --name $Config.AppName --resource-group $Config.ResourceGroup --query "name" --output tsv 2>$null
    if ([string]::IsNullOrEmpty($appExists)) {
        Write-Info "Creating App Service: $($Config.AppName)"
        az webapp up `
            --name $Config.AppName `
            --resource-group $Config.ResourceGroup `
            --runtime "PYTHON|$($Config.PythonVersion)" `
            --location $Config.Location `
            --sku "B1"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create App Service"
            exit 1
        }
    }
    else {
        Write-Info "App Service '$($Config.AppName)' already exists"
    }
    
    Write-Success "Azure resources ready!"
}

# Function to deploy SSL certificate bundle
function Deploy-SSLCertificate {
    param([hashtable]$Config)
    
    if (!$Config.UseCustomSSLRoots -or [string]::IsNullOrEmpty($Config.SSLCertPath)) {
        return $null
    }
    
    Write-Info "Preparing custom SSL certificate bundle for deployment..."
    
    # Verify SSL certificate file exists
    if (!(Test-Path $Config.SSLCertPath)) {
        Write-Error "SSL certificate file not found: $($Config.SSLCertPath)"
        exit 1
    }
    
    # Copy SSL certificate to PythonAPI directory for deployment
    $deploySSLPath = "PythonAPI\custom-ca-bundle.pem"
    Copy-Item -Path $Config.SSLCertPath -Destination $deploySSLPath -Force
    
    Write-Success "SSL certificate bundle prepared for deployment: $deploySSLPath"
    return $deploySSLPath
}

# Function to set environment variables with High Security pip settings
function Set-EnvironmentVariablesHS {
    param([hashtable]$Config)
    
    Write-Info "Setting environment variables for High Security deployment..."
    
    # Create pip install command with custom settings
    $pipInstallCmd = "pip install --upgrade pip"
    
    # Add trusted hosts to pip install command
    if ($Config.TrustedHosts.Count -gt 0) {
        $trustedArgs = $Config.TrustedHosts | ForEach-Object { "--trusted-host $_" }
        $pipInstallCmd += " " + ($trustedArgs -join ' ')
    }
    
    # Add custom index if specified
    if (![string]::IsNullOrEmpty($Config.CustomPipIndex)) {
        $pipInstallCmd += " --index-url '$($Config.CustomPipIndex)'"
    }
    
    # Set custom build command for pip installations
    $customBuildScript = @"
#!/bin/bash
set -e
echo "Starting High Security pip installation..."

# Upgrade pip with custom settings
$pipInstallCmd

# Install requirements with custom settings
pip install $($Config.TrustedHosts | ForEach-Object { "--trusted-host $_" } | Join-String -Separator ' ') $(if ($Config.CustomPipIndex) { "--index-url '$($Config.CustomPipIndex)'" }) -r requirements.txt

echo "High Security pip installation completed!"
"@
    
    # Set the startup command
    az webapp config set `
        --name $Config.AppName `
        --resource-group $Config.ResourceGroup `
        --startup-file "gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 300 --keep-alive 75 --no-sendfile --max-requests 1000 --max-requests-jitter 50 --access-logfile - --error-logfile - wsgi:app"
    
    # Set Python version and build settings
    az webapp config set `
        --name $Config.AppName `
        --resource-group $Config.ResourceGroup `
        --linux-fx-version "PYTHON|$($Config.PythonVersion)"
    
    # Set custom pip installation settings
    $appSettings = @{
        "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
        "ENABLE_ORYX_BUILD" = "true"
        "BUILD_FLAGS" = "UseAppInsights=false"
        "PYTHONPATH" = "/home/site/wwwroot"
    }
    
    # Add custom pip settings if configured
    if ($Config.TrustedHosts.Count -gt 0) {
        $appSettings["PIP_TRUSTED_HOST"] = ($Config.TrustedHosts -join ' ')
    }
    
    if (![string]::IsNullOrEmpty($Config.CustomPipIndex)) {
        $appSettings["PIP_INDEX_URL"] = $Config.CustomPipIndex
    }
    
    # Configure SSL certificate bundle for the application
    if ($Config.UseCustomSSLRoots) {
        $appSettings["REQUESTS_CA_BUNDLE"] = "/home/site/wwwroot/custom-ca-bundle.pem"
        $appSettings["SSL_CERT_FILE"] = "/home/site/wwwroot/custom-ca-bundle.pem"
        $appSettings["CURL_CA_BUNDLE"] = "/home/site/wwwroot/custom-ca-bundle.pem"
        # Keep HTTPS verification enabled when using custom bundle
        $appSettings["PYTHONHTTPSVERIFY"] = "/home/site/wwwroot/custom-ca-bundle.pem"
    }
    
    # Core Flask settings
    $appSettings += @{
        "FLASK_ENV" = "production"
        "FLASK_DEBUG" = "false"
        "LOG_LEVEL" = "INFO"
        "API_HOST" = "0.0.0.0"
        "API_PORT" = "8000"
        "MCP_SERVER_NAME" = "PythonAPI_MCP_Server"
        "MCP_SERVER_PORT" = "3001"
        "MCP_MOUNT_PATH" = "/mcp"
        "DEFAULT_USER_ID" = "system"
        "WEBSITE_DISABLE_RESPONSE_BUFFERING" = "true"
        "WEBSITE_HTTPLOGGING_RETENTION_DAYS" = "3"
        "WEBSITE_LOAD_CERTIFICATES" = "*"
        "WEBSITE_TIME_ZONE" = "UTC"
        "WEBSITE_ENABLE_SYNC_UPDATE_SITE" = "true"
    }
    
    # Convert hashtable to Azure CLI format
    $settingsArray = @()
    foreach ($key in $appSettings.Keys) {
        $settingsArray += "$key=$($appSettings[$key])"
    }
    
    # Set all app settings
    az webapp config appsettings set `
        --name $Config.AppName `
        --resource-group $Config.ResourceGroup `
        --settings $settingsArray
    
    # Set additional App Service configurations
    az webapp config set `
        --name $Config.AppName `
        --resource-group $Config.ResourceGroup `
        --always-on true `
        --http20-enabled true `
        --client-affinity-enabled true
    
    Write-Success "High Security environment variables set!"
    
    Write-Warning "IMPORTANT: Set your Azure-specific environment variables:"
    Write-Host "az webapp config appsettings set --name $($Config.AppName) --resource-group $($Config.ResourceGroup) --settings OPENAI_ENDPOINT='your-endpoint' OPENAI_API_KEY='your-key'"
}

# Function to deploy with High Security pip configuration
function Deploy-ApplicationHS {
    param([hashtable]$Config)
    
    Write-Info "Deploying application with High Security pip configuration..."
    
    try {
        # Create pip configuration files
        $pipConfPath = New-PipConfiguration -Config $Config
        $deployReqsPath = New-CustomRequirements -Config $Config
        
        # Deploy SSL certificate if configured
        $sslCertPath = Deploy-SSLCertificate -Config $Config
        
        # Create custom .oryx_build.sh for Azure deployment
        $customBuildScript = @"
#!/bin/bash
set -e
echo "Starting High Security build process..."

# Set up pip configuration
export PIP_CONFIG_FILE=/home/site/wwwroot/pip.conf
"@
        
        if ($Config.TrustedHosts.Count -gt 0) {
            $trustedHostsEnv = $Config.TrustedHosts -join ' '
            $customBuildScript += @"

export PIP_TRUSTED_HOST="$trustedHostsEnv"
"@
        }
        
        if (![string]::IsNullOrEmpty($Config.CustomPipIndex)) {
            $customBuildScript += @"

export PIP_INDEX_URL="$($Config.CustomPipIndex)"
"@
        }
        
        $customBuildScript += @"

# Upgrade pip
python -m pip install --upgrade pip

# Install requirements with custom configuration
python -m pip install -r requirements.txt

echo "High Security build completed!"
"@
        
        # Create .oryx_build.sh in PythonAPI directory
        $buildScriptPath = "PythonAPI\.oryx_build.sh"
        $customBuildScript | Out-File -FilePath $buildScriptPath -Encoding UTF8 -Force
        
        Write-Info "Created custom build script: $buildScriptPath"
        
        # Create deployment zip
        Write-Info "Creating deployment package from PythonAPI contents..."
        $zipPath = "deploy-hs.zip"
        $fullZipPath = Join-Path (Get-Location) $zipPath
        
        if (Test-Path $fullZipPath) {
            Remove-Item $fullZipPath -Force
        }
        
        # Verify required files exist
        $requiredFiles = @("main.py", "requirements.txt", "wsgi.py")
        foreach ($file in $requiredFiles) {
            if (!(Test-Path "PythonAPI\$file")) {
                Write-Error "$file not found in PythonAPI directory"
                exit 1
            }
        }
        
        # Add SSL certificate to required files check if configured
        if ($sslCertPath -and !(Test-Path $sslCertPath)) {
            Write-Error "SSL certificate bundle not found: $sslCertPath"
            exit 1
        }
        
        # Create zip with PythonAPI contents
        $excludePatterns = @("__pycache__", "*.pyc", ".git", ".pytest_cache", "node_modules", ".deployment", "myenv", "venv")
        Write-Info "Creating High Security deployment package..."
        
        Compress-Archive -Path "PythonAPI\*" -DestinationPath $fullZipPath -Force
        
        # Verify zip contents
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zipCheck = [System.IO.Compression.ZipFile]::OpenRead($fullZipPath)
        $zipEntries = $zipCheck.Entries | ForEach-Object { $_.FullName }
        $zipCheck.Dispose()
        
        Write-Info "Deployment package contains:"
        $zipEntries | ForEach-Object { Write-Host "  - $_" }
        
        # Deploy to Azure
        Write-Info "Uploading High Security application to Azure..."
        az webapp deploy `
            --name $Config.AppName `
            --resource-group $Config.ResourceGroup `
            --src-path $fullZipPath `
            --type zip `
            --async false
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "High Security deployment failed"
            exit 1
        }
        
        # Clean up
        if (Test-Path $fullZipPath) {
            Remove-Item $fullZipPath -Force
        }
        
        Write-Success "High Security application deployed successfully!"
    }
    catch {
        Write-Error "High Security deployment failed: $_"
        exit 1
    }
}

# Function to show post-deployment information
function Show-DeploymentInfoHS {
    param([hashtable]$Config)
    
    Write-Success "High Security Deployment completed successfully!"
    Write-Host ""
    Write-Info "Application Information:"
    Write-Host "  App URL: https://$($Config.AppName).azurewebsites.net"
    Write-Host "  API Health: https://$($Config.AppName).azurewebsites.net/health"
    Write-Host "  API Endpoints: https://$($Config.AppName).azurewebsites.net/api/v1"
    Write-Host ""
    Write-Info "High Security Configuration:"
    if (![string]::IsNullOrEmpty($Config.CustomPipIndex)) {
        Write-Host "  Custom Pip Index: $($Config.CustomPipIndex)"
    }
    if ($Config.TrustedHosts.Count -gt 0) {
        Write-Host "  Trusted Hosts: $($Config.TrustedHosts -join ', ')"
    }
    if ($Config.UseCustomSSLRoots) {
        Write-Host "  Custom SSL Certificate Bundle: Deployed to /home/site/wwwroot/custom-ca-bundle.pem"
        Write-Host "  SSL Environment Variables: REQUESTS_CA_BUNDLE, SSL_CERT_FILE, CURL_CA_BUNDLE set"
    }
    Write-Host ""
    Write-Info "Next Steps:"
    Write-Host "1. Monitor logs: az webapp log tail --name $($Config.AppName) --resource-group $($Config.ResourceGroup)"
    Write-Host "2. View app settings: az webapp config appsettings list --name $($Config.AppName) --resource-group $($Config.ResourceGroup)"
    Write-Host "3. Test your application at: https://$($Config.AppName).azurewebsites.net"
    if ($Config.UseCustomSSLRoots) {
        Write-Host "4. Verify SSL certificate bundle: Check that HTTPS requests use the custom CA bundle"
    }
    Write-Host ""
}

# Main deployment function
function Main {
    Write-Host "========================================================"
    Write-Host "Azure App Service High Security (HS) Deployment Script"
    Write-Host "Flask API + Angular Frontend with Custom Pip Support"
    Write-Host "========================================================"
    Write-Host ""
    
    # Check prerequisites
    Test-Prerequisites
    
    # Get deployment configuration
    $config = Get-DeploymentConfigHS
    
    # Build Angular
    Build-Angular
    
    # Copy Angular files to Flask
    Copy-AngularToFlask
    
    # Create Azure resources
    New-AzureResourcesHS -Config $config
    
    # Set environment variables with HS settings
    Set-EnvironmentVariablesHS -Config $config
    
    # Deploy application with HS configuration
    Deploy-ApplicationHS -Config $config
    
    # Show deployment info
    Show-DeploymentInfoHS -Config $config
}

# Run main function
Main