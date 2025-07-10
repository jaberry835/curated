"""Fictional companies information tools for direct function calls."""

import json
import requests
import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Base URL for the fictional companies API - configurable via environment variable
BASE_URL = os.getenv("FICTIONAL_COMPANIES_API_URL", "http://localhost:8000")

def get_ip_company_info_impl(ip_address: str, **kwargs) -> dict:
    """Get fictional company information for a given IP address."""
    try:
        # Use GET method with path parameter
        url = f"{BASE_URL}/api/v1/ip-company/{ip_address}"
        logger.info(f"Making request to: {url}")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Retrieved fictional company information for IP {ip_address}"
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching IP company info: {e}")
        return {
            "status": "error",
            "message": f"Failed to get company info for IP {ip_address}: {str(e)}",
            "data": None
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "data": None
        }

def get_company_devices_impl(company_name: str, **kwargs) -> dict:
    """Get fictional device information for a given company."""
    try:
        # Use GET method with path parameter
        url = f"{BASE_URL}/api/v1/company-devices/{company_name}"
        logger.info(f"Making request to: {url}")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Retrieved fictional device information for company {company_name}"
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching company devices: {e}")
        return {
            "status": "error",
            "message": f"Failed to get device info for company {company_name}: {str(e)}",
            "data": None
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "data": None
        }

def get_company_summary_impl(company_name: str, **kwargs) -> dict:
    """Get comprehensive fictional summary for a given company."""
    try:
        # Use GET method with path parameter
        url = f"{BASE_URL}/api/v1/company-summary/{company_name}"
        logger.info(f"Making request to: {url}")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Retrieved fictional company summary for {company_name}"
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching company summary: {e}")
        return {
            "status": "error",
            "message": f"Failed to get company summary for {company_name}: {str(e)}",
            "data": None
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "data": None
        }

def health_check_impl(**kwargs) -> dict:
    """Check if the fictional companies API is healthy and available."""
    try:
        url = f"{BASE_URL}/health"
        logger.info(f"Making health check request to: {url}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": "Fictional companies API is healthy and available"
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "message": f"Health check failed: {str(e)}",
            "data": None
        }
    except Exception as e:
        logger.error(f"Unexpected error during health check: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "data": None
        }
