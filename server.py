# server.py
from mcp.server.fastmcp import FastMCP
import os
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv
import json  # Add this import at the top

# Load environment variables
load_dotenv()

# Create an MCP server
mcp = FastMCP("JIRA Demo")

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


# Helper function to extract text from JIRA descriptions (which can be in various formats)
def get_description_text(description) -> str:
    """Extract plain text from a JIRA description field that could have various formats"""
    if description is None:
        return ""
    
    # If it's a string, return it directly
    if isinstance(description, str):
        return description
    
    # If it's a dict with content (Atlassian Document Format)
    if isinstance(description, dict):
        if "content" in description:
            text_parts = []
            for content_item in description.get("content", []):
                # For paragraph type content
                if content_item.get("type") == "paragraph":
                    for text_node in content_item.get("content", []):
                        if text_node.get("type") == "text":
                            text_parts.append(text_node.get("text", ""))
                # For other types like bulletList, orderedList, etc.
                elif content_item.get("type") in ["bulletList", "orderedList"]:
                    for list_item in content_item.get("content", []):
                        for item_content in list_item.get("content", []):
                            if item_content.get("type") == "paragraph":
                                for text_node in item_content.get("content", []):
                                    if text_node.get("type") == "text":
                                        text_parts.append("• " + text_node.get("text", ""))
            
            return "\n".join(text_parts)
        
        # If it has a raw text field
        if "text" in description:
            return description.get("text", "")
    
    # If it's something else, convert to string
    return str(description)


# Function to extract text from JIRA comment body with complex structure
def extract_comment_text(comment_body) -> str:
    """
    Extract readable text from a JIRA comment body, which can have a complex nested structure.
    Handles different content types like paragraphs, headings, lists, code blocks, etc.
    
    Args:
        comment_body: The comment body object from JIRA API
        
    Returns:
        A formatted string with the readable text content
    """
    if comment_body is None:
        return ""
    
    # If it's already a string, return it directly
    if isinstance(comment_body, str):
        return comment_body
    
    # Handle Atlassian Document Format structure
    if isinstance(comment_body, dict) and "content" in comment_body:
        return _process_content_nodes(comment_body.get("content", []))
    
    # Fallback to string representation
    return str(comment_body)


def _process_content_nodes(nodes, indent_level=0, list_prefix=""):
    """
    Recursively process content nodes from JIRA's Atlassian Document Format
    
    Args:
        nodes: List of content nodes
        indent_level: Current indentation level for nested structures
        list_prefix: Prefix for list items (bullet or number)
        
    Returns:
        Formatted text string
    """
    if not nodes:
        return ""
    
    result = []
    indent = "  " * indent_level
    
    for node in nodes:
        node_type = node.get("type", "")
        
        # Handle different node types
        if node_type == "text":
            # Basic text node
            text = node.get("text", "")
            # Handle links or other text marks
            if node.get("marks"):
                for mark in node.get("marks", []):
                    if mark.get("type") == "link" and "attrs" in mark and "href" in mark["attrs"]:
                        text = f"{text} ({mark['attrs']['href']})"
            result.append(f"{indent}{list_prefix}{text}")
            
        elif node_type == "paragraph":
            # Process paragraph content
            para_text = _process_content_nodes(node.get("content", []), indent_level)
            if para_text:
                result.append(para_text)
                result.append("")  # Add a blank line after paragraphs
            
        elif node_type == "heading":
            # Process heading with appropriate level
            level = node.get("attrs", {}).get("level", 1)
            heading_prefix = "#" * level + " "
            heading_text = _process_content_nodes(node.get("content", []), 0, "")
            result.append(f"{indent}{heading_prefix}{heading_text}")
            result.append("")
            
        elif node_type == "bulletList":
            # Process bullet list items
            for i, item in enumerate(node.get("content", [])):
                item_text = _process_content_nodes(item.get("content", []), indent_level + 1, "• ")
                result.append(item_text)
            
        elif node_type == "orderedList":
            # Process numbered list items
            for i, item in enumerate(node.get("content", [])):
                item_text = _process_content_nodes(item.get("content", []), indent_level + 1, f"{i+1}. ")
                result.append(item_text)
            
        elif node_type == "listItem":
            # Process list item content
            for content in node.get("content", []):
                content_text = _process_content_nodes([content], indent_level, list_prefix)
                result.append(content_text)
            
        elif node_type == "codeBlock":
            # Process code block
            code_text = "\n".join([node.get("text", "") for node in node.get("content", [])])
            result.append(f"{indent}```\n{code_text}\n{indent}```")
            result.append("")
            
        elif node_type == "rule":
            # Horizontal rule
            result.append(f"{indent}---")
            result.append("")
            
        elif node_type == "mention":
            # Handle mentions
            mention_text = node.get("attrs", {}).get("text", "@unknown")
            result.append(f"{indent}{list_prefix}{mention_text}")
            
        elif node_type == "hardBreak":
            # Line break
            result.append("")
            
        elif "content" in node:
            # Recursively process any other node with content
            nested_text = _process_content_nodes(node.get("content", []), indent_level, list_prefix)
            result.append(nested_text)
    
    # Join all processed text, handling nested structures properly
    joined = "\n".join([r for r in result if r is not None and r != []])
    return joined


# Add JIRA board tickets endpoint
@mcp.tool()
def list_jira_tickets(board_id: int = 45, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    List tickets (issues) from a specified JIRA board
    
    Args:
        board_id: The ID of the JIRA board (default: 45)
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
        Detailed information about the ticket including description and comments in a readable format
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
        
        # Log the full data to a file for inspection
        pretty_print_to_file(issue_data, f"jira_ticket_{ticket_key}_data.json")
        
        # Get comments separately with the comments API
        comments_url = f"{base_url}/rest/api/3/issue/{ticket_key}/comment"
        comments_response = requests.get(comments_url, headers=get_jira_headers())
        comments_response.raise_for_status()
        
        comments_data = comments_response.json()
        
        # Log comments data
        pretty_print_to_file(comments_data, f"jira_ticket_{ticket_key}_comments.json")
        
        # Extract field names mapping
        field_names = issue_data.get("names", {})
        
        # Get rendered fields (human-readable HTML content)
        rendered_fields = issue_data.get("renderedFields", {})
        
        # Format comments in a readable way
        formatted_comments = []
        for comment in comments_data.get("comments", []):
            comment_body = comment.get("body", "")
            author = comment.get("author", {}).get("displayName", "Unknown")
            created = comment.get("created", "")
            
            # Extract text from comment body using the helper function
            readable_comment_body = extract_comment_text(comment_body)
            
            formatted_comment = (
                f"Comment by {author} on {created}:\n"
                f"{readable_comment_body}"
            )
            formatted_comments.append(formatted_comment)
        
        # Create a formatted ticket representation with main fields and custom fields
        formatted_custom_fields = []
        for field_id, field_name in field_names.items():
            # Only include fields that have rendered content and are custom fields
            if field_id.startswith("customfield_") and field_id in rendered_fields and rendered_fields.get(field_id):
                formatted_custom_fields.append(
                    f"## {field_name}\n{rendered_fields.get(field_id)}"
                )
        
        # Combine all information into a well-structured format
        ticket_formatted = {
            "ticket_key": issue_data.get("key"),
            "ticket_info": (
                f"# {issue_data.get('key')} - {issue_data.get('fields', {}).get('summary')}\n\n"
                f"**Type:** {issue_data.get('fields', {}).get('issuetype', {}).get('name')}\n"
                f"**Status:** {issue_data.get('fields', {}).get('status', {}).get('name')}\n"
                f"**Priority:** {issue_data.get('fields', {}).get('priority', {}).get('name') if issue_data.get('fields', {}).get('priority') else 'None'}\n"
                f"**Assignee:** {issue_data.get('fields', {}).get('assignee', {}).get('displayName') if issue_data.get('fields', {}).get('assignee') else 'Unassigned'}\n"
                f"**Reporter:** {issue_data.get('fields', {}).get('reporter', {}).get('displayName') if issue_data.get('fields', {}).get('reporter') else 'None'}\n"
                f"**Created:** {issue_data.get('fields', {}).get('created')}\n"
                f"**Updated:** {issue_data.get('fields', {}).get('updated')}\n\n"
                f"## Description\n{rendered_fields.get('description') or 'No description provided.'}\n\n"
                + ("\n\n".join(formatted_custom_fields) if formatted_custom_fields else "") + "\n\n"
                f"## Comments\n" + ("\n\n".join(formatted_comments) if formatted_comments else "No comments.")
            )
        }
        
        return ticket_formatted
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch JIRA ticket details: {str(e)}"}


# Add a tool to get all available fields for a JIRA ticket
@mcp.tool()
def get_jira_ticket_all_fields(ticket_key: str) -> Dict[str, Any]:
    """
    Get all fields (including custom fields) for a specific JIRA ticket
    
    Args:
        ticket_key: The key of the JIRA ticket (e.g., 'SUP-3591')
        
    Returns:
        All fields available for the ticket, formatted in a human-readable way
    """
    base_url = os.getenv("JIRA_BASE_URL", "https://wovnio.atlassian.net")
    
    # Endpoint to get issue details
    url = f"{base_url}/rest/api/3/issue/{ticket_key}"
    
    # Parameters to expand additional information
    params = {
        "expand": "names,schema,editmeta,renderedFields,comment"
    }
    
    try:
        # Get the ticket with all fields
        response = requests.get(url, headers=get_jira_headers(), params=params)
        response.raise_for_status()
        
        issue_data = response.json()
        
        # Extract field names mapping
        field_names = issue_data.get("names", {})
        
        # Get rendered fields (human-readable HTML content)
        rendered_fields = issue_data.get("renderedFields", {})
        
        # Format all fields in a readable way
        formatted_fields = []
        for field_id, field_name in field_names.items():
            # Try to get the rendered value first, then fall back to regular value
            field_value = ""
            if field_id in rendered_fields and rendered_fields.get(field_id):
                field_value = rendered_fields.get(field_id)
            elif field_id in issue_data.get("fields", {}):
                raw_value = issue_data.get("fields", {}).get(field_id)
                
                # Special handling for comment field
                if field_id == "comment" and isinstance(raw_value, dict) and "comments" in raw_value:
                    comment_sections = []
                    for comment in raw_value.get("comments", []):
                        comment_body = comment.get("body", "")
                        author = comment.get("author", {}).get("displayName", "Unknown")
                        created = comment.get("created", "")
                        
                        # Extract text from comment body using the helper function
                        readable_comment_body = extract_comment_text(comment_body)
                        
                        comment_sections.append(
                            f"### Comment by {author} on {created}:\n"
                            f"{readable_comment_body}\n"
                        )
                    
                    field_value = "\n".join(comment_sections)
                elif isinstance(raw_value, dict) and "displayName" in raw_value:
                    field_value = raw_value.get("displayName")
                elif isinstance(raw_value, list):
                    if all(isinstance(item, dict) and "name" in item for item in raw_value):
                        field_value = ", ".join(item.get("name") for item in raw_value)
                    else:
                        field_value = str(raw_value)
                else:
                    field_value = str(raw_value) if raw_value is not None else ""
            
            # Only include fields that have content
            if field_value and field_value != "None" and field_value != "null":
                formatted_fields.append(
                    f"## {field_name}\n{field_value}"
                )
        
        # Return the formatted output
        return {
            "ticket_key": issue_data.get("key"),
            "formatted_content": (
                f"# {issue_data.get('key')} - Field Details\n\n"
                + "\n\n".join(formatted_fields)
            )
        }
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch JIRA ticket fields: {str(e)}"}


# Helper function to pretty print data to a file for debugging
def pretty_print_to_file(data, filename="jira_data_log.json"):
    """
    Pretty print data to a file for debugging purposes
    
    Args:
        data: The data to pretty print
        filename: The name of the file to write to
    """
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Data written to {filename}")
    except Exception as e:
        print(f"Error writing data to file: {e}")

# Start the server when this script is run directly
if __name__ == "__main__":
    # For development purposes
    mcp.run()