# get_worker_server.py
from typing import Dict, Any, Optional
import requests
import json
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Configuration
WORKDAY_API_URL = os.getenv("WORKDAY_API_URL", "https://api.us.wcp.workday.com/common/v1/workers")
WORKDAY_API_TOKEN = os.getenv("WORKDAY_API_TOKEN")

# Create MCP server
mcp = FastMCP("Workday MCP Server")

async def get_workday_data(url: str, params: Dict = None) -> Dict[str, Any]:
    """
    Generic function to retrieve data from Workday API
    """
    if not WORKDAY_API_TOKEN:
        raise ValueError("Missing API token. Set WORKDAY_API_TOKEN environment variable.")
    
    # Setup request headers with authorization
    headers = {
        'Authorization': f'Bearer {WORKDAY_API_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    try:
        # Execute GET request
        response = requests.get(url, headers=headers, params=params)
        
        # Check for HTTP errors
        response.raise_for_status()
        
        # Parse JSON response
        return response.json()
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"Workday API error: {str(e)}"
        if hasattr(response, 'text'):
            error_msg += f", Response: {response.text}"
        return {"error": error_msg, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}", "status_code": 500}
    except json.JSONDecodeError:
        return {"error": "Response is not valid JSON", "status_code": 500}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "status_code": 500}

# Define MCP Resources
@mcp.resource("workday://workers")
async def get_workers() -> str:
    """
    Retrieve list of all workers from Workday API
    """
    result = await get_workday_data(WORKDAY_API_URL)
    if "error" in result:
        return json.dumps({"error": result["error"]})
    return json.dumps(result, indent=2)

@mcp.resource("workday://worker/{worker_id}")
async def get_worker(worker_id: str) -> str:   
    """
    Retrieve detailed information about a specific worker
    
    Args:
        worker_id: Worker ID to retrieve (required)
    
    Returns:
        JSON string with detailed worker data
    """
    if not worker_id:
        return json.dumps({"error": "worker_id is required"})
    
    # Build URL for specific worker
    url = f"{WORKDAY_API_URL}/{worker_id}"
    
    # Get data from Workday API
    result = await get_workday_data(url)
    
    if "error" in result:
        return json.dumps({"error": result["error"]})
    
    return json.dumps(result, indent=2) 



# Define MCP Tools
@mcp.tool()
async def get_workers_tool(limit: Optional[int] = 100, offset: Optional[int] = 0, search: Optional[str] = '') -> str:
    """
    Tool to retrieve worker data with optional parameters
    
    Args:
        limit: Maximum number of workers to return (default: 100)
        offset: Pagination offset (default: 0)
        search: Search term (default: '')
    Returns:
        JSON string with worker data
    """
    print(f"[DEBUG] get_workers_tool called with args: limit={limit} (type: {type(limit)}), offset={offset} (type: {type(offset)}), search={search} (type: {type(search)})")
    # Add query parameters
    query_params = {}
    if offset:
        query_params["offset"] = offset
    if limit:
        query_params["limit"] = limit
    if search:
        query_params["search"] = search
    
    # Get data from Workday API
    result = await get_workday_data(WORKDAY_API_URL, query_params)
    
    # Return results as JSON string
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_worker_details_tool(worker_id: str) -> str:
    """
    Tool to retrieve detailed information about a specific worker
    
    Args:
        worker_id: Worker ID to retrieve (required)
    
    Returns:
        JSON string with detailed worker data
    """
    # Check required parameters
    if not worker_id:
        return json.dumps({"error": "worker_id is required"})
    
    # Build URL for specific worker
    url = f"{WORKDAY_API_URL}/{worker_id}"
    
    # Add query parameters to include details
    query_params = {"include": "details"}
    
    # Get data from Workday API
    result = await get_workday_data(url, query_params)
    
    # Return as JSON string
    return json.dumps(result, indent=2)

# Define MCP Prompts
@mcp.prompt()
def worker_search_prompt() -> str:
    """Create a prompt for worker search"""
    return """
    I need to find employee information in our Workday system. 
    Please help me search for a worker based on their name or other attributes.
    You can use the get_workers_tool to find matching employees.
    """

@mcp.prompt()
def worker_details_prompt() -> str:
    """Create a prompt for viewing worker details"""
    return """
    I need to view detailed information about a specific employee in our Workday system.
    If you know the employee's ID, you can use the get_worker_details_tool to retrieve their information.
    If you don't know their ID, you can first search for them using the get_worker_details_tool.
    """

# Main execution
if __name__ == "__main__": 
    print("Starting MCP server...")
    try:
        mcp.run(transport="stdio")
        print("MCP server started successfully")
    except Exception as e:
        error_msg = f"Error running MCP server: {e}"
        print(error_msg)
