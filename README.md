# Transmission Apprentice Training App

A Streamlit application for transmission apprentice training and development with Azure AD OAuth authentication.

## Features

- 🔐 Azure AD OAuth 2.0 authentication
- 🔒 Secure credential management via environment variables
- 👤 User information display
- 📚 Training modules and content (to be implemented)

## Project Structure

```
.
├── app/
│   ├── main.py                 # Main Streamlit application
│   ├── core/                   # Core app infrastructure
│   │   ├── auth.py             # Azure OAuth authentication
│   │   └── config.py           # Configuration management
│   └── pages/                  # Additional app pages (optional)
├── .env.example                # Example environment variables
├── .gitignore                  # Git ignore file
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Azure AD Application

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Create a new app registration or select an existing one
4. Note down the following values:
   - **Tenant ID** (Directory ID)
   - **Client ID** (Application ID)
   - **Object ID** (for reference)
5. Create a client secret:
   - Go to **Certificates & secrets**
   - Click **New client secret**
   - Copy the secret value (you'll only see it once!)

### 3. Configure Redirect URI in Azure AD

1. In your Azure AD app registration, go to **Authentication**
2. Add a redirect URI:
   - For local development: `http://localhost:8501`
   - For production: Your production URL
3. Select **Web** as the platform type
4. Save the changes

### 4. Set Up Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   copy .env.example .env
   ```

2. Edit `.env` and fill in your Azure AD credentials:
   ```
   AZURE_TENANT_ID=your-tenant-id
   AZURE_CLIENT_ID=your-client-id
   AZURE_CLIENT_SECRET=your-client-secret
   AZURE_OBJECT_ID=your-object-id
   AZURE_REDIRECT_URI=http://localhost:8501
   ```

### 5. Run the Application

```bash
streamlit run app/main.py
```

The app will open in your browser at `http://localhost:8501`.

## Usage

1. **Authentication**: When you first access the app, you'll be prompted to sign in with Azure AD.

2. **Main App**: After successful authentication, you'll see the main training application interface.

3. **Logout**: Use the logout button in the sidebar to sign out.

## Azure AD Permissions

The app uses the following Microsoft Graph API permissions:
- **User.Read**: Read user profile information

Make sure these permissions are granted admin consent in your Azure AD app registration if required.

## Security Notes

- Never commit the `.env` file to version control
- Keep your client secret secure
- Use environment variables or secure secret management in production
- The `.env` file is already included in `.gitignore`

## Troubleshooting

### Authentication Fails

- Verify your Azure AD credentials are correct
- Check that the redirect URI matches exactly in Azure AD
- Ensure the client secret hasn't expired
- Verify the app has the required permissions

### Configuration Not Loading

- Make sure the `.env` file exists in the project root
- Check that all required environment variables are set
- Restart the Streamlit app after changing configuration

### Cleaning Python Cache Files

Python automatically creates `__pycache__` folders containing `.pyc` (bytecode) files to speed up imports. These are safe to delete and will be regenerated automatically. They're already ignored by git.

To clean them manually:
```bash
# PowerShell
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# Or manually delete any __pycache__ folders you see
```

## Development

### Adding New Pages

Create new files in `app/pages/` with the format:
- `2_📊_Dashboard.py`
- `3_📈_Analytics.py`
etc.

Streamlit will automatically detect and add them to the navigation.

### Adding Training Features

Training modules and features can be added to the main app or as separate pages in `app/pages/`. The authentication infrastructure is already in place in `app/core/auth.py`.

### Extending Authentication

The `AzureAuth` class in `app/core/auth.py` can be extended to:
- Add more Microsoft Graph API scopes
- Implement role-based access control
- Add token refresh logic
- Customize user information retrieval
