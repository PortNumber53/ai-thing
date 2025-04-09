# Email Watcher Service

## Prerequisites
- Go 1.21+
- Google Cloud Project with Gmail API enabled
- OAuth 2.0 Credentials

## Setup
1. Create a Google Cloud Project
2. **IMPORTANT: Enable Gmail API**
   - Go to [Google Cloud Console](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - Click "Enable" for the Gmail API
3. Create OAuth 2.0 Credentials (OAuth client ID)
   - Select "Desktop app" as the application type
4. Set environment variables:
   ```bash
   export GOOGLE_CLIENT_ID=your_client_id
   export GOOGLE_CLIENT_SECRET=your_client_secret
   ```

## Credentials Setup

### Option 1: Environment Variables
```bash
export GOOGLE_CLIENT_ID=your_client_id
export GOOGLE_CLIENT_SECRET=your_client_secret
```

### Option 2: Credentials File
1. Copy `credentials.example` to `.env`
2. Fill in your Google OAuth credentials
3. Ensure `.env` is in `.gitignore`

### Obtaining Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API
4. Go to "Credentials" section
5. Create an OAuth 2.0 Client ID
   - Application Type: Desktop app
6. Download the credentials JSON
7. Extract `client_id` and `client_secret`

### Security Warnings
- NEVER commit credentials to version control
- Use environment variables or `.env` file
- Protect your `.env` file with strict file permissions
- Rotate credentials periodically

## Token Persistence
- The application now saves your OAuth token in `.gmail_token.json`
- Subsequent runs will use the saved token without requiring re-authentication
- Token is automatically refreshed if expired
- Token file is saved with restricted permissions (0600)

### Security Notes
- The token file is saved in the same directory as the executable
- Keep the token file secure and do not share it
- The token can be deleted to force re-authentication

## Running the Application
```bash
go mod tidy
go run src/main.go
```

### First-Time Authorization
1. The app will print an authorization URL
2. Open the URL in your browser
3. Authorize the application
4. Copy the authorization code back to the terminal

## How it Works
- Connects to Gmail via OAuth 2.0
- Watches for unread emails every 5 minutes
- Allows custom message processing logic

## Customization
Modify the `processMessage` method in `main.go` to add your specific email processing logic.

## Security Notes
- Never commit your OAuth credentials
- Use environment variables or `.env` file
- Rotate credentials periodically
