# Azure App Service Deployment Guide

This guide explains how to deploy your Flask API + Angular frontend to Azure App Service using the provided deployment scripts.

## Prerequisites

Before running the deployment script, ensure you have:

1. **Node.js and npm** installed
2. **Angular CLI** installed globally: `npm install -g @angular/cli`
3. **Azure CLI** installed: [Install Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
4. **Azure account** with appropriate permissions to create resources
5. **Logged in to Azure CLI**: Run `az login` and follow the prompts

## Project Structure

After deployment, your project structure will look like this:

```
AgentChat/
├── PythonAPI/
│   ├── app.py                 # Azure App Service entry point
│   ├── main.py                # Local development entry point
│   ├── requirements.txt       # Python dependencies
│   ├── static/                # Angular build output (created by script)
│   │   ├── index.html
│   │   └── ...                # Other Angular files
│   └── src/                   # Your Flask API source code
├── src/                       # Angular source code
├── dist/                      # Angular build output (temporary)
├── deploy.ps1                 # PowerShell deployment script
├── deploy.sh                  # Bash deployment script (Linux/Mac)
├── deploy.bat                 # Windows batch file
└── azure-env-template.env     # Environment variables template
```

## Deployment Process

### Option 1: Windows (PowerShell)

```powershell
# Run the PowerShell script directly
.\deploy.ps1

# Or use the batch file
.\deploy.bat
```

### Option 2: Linux/Mac (Bash)

```bash
# Make the script executable
chmod +x deploy.sh

# Run the deployment script
./deploy.sh
```

## What the Deployment Script Does

1. **Checks Prerequisites**: Verifies Angular CLI and Azure CLI are installed
2. **Gets Configuration**: Prompts for App Service name and Resource Group
3. **Builds Angular**: Runs `ng build --configuration=production`
4. **Copies Files**: Copies Angular build output to `PythonAPI/static/`
5. **Creates Azure Resources**: Creates Resource Group and App Service if they don't exist
6. **Sets Environment Variables**: Configures basic Flask settings
7. **Deploys Application**: Creates zip package and deploys to Azure
8. **Shows Results**: Displays deployment information and next steps

## Environment Variables

After deployment, you need to set your Azure service environment variables. The script provides commands to set these variables, but you need to fill in your actual values.

### Required Environment Variables

#### Azure OpenAI
```bash
az webapp config appsettings set \
  --name YOUR_APP_NAME \
  --resource-group YOUR_RESOURCE_GROUP \
  --settings \
  OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/" \
  OPENAI_API_KEY="your-openai-api-key" \
  OPENAI_DEPLOYMENT="your-gpt-deployment-name" \
  OPENAI_EMBEDDING_DEPLOYMENT="your-embedding-deployment-name"
```

#### Azure Cosmos DB
```bash
az webapp config appsettings set \
  --name YOUR_APP_NAME \
  --resource-group YOUR_RESOURCE_GROUP \
  --settings \
  COSMOS_DB_ENDPOINT="https://your-cosmos-account.documents.azure.com:443/" \
  COSMOS_DB_KEY="your-cosmos-primary-key" \
  COSMOS_DB_DATABASE="your-database-name" \
  COSMOS_DB_SESSIONS_CONTAINER="sessions" \
  COSMOS_DB_MESSAGES_CONTAINER="messages"
```

#### Azure Blob Storage
```bash
az webapp config appsettings set \
  --name YOUR_APP_NAME \
  --resource-group YOUR_RESOURCE_GROUP \
  --settings \
  STORAGE_ACCOUNT_NAME="your-storage-account-name" \
  STORAGE_ACCOUNT_KEY="your-storage-account-key" \
  STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=your-account;AccountKey=your-key;EndpointSuffix=core.windows.net" \
  STORAGE_CONTAINER_NAME="documents"
```

#### Azure AI Search
```bash
az webapp config appsettings set \
  --name YOUR_APP_NAME \
  --resource-group YOUR_RESOURCE_GROUP \
  --settings \
  SEARCH_ENDPOINT="https://your-search-service.search.windows.net" \
  SEARCH_KEY="your-search-admin-key" \
  SEARCH_INDEX_NAME="your-index-name"
```

See `azure-env-template.env` for a complete list of environment variables.

## Post-Deployment

After deployment, your application will be available at:
- **Main App**: `https://YOUR_APP_NAME.azurewebsites.net`
- **API Health**: `https://YOUR_APP_NAME.azurewebsites.net/health`
- **API Endpoints**: `https://YOUR_APP_NAME.azurewebsites.net/api/v1`

### Monitoring and Troubleshooting

1. **View Logs**:
   ```bash
   az webapp log tail --name YOUR_APP_NAME --resource-group YOUR_RESOURCE_GROUP
   ```

2. **Check Application Settings**:
   ```bash
   az webapp config appsettings list --name YOUR_APP_NAME --resource-group YOUR_RESOURCE_GROUP
   ```

3. **Restart Application**:
   ```bash
   az webapp restart --name YOUR_APP_NAME --resource-group YOUR_RESOURCE_GROUP
   ```

4. **SSH into Container** (for debugging):
   ```bash
   az webapp ssh --name YOUR_APP_NAME --resource-group YOUR_RESOURCE_GROUP
   ```

## Application Architecture

The deployed application uses the following architecture:

- **Flask Backend**: Serves both API endpoints and static Angular files
- **Server-Sent Events (SSE)**: Enables real-time communication for agent activities
- **Static Files**: Angular build output served from `/static/` directory
- **API Routes**: All API endpoints under `/api/v1/`
- **Health Check**: Available at `/health`

## Azure App Service Configuration

The deployment script configures the following settings:

- **Runtime**: Python 3.13 on Linux
- **Startup Command**: `cd PythonAPI && gunicorn -w 1 --bind 0.0.0.0:8000 wsgi:app`
- **Port**: 8000 (required for App Service)
- **Worker Class**: default (standard Flask WSGI)
- **Workers**: 1 (single worker for SSE compatibility)

## Troubleshooting

### Common Issues

1. **Build Fails**: Ensure Angular CLI is installed and `ng build` works locally
2. **Deployment Fails**: Check Azure CLI login status and permissions
3. **App Won't Start**: Verify environment variables are set correctly
4. **SSE Connection Issues**: Check if SSE endpoint is accessible and CORS is configured properly
5. **Static Files 404**: Verify Angular files were copied to `/static/` directory

### Getting Help

If you encounter issues:

1. Check the Azure portal logs
2. Review the deployment script output
3. Verify all environment variables are set
4. Test the application locally first
5. Check Azure service status

## Cost Optimization

To optimize costs:

1. **Use B1 SKU** for development/testing
2. **Scale down** when not in use
3. **Use managed identity** instead of storing keys
4. **Monitor resource usage** in Azure portal
5. **Set up auto-scaling** for production workloads

## Security Best Practices

1. **Use Managed Identity** for Azure services
2. **Store secrets** in Azure Key Vault
3. **Enable HTTPS only** in App Service settings
4. **Configure CORS** appropriately
5. **Use Network Security Groups** for additional security
6. **Enable Application Insights** for monitoring

## Next Steps

1. Set up your Azure services (OpenAI, Cosmos DB, etc.)
2. Configure environment variables with your actual values
3. Test the deployed application
4. Set up continuous deployment with GitHub Actions (optional)
5. Configure custom domains and SSL certificates (optional)
6. Set up monitoring and alerting
