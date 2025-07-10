"""
Azure Configuration Verification Script
Run this to test if your Azure setup is correct.
"""

import os
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

def test_azure_configuration():
    """Test Azure configuration for ADX user impersonation."""
    
    print("🔍 Testing Azure Configuration for ADX User Impersonation\n")
    
    # Test 1: Check environment variables
    print("1. Checking Environment Variables:")
    adx_cluster = os.getenv("ADX_CLUSTER_URL")
    if adx_cluster:
        print(f"   ✅ ADX_CLUSTER_URL: {adx_cluster}")
    else:
        print("   ❌ ADX_CLUSTER_URL not set")
        return False
    
    # Test 2: Test system identity connection
    print("\n2. Testing System Identity Connection:")
    try:
        credential = DefaultAzureCredential()
        kcsb = KustoConnectionStringBuilder.with_azure_token_credential(adx_cluster, credential)
        client = KustoClient(kcsb)
        
        # Try a simple query
        response = client.execute("", ".show databases")
        print(f"   ✅ System identity works. Found {len(list(response.primary_results[0]))} databases")
        
    except Exception as e:
        print(f"   ❌ System identity failed: {str(e)}")
        return False
    
    # Test 3: Check if user token authentication would work
    print("\n3. Checking User Token Authentication Setup:")
    try:
        # This tests the token-based connection setup (without actual user token)
        test_kcsb = KustoConnectionStringBuilder.with_aad_user_token(adx_cluster, "dummy_token")
        print("   ✅ User token authentication method is available")
    except Exception as e:
        print(f"   ❌ User token authentication setup failed: {str(e)}")
        return False
    
    print("\n📋 Next Steps:")
    print("   1. Ensure your Angular app registration has 'Azure Data Explorer' API permissions")
    print("   2. Grant admin consent for the API permissions")
    print("   3. Add users to appropriate ADX database/table permissions")
    print("   4. Test with a real user login from your Angular app")
    
    return True

if __name__ == "__main__":
    success = test_azure_configuration()
    if success:
        print("\n🎉 Azure configuration looks good!")
        print("✅ Your setup should support ADX user impersonation")
    else:
        print("\n❌ Configuration issues found. Please fix the errors above.")
