"""Handles federated connector authentication and authorization flow for Google Discovery Engine."""
import os
import logging
import requests
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()
logger = logging.getLogger(__name__)

def _get_location() -> str:
    return os.environ.get("GOOGLE_DISCOVERY_LOCATION", os.environ.get("LOCATION", "global"))

def _get_endpoint(location: str) -> str:
    if location != "global":
        return f"{location}-discoveryengine.googleapis.com"
    return "discoveryengine.googleapis.com"

def _get_project_id() -> str:
    return os.environ.get("GCP_PROJECT_ID", "")

def _get_project_number() -> str:
    return os.environ.get("GCP_PROJECT_NUMBER") or _get_project_id()

def _get_engine_id() -> str:
    return os.environ.get("ENGINE_ID", "")

def allowlist_custom_domain(token: str, custom_domain_url: str) -> bool:
    """Allowlists the custom domain on the widget config."""
    location = _get_location()
    endpoint = _get_endpoint(location)
    project_id = _get_project_id()
    project_number = _get_project_number()
    engine_id = _get_engine_id()
    version = "v1alpha"
    widget_config_id = "default_search_widget_config"
    
    url = f"https://{endpoint}/{version}/projects/{project_number}/locations/{location}/collections/default_collection/engines/{engine_id}/widgetConfigs/{widget_config_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    update_request = {
        "name": f"projects/{project_number}/locations/{location}/collections/default_collection/engines/{engine_id}/widgetConfigs/{widget_config_id}",
        "accessSettings": {
            "allowlistedDomains": [custom_domain_url]
        }
    }
    update_mask = {"updateMask": "accessSettings"}
    
    logger.info(f"Allowlisting custom domain: {custom_domain_url} on {url}")
    try:
        response = requests.patch(url, headers=headers, json=update_request, params=update_mask, timeout=30)
        if response.status_code == 200:
            logger.info("Widget config custom domain allowlisted successfully.")
            return True
        else:
            logger.warning(f"Warning allowlisting domain {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to call REST API for allowlist: {e}")
        return False

def get_widget_config(token: str, custom_domain_url: str = None) -> Optional[Dict]:
    """Retrieves widget configuration containing connector states and authorization URIs."""
    if custom_domain_url:
        allowlist_custom_domain(token, custom_domain_url)
    
    location = _get_location()
    endpoint = _get_endpoint(location)
    project_id = _get_project_id()
    project_number = _get_project_number()
    engine_id = _get_engine_id()
    version = "v1alpha"
    widget_config_id = "default_search_widget_config"
    
    url = f"https://{endpoint}/{version}/projects/{project_number}/locations/{location}/collections/default_collection/engines/{engine_id}/widgetConfigs/{widget_config_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    params = {}
    if custom_domain_url:
        params["getWidgetConfigRequestOption.customDomain"] = custom_domain_url
    
    logger.info(f"Fetching Widget Config from: {url}")
    try:
        response = requests.get(url, headers=headers, params=params if params else None, timeout=30)
        if response.status_code == 200:
            logger.info("Widget Config Retrieved Successfully")
            return response.json()
        else:
            logger.error(f"Error getting widget config {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Failed to call REST API for get_widget_config: {e}")
        return None

def parse_connectors(widget_data: Dict) -> List[Dict]:
    """Parses widget_data dictionary to extract connector info and auth URLs."""
    connectors_info = []
    if not widget_data or 'collectionComponents' not in widget_data:
        return connectors_info
        
    for component in widget_data['collectionComponents']:
        connector_id = component.get('id')
        if not connector_id or connector_id == 'default_collection':
            continue
            
        display_name = component.get('dataSourceDisplayName') or component.get('displayName', connector_id)
        data_source = component.get('dataSource', 'unknown')
        auth_state_data = component.get('connectorAuthState', {})
        auth_state = auth_state_data.get('authState', 'NOT_AUTHORIZED')
        authorization_uri = auth_state_data.get('authorizationUri') or component.get('federatedSearchConnectorAuthUri', 'N/A')
        
        entity_ids = []
        if 'dataStoreComponents' in component:
            for ds_component in component['dataStoreComponents']:
                if ds_component.get('id'):
                    entity_ids.append(ds_component['id'])
                    
        conn_detail = {
            'id': connector_id,
            'displayName': display_name,
            'dataSource': data_source,
            'authState': auth_state,
            'authorizationUri': authorization_uri,
            'entityIds': entity_ids
        }
        connectors_info.append(conn_detail)
    return connectors_info

def get_federated_connectors(token: str, custom_domain_url: str = None) -> List[Dict]:
    """High-level function to get all federated connectors and their current auth statuses."""
    widget_data = get_widget_config(token, custom_domain_url=None)
    if not widget_data:
        return []
    return parse_connectors(widget_data)

def post_refresh_token(token: str, connector_id: str, access_token_redirect_uri: str) -> Dict:
    """Posts the full redirect URI obtained from OAuth callback to acquire and store refresh token."""
    location = _get_location()
    endpoint = _get_endpoint(location)
    project_id = _get_project_id()
    project_number = _get_project_number()
    version = "v1alpha"
    
    url = f"https://{endpoint}/{version}/projects/{project_number}/locations/{location}/collections/{connector_id}/dataConnector:acquireAndStoreRefreshToken"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    request_body = {
        "fullRedirectUri": access_token_redirect_uri
    }
    logger.info(f"Posting refresh token to: {url}")
    response = requests.post(url, headers=headers, json=request_body, timeout=30)
    if response.status_code == 200:
        logger.info("Refresh Token Stored Successfully")
        return response.json()
    else:
        raise ValueError(f"Error storing refresh token ({response.status_code}): {response.text}")

def change_connector_auth(token: str, connector_id: str, auth_state: str) -> Dict:
    """Calls UpdateEngineUserData API to update connector state to AUTHORIZED or EXPIRED."""
    location = _get_location()
    endpoint = _get_endpoint(location)
    project_id = _get_project_id()
    project_num = _get_project_number()
    engine_id = _get_engine_id()
    version = "v1alpha"
    
    connector_name = f"projects/{project_num}/locations/{location}/collections/{connector_id}/dataConnector"
    engine_name = f"https://{endpoint}/{version}/projects/{project_num}/locations/{location}/collections/default_collection/engines/{engine_id}"
    get_url = f"{engine_name}:getEngineUserData"
    update_url = f"{engine_name}:updateEngineUserData"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    logger.info(f"Fetching EngineUserData from: {get_url}")
    resp = requests.post(get_url, headers=headers, timeout=30)
    engine_user_data = resp.json() if resp.status_code == 200 else {}
    
    request_body = engine_user_data
    if 'connectorAuthStates' not in request_body:
        request_body['connectorAuthStates'] = []
        
    connector_found = False
    for connector_state in request_body['connectorAuthStates']:
        existing_dc = connector_state.get('dataConnector', '')
        if f"/collections/{connector_id}/dataConnector" in existing_dc:
            connector_state['authState'] = auth_state
            connector_found = True
            break
            
    if not connector_found:
        request_body['connectorAuthStates'].append({
            'dataConnector': connector_name,
            'authState': auth_state
        })
        
    update_request_body = {
        'engine': f"projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}",
        'engineUserData': {
            'connectorAuthStates': request_body['connectorAuthStates']
        },
        'addEntitiesOnly': True
    }
    params = {"updateMask": "connectorAuthStates"}
    
    logger.info(f"Updating DataConnector states at: {update_url}")
    update_resp = requests.post(update_url, headers=headers, params=params, json=update_request_body, timeout=30)
    if update_resp.status_code == 200:
        logger.info(f"Data Connector State Updated to {auth_state} Successfully")
        return update_resp.json()
    else:
        raise ValueError(f"Error updating connector auth state ({update_resp.status_code}): {update_resp.text}")

def authorize_connector(token: str, connector_id: str, redirect_uri: str) -> Dict:
    """Completes the authorization flow for a federated connector."""
    post_refresh_token(token, connector_id, redirect_uri)
    return change_connector_auth(token, connector_id, "AUTHORIZED")

def unauthorize_connector(token: str, connector_id: str) -> Dict:
    """Unauthorizes a connector by updating its state to EXPIRED."""
    return change_connector_auth(token, connector_id, "EXPIRED")

def sync_workspace_connectors(token: str):
    """Automatically synchronizes Google Workspace connector states (Drive, Mail, Calendar) to AUTHORIZED in EngineUserData."""
    try:
        connectors = get_federated_connectors(token)
        for conn in connectors:
            if conn.get('dataSource') in ['google_drive', 'google_mail', 'google_calendar']:
                if conn.get('authState') != 'AUTHORIZED':
                    logger.debug(f"Attempting to sync Google Workspace connector {conn['id']} state to AUTHORIZED")
                    try:
                        change_connector_auth(token, conn['id'], "AUTHORIZED")
                    except Exception as sub_e:
                        logger.debug(f"Optional widget state sync bypassed ({sub_e})")
    except Exception as e:
        logger.debug(f"Background Workspace connector sync check completed ({e})")

