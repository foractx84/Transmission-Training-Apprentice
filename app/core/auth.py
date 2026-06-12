"""
Azure AD OAuth authentication for the Transmission Apprentice Training App.
"""
import streamlit as st
import msal
from typing import Dict, Optional, Any, List
import requests


class AzureAuth:
    """Handles Azure AD OAuth authentication for Streamlit."""
    
    def __init__(self, config: Dict[str, str]):
        """
        Initialize Azure authentication.
        
        Args:
            config: Dictionary containing Azure configuration:
                - tenant_id: Azure AD tenant ID
                - client_id: Azure AD client ID
                - client_secret: Azure AD client secret
                - redirect_uri: Redirect URI configured in Azure AD
        """
        self.tenant_id = config.get("tenant_id")
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        self.redirect_uri = config.get("redirect_uri", "http://localhost:8501")
        
        # Azure AD endpoints
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"

        # Scopes:
        # - User.Read: basic profile
        # - GroupMember.Read.All: read group memberships via Microsoft Graph
        # - Files.Read.All: read files from SharePoint drives (JPM/HOSD form sync)
        # Admin consent is required in Azure AD for GroupMember.Read.All and Files.Read.All.
        self.scope = ["User.Read", "GroupMember.Read.All", "Files.Read.All"]
        
        # Initialize MSAL app
        self.app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority
        )
        
        # Initialize session state
        if "auth_token" not in st.session_state:
            st.session_state.auth_token = None
        if "user_info" not in st.session_state:
            st.session_state.user_info = None
        if "id_token_claims" not in st.session_state:
            st.session_state.id_token_claims = None
        if "user_groups" not in st.session_state:
            st.session_state.user_groups = None
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return st.session_state.auth_token is not None
    
    def get_authorization_url(self) -> str:
        """Generate authorization URL for OAuth flow."""
        auth_url = (
            f"{self.authority}/oauth2/v2.0/authorize?"
            f"client_id={self.client_id}&"
            f"response_type=code&"
            f"redirect_uri={self.redirect_uri}&"
            f"response_mode=query&"
            f"scope={' '.join(self.scope)}"
        )
        return auth_url
    
    def get_token_from_code(self, authorization_code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token."""
        try:
            result = self.app.acquire_token_by_authorization_code(
                code=authorization_code,
                scopes=self.scope,
                redirect_uri=self.redirect_uri
            )
            
            if "access_token" in result:
                # Store id token claims for roles / groups if present
                st.session_state.id_token_claims = result.get("id_token_claims")
                return result
            else:
                st.error(f"Token acquisition failed: {result.get('error_description', 'Unknown error')}")
                return None
        except Exception as e:
            st.error(f"Error acquiring token: {str(e)}")
            return None
    
    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get basic user information from Microsoft Graph API."""
        if not self.is_authenticated():
            return None
        
        if st.session_state.user_info:
            return st.session_state.user_info
        
        token = st.session_state.auth_token
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers
            )
            
            if response.status_code == 200:
                user_info = response.json()
                st.session_state.user_info = user_info
                return user_info
            else:
                st.error(f"Failed to get user info: {response.status_code}")
                return None
        except Exception as e:
            st.error(f"Error fetching user info: {str(e)}")
            return None

    def get_user_groups(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get Azure AD groups for the current user via Microsoft Graph.

        Returns a list like: [{"id": "...", "name": "Group Name"}, ...]
        """
        if not self.is_authenticated():
            return None

        if st.session_state.user_groups:
            return st.session_state.user_groups

        token = st.session_state.auth_token
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # Get groups the user is a direct member of
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/memberOf?$select=displayName,id",
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                groups_raw = data.get("value", [])

                groups: List[Dict[str, Any]] = []
                for g in groups_raw:
                    name = g.get("displayName")
                    gid = g.get("id")
                    if name and gid:
                        groups.append({"id": gid, "name": name})

                st.session_state.user_groups = groups
                return groups

            # Non-200 response
            st.warning(
                "Could not load groups from Microsoft Graph. "
                f"(HTTP {response.status_code}) – check that the app has 'GroupMember.Read.All' permission."
            )
            return None
        except Exception as e:
            st.error(f"Error fetching user groups: {str(e)}")
            return None

    def get_user_roles(self) -> Optional[List[str]]:
        """
        Get app roles for the current user from the ID token claims.

        Note: App role assignments must be configured in Azure AD and
        emitted in the token (e.g. `roles` claim).
        """
        claims = st.session_state.get("id_token_claims")
        if not claims:
            return None

        roles = claims.get("roles")
        if roles is None:
            return None

        if isinstance(roles, str):
            return [roles]
        if isinstance(roles, list):
            # Ensure all entries are strings
            return [str(r) for r in roles]

        return None
    
    def login(self):
        """Handle login flow."""
        # Check for authorization code in URL
        query_params = st.query_params
        
        if "code" in query_params:
            # Exchange code for token
            code = query_params["code"]
            token_result = self.get_token_from_code(code)
            
            if token_result and "access_token" in token_result:
                st.session_state.auth_token = token_result["access_token"]
                # Clear the code from URL
                st.query_params.clear()
                st.rerun()
            else:
                st.error("Failed to authenticate. Please try again.")
        else:
            # Show login button
            st.title("🔐 SIGN IN")
            st.info("Please sign in with your Azure AD account to continue.")
            
            auth_url = self.get_authorization_url()
            
            if st.button("🔑 Sign in with Azure AD", use_container_width=True, type="primary"):
                st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url}">', unsafe_allow_html=True)
                st.link_button("Click here if not redirected", auth_url)
    
    def logout(self):
        """Handle logout."""
        st.session_state.auth_token = None
        st.session_state.user_info = None
        st.session_state.id_token_claims = None
        st.session_state.user_groups = None
        st.query_params.clear()
        st.success("You have been logged out successfully.")
        st.rerun()
