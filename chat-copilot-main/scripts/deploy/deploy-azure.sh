#!/usr/bin/env bash

# Deploy Chat Copilot Azure resources.

set -e

usage() {
    echo "Usage: $0 -d DEPLOYMENT_NAME -s SUBSCRIPTION -c BACKEND_CLIENT_ID -fc FRONTEND_CLIENT_ID -t AZURE_AD_TENANT_ID -ai AI_SERVICE_TYPE -cm COMPLETION_MODEL -em EMBEDDING_MODEL [OPTIONS]"
    echo ""
    echo "Arguments:"
    echo "  -d, --deployment-name DEPLOYMENT_NAME      Name for the deployment (mandatory)"
    echo "  -s, --subscription SUBSCRIPTION            Subscription to which to make the deployment (mandatory)"
    echo "  -c, --client-id BACKEND_CLIENT_ID          Azure AD client ID for the Web API backend app registration (mandatory)"
    echo "  -fc, --frontend-client-id FE_CLIENT_ID     Azure AD client ID for the frontend app registration (mandatory)"
    echo "  -t, --tenant-id AZURE_AD_TENANT_ID         Azure AD tenant ID for authenticating users (mandatory)"
    echo "  -ai, --ai-service AI_SERVICE_TYPE          Type of AI service to use (i.e., OpenAI or AzureOpenAI) (mandatory)"
    echo "  -cm, --completion-model COMPLETION_MODEL   Model to use for chat completions (mandatory)"
    echo "  -em, --embedding-model EMBEDDING_MODEL     Model to use for text embeddings (mandatory)"
    echo "  -aiend, --ai-endpoint AI_ENDPOINT          Endpoint for existing Azure OpenAI resource"
    echo "  -aikey, --ai-service-key AI_SERVICE_KEY    API key for existing Azure OpenAI resource or OpenAI account"
    echo "  -rg, --resource-group RESOURCE_GROUP       Resource group to which to make the deployment (default: \"rg-\$DEPLOYMENT_NAME\")"
    echo "  -r, --region REGION                        Region to which to make the deployment (default: \"South Central US\")"
    echo "  -a, --app-service-sku WEB_APP_SVC_SKU      SKU for the Azure App Service plan (default: \"B1\")"
    echo "  -i, --instance AZURE_AD_INSTANCE           Azure AD cloud instance for authenticating users"
    echo "                                             (default: \"https://login.microsoftonline.com\")"
    echo "  -ms, --memory-store                        Method to use to persist embeddings. Valid values are"
    echo "                                             \"AzureAISearch\" (default) and \"Qdrant\""
    echo "  -nc, --no-cosmos-db                        Don't deploy Cosmos DB for chat storage - Use volatile memory instead"
    echo "  -ns, --no-speech-services                  Don't deploy Speech Services to enable speech as chat input"
    echo "  -ws, --deploy-web-searcher-plugin          Deploy the web searcher plugin"
    echo "  -dd, --debug-deployment                    Switches on verbose template deployment output"
    echo "  -ndp, --no-deploy-package                  Skips deploying binary packages to cloud when set."
    echo "  -aoaigr, --aoai-resource-group-name        Azure OpenAI service resource group name"
    echo "  -aoaian, --aoai-account-name               Azure OpenAI resource account name"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
    -d | --deployment-name)
        DEPLOYMENT_NAME="$2"
        shift
        shift
        ;;
    -s | --subscription)
        SUBSCRIPTION="$2"
        shift
        shift
        ;;
    -c | --client-id)
        BACKEND_CLIENT_ID="$2"
        shift
        shift
        ;;
    -fc | --frontend-client-id)
        FRONTEND_CLIENT_ID="$2"
        shift
        shift
        ;;
    -t | --tenant-id)
        AZURE_AD_TENANT_ID="$2"
        shift
        shift
        ;;
    -ai | --ai-service)
        AI_SERVICE_TYPE="$2"
        shift
        shift
        ;;
    -cm | --completion-model)
        COMPLETION_MODEL="$2"
        shift
        shift
        ;;
    -em | --embedding-model)
        EMBEDDING_MODEL="$2"
        shift
        shift
        ;;
    -aikey | --ai-service-key)
        AI_SERVICE_KEY="$2"
        shift
        shift
        ;;
    -aiend | --ai-endpoint)
        AI_ENDPOINT="$2"
        shift
        shift
        ;;
    -rg | --resource-group)
        RESOURCE_GROUP="$2"
        shift
        shift
        ;;
    -r | --region)
        REGION="$2"
        shift
        shift
        ;;
    -a | --app-service-sku)
        WEB_APP_SVC_SKU="$2"
        shift
        shift
        ;;
    -i | --instance)
        AZURE_AD_INSTANCE="$2"
        shift
        shift
        ;;
    -ms | --memory-store)
        MEMORY_STORE="$2"
        shift
        ;;
    -nc | --no-cosmos-db)
        NO_COSMOS_DB=true
        shift
        ;;
    -ns | --no-speech-services)
        NO_SPEECH_SERVICES=true
        shift
        ;;
    -ws | --deploy-web-searcher-plugin)
        DEPLOY_WEB_SEARCHER_PLUGIN=true
        shift
        ;;
    -dd | --debug-deployment)
        DEBUG_DEPLOYMENT=true
        shift
        ;;
    -ndp | --no-deploy-package)
        NO_DEPLOY_PACKAGE=true
        shift
        ;;
    -aoaigr | --aoai-resource-group-name)
        AOAI_RESOURCE_GROUP_NAME="$2"
        shift
        shift
        ;;
    -aoaian | --aoai-account-name)
        AOAI_ACCOUNT_NAME="$2"
        shift
        shift
        ;;
    -e | --environment)
        ENVIRONMENT="$2"        
        if [[ "$ENVIRONMENT" != "AzureCloud" && "$ENVIRONMENT" != "AzureUSGovernment" ]]; then
            echo "Invalid environment option. Use 'AzureCloud' or 'AzureUSGovernment'."
            exit 1
        fi
        shift
        shift
        ;;
    *)
        echo "Unknown option $1"
        usage
        exit 1
        ;;
    esac
done

# Check mandatory arguments
if [[ -z "$DEPLOYMENT_NAME" ]] || [[ -z "$SUBSCRIPTION" ]] || [[ -z "$BACKEND_CLIENT_ID" ]] || [[ -z "$FRONTEND_CLIENT_ID" ]] || [[ -z "$AZURE_AD_TENANT_ID" ]] || [[ -z "$AI_SERVICE_TYPE" ]] || [[ -z "$COMPLETION_MODEL" ]] || [[ -z "$EMBEDDING_MODEL" ]]; then
    usage
    exit 1
fi

# Check if AI_SERVICE_TYPE is either OpenAI or AzureOpenAI
if [[ "${AI_SERVICE_TYPE,,}" != "openai" ]] && [[ "${AI_SERVICE_TYPE,,}" != "azureopenai" ]]; then
    echo "--ai-service must be either OpenAI or AzureOpenAI"
    usage
    exit 1
fi

# if AI_SERVICE_TYPE is AzureOpenAI
if [[ "${AI_SERVICE_TYPE,,}" = "azureopenai" ]]; then
    # Both AI_ENDPOINT and AI_SERVICE_KEY must be set or neither of them.
    if [[ (-z "$AI_ENDPOINT" && -n "$AI_SERVICE_KEY") || (-n "$AI_ENDPOINT" && -z "$AI_SERVICE_KEY") ]]; then
        echo "When --ai is 'AzureOpenAI', if either --ai-endpoint or --ai-service-key is set, then both must be set."
        usage
        exit 1
    fi

    # if AI_ENDPOINT and AI_SERVICE_KEY are not set, set NO_NEW_AZURE_OPENAI to false and tell the user, else set NO_NEW_AZURE_OPENAI to true
    if [[ -z "$AI_ENDPOINT" ]] && [[ -z "$AI_SERVICE_KEY" ]]; then
        NO_NEW_AZURE_OPENAI=false
        echo "When --ai is 'AzureOpenAI', if neither --ai-endpoint nor --ai-service-key are set, then a new Azure OpenAI resource will be created."
    else
        NO_NEW_AZURE_OPENAI=true
        echo "When --ai is 'AzureOpenAI', if both --ai-endpoint and --ai-service-key are set, then an existing Azure OpenAI resource will be used."
    fi
fi

# if AI_SERVICE_TYPE is OpenAI then AI_SERVICE_KEY is mandatory
if [[ "${AI_SERVICE_TYPE,,}" = "openai" ]] && [[ -z "$AI_SERVICE_KEY" ]]; then
    echo "When --ai is 'OpenAI', --ai-service-key must be set."
    usage
    exit 1
fi
# If resource group is not set, then set it to rg-DEPLOYMENT_NAME
if [ -z "$RESOURCE_GROUP" ]; then
    RESOURCE_GROUP="rg-${DEPLOYMENT_NAME}"
fi

TEMPLATE_FILE="$(dirname "$0")/main.bicep"

# Ensure that the environment variable is set
if [[ -z "$ENVIRONMENT" ]]; then
    echo "Error: Environment not set. Please set the environment to either 'AzureCloud' or 'AzureUSGovernment'."
    exit 1
fi

echo "Setting Azure cloud environment to $ENVIRONMENT..."
az cloud set --name "$ENVIRONMENT"

# Check if the last command was successful
if [[ $? -ne 0 ]]; then
    echo "Error: Failed to set Azure cloud environment to $ENVIRONMENT."
    exit $?
fi

echo "Azure cloud environment successfully set to $ENVIRONMENT."

az account show --output none
if [ $? -ne 0 ]; then
    echo "Log into your Azure account"
    az login --use-device-code
fi

az account set -s "$SUBSCRIPTION"

# Set defaults
: "${REGION:="southcentralus"}"
: "${WEB_APP_SVC_SKU:="B1"}"
: "${AZURE_AD_INSTANCE:="https://login.microsoftonline.com"}"
: "${MEMORY_STORE:="AzureAISearch"}"
: "${NO_COSMOS_DB:=false}"
: "${NO_SPEECH_SERVICES:=false}"
: "${DEPLOY_WEB_SEARCHER_PLUGIN:=false}"

# Check environment and adjust region and Azure AD instance
if [[ "$ENVIRONMENT" == "AzureUSGovernment" ]]; then
    echo "updating values for Government Cloud"
    REGION="usgovvirginia"  # Direct assignment
    AZURE_AD_INSTANCE="https://login.microsoftonline.us"  # Direct assignment
else
    echo "Unknown environment: $ENVIRONMENT"
    exit 1
fi

# Log the values of REGION and AZURE_AD_INSTANCE
echo "Region set to: $REGION"
echo "Azure AD Instance set to: $AZURE_AD_INSTANCE"
# Create JSON config
JSON_CONFIG=$(
    cat <<EOF
{
    "webAppServiceSku": { "value": "$WEB_APP_SVC_SKU" },
    "aiService": { "value": "$AI_SERVICE_TYPE" },
    "completionModel": { "value": "$COMPLETION_MODEL" },
    "embeddingModel": { "value": "$EMBEDDING_MODEL" },
    "aiApiKey": { "value": "$AI_SERVICE_KEY" },
    "deployPackages": { "value": $([ "$NO_DEPLOY_PACKAGE" = true ] && echo "false" || echo "true") },
    "aiEndpoint": { "value": "$([ ! -z "$AI_ENDPOINT" ] && echo "$AI_ENDPOINT")" },
    "azureAdInstance": { "value": "$AZURE_AD_INSTANCE" },
    "azureAdTenantId": { "value": "$AZURE_AD_TENANT_ID" },
    "webApiClientId": { "value": "$BACKEND_CLIENT_ID" },
    "frontendClientId": { "value": "$FRONTEND_CLIENT_ID" },
    "AOAIResourceGroupName": { "value": "$AOAI_RESOURCE_GROUP_NAME" },
    "AOAIAccountName": { "value": "$AOAI_ACCOUNT_NAME" },
    "deployNewAzureOpenAI": { "value": $([ "$NO_NEW_AZURE_OPENAI" = true ] && echo "false" || echo "true") },
    "memoryStore": { "value": "$MEMORY_STORE" },
    "deployCosmosDB": { "value": $([ "$NO_COSMOS_DB" = true ] && echo "false" || echo "true") },
    "deploySpeechServices": { "value": $([ "$NO_SPEECH_SERVICES" = true ] && echo "false" || echo "true") },
    "deployWebSearcherPlugin": { "value": $([ "$DEPLOY_WEB_SEARCHER_PLUGIN" = true ] && echo "true" || echo "false") }
}
EOF
)

echo "Ensuring resource group $RESOURCE_GROUP exists..."
az group create --location "$REGION" --name "$RESOURCE_GROUP" --tags Creator="$USER"

echo "Validating template file..."
az deployment group validate --name "$DEPLOYMENT_NAME" --resource-group "$RESOURCE_GROUP" --template-file "$TEMPLATE_FILE" --parameters "$JSON_CONFIG"

echo "Deploying Azure resources ($DEPLOYMENT_NAME)..."

if [ "$DEBUG_DEPLOYMENT" = true ]; then
    az deployment group create --name "$DEPLOYMENT_NAME" --resource-group "$RESOURCE_GROUP" --template-file "$TEMPLATE_FILE" --debug --parameters "$JSON_CONFIG"
else
    az deployment group create --name "$DEPLOYMENT_NAME" --resource-group "$RESOURCE_GROUP" --template-file "$TEMPLATE_FILE" --parameters "$JSON_CONFIG"
fi
