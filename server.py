# server.py
from mcp.server.fastmcp import FastMCP
import os
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create an MCP server
mcp = FastMCP("JIRA Demo")


# Add an addition tool
@mcp.tool()
def sum(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"


# JIRA API functions
def get_jira_headers() -> Dict[str, str]:
    """Get headers for JIRA API requests"""
    api_token = os.getenv("JIRA_API_KEY")  # Using JIRA_API_KEY as mentioned in your request
    jira_user = os.getenv("JIRA_USER")
    
    if not api_token:
        raise ValueError("JIRA API key not found in environment variables")
    if not jira_user:
        raise ValueError("JIRA user email not found in environment variables")
    
    # For Atlassian Cloud, Basic Auth is required with email:token
    import base64
    auth_str = f"{jira_user}:{api_token}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    return {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/json"
    }


# Add JIRA board tickets endpoint
@mcp.tool()
def list_jira_tickets(board_id: int, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    List tickets (issues) from a specified JIRA board
    
    Args:
        board_id: The ID of the JIRA board
        max_results: Maximum number of results to return (default: 50)
        
    Returns:
        List of tickets with their details
    """
    # Base URL for your JIRA instance - you might need to adjust this for your specific JIRA domain
    # For example, if you're using Atlassian Cloud, it might be https://your-domain.atlassian.net
    # In a production app, this should be in your .env file
    base_url = os.getenv("JIRA_BASE_URL", "https://wovnio.atlassian.net")
    
    # Endpoint to get issues from a board
    url = f"{base_url}/rest/agile/1.0/board/{board_id}/issue"
    
    # Parameters for the request
    params = {
        "maxResults": max_results,
        "jql": "order by created DESC"  # Order by creation date descending
    }
    
    try:
        response = requests.get(url, headers=get_jira_headers(), params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        data = response.json()
        issues = data.get("issues", [])
        
        # Transform the response to include only relevant information
        simplified_issues = []
        for issue in issues:
            simplified_issues.append({
                "id": issue.get("id"),
                "key": issue.get("key"),
                "summary": issue.get("fields", {}).get("summary"),
                "status": issue.get("fields", {}).get("status", {}).get("name"),
                "type": issue.get("fields", {}).get("issuetype", {}).get("name"),
                "priority": issue.get("fields", {}).get("priority", {}).get("name"),
                "assignee": issue.get("fields", {}).get("assignee", {}).get("displayName") if issue.get("fields", {}).get("assignee") else "Unassigned"
            })
        
        return simplified_issues
    
    except requests.exceptions.RequestException as e:
        return [{"error": f"Failed to fetch JIRA tickets: {str(e)}"}]


# Add JIRA ticket details endpoint
@mcp.tool()
def get_jira_ticket_details(ticket_key: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific JIRA ticket
    
    Args:
        ticket_key: The key of the JIRA ticket (e.g., 'SUP-3591')
        
    Returns:
        Detailed information about the ticket including description and comments
    """
    base_url = os.getenv("JIRA_BASE_URL", "https://wovnio.atlassian.net")
    
    # Endpoint to get issue details
    url = f"{base_url}/rest/api/3/issue/{ticket_key}"
    
    # Parameters to expand additional fields like comments
    params = {
        "expand": "renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations"
    }
    
    try:
        # Get the main ticket details
        response = requests.get(url, headers=get_jira_headers(), params=params)
        response.raise_for_status()
        
        issue_data = response.json()
        
        # Get comments separately with the comments API
        comments_url = f"{base_url}/rest/api/3/issue/{ticket_key}/comment"
        comments_response = requests.get(comments_url, headers=get_jira_headers())
        comments_response.raise_for_status()
        
        comments_data = comments_response.json()
        
        # Build a comprehensive response with all the details
        ticket_details = {
            "id": issue_data.get("id"),
            "key": issue_data.get("key"),
            "summary": issue_data.get("fields", {}).get("summary"),
            "description": issue_data.get("fields", {}).get("description"),
            "rendered_description": issue_data.get("renderedFields", {}).get("description"),
            "status": issue_data.get("fields", {}).get("status", {}).get("name"),
            "type": issue_data.get("fields", {}).get("issuetype", {}).get("name"),
            "priority": issue_data.get("fields", {}).get("priority", {}).get("name") if issue_data.get("fields", {}).get("priority") else None,
            "assignee": issue_data.get("fields", {}).get("assignee", {}).get("displayName") if issue_data.get("fields", {}).get("assignee") else "Unassigned",
            "reporter": issue_data.get("fields", {}).get("reporter", {}).get("displayName") if issue_data.get("fields", {}).get("reporter") else None,
            "created": issue_data.get("fields", {}).get("created"),
            "updated": issue_data.get("fields", {}).get("updated"),
            "labels": issue_data.get("fields", {}).get("labels", []),
            "components": [comp.get("name") for comp in issue_data.get("fields", {}).get("components", [])],
            "comments": []
        }
        
        # Add comments to the response
        for comment in comments_data.get("comments", []):
            ticket_details["comments"].append({
                "id": comment.get("id"),
                "author": comment.get("author", {}).get("displayName"),
                "body": comment.get("body"),
                "created": comment.get("created"),
                "updated": comment.get("updated")
            })
        
        return ticket_details
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch JIRA ticket details: {str(e)}"}


# Start the server when this script is run directly
if __name__ == "__main__":
    # For development purposes
    mcp.run()