package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/joho/godotenv"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
	"google.golang.org/api/gmail/v1"
	"google.golang.org/api/option"
)

type EmailWatcher struct {
	srv            *gmail.Service
	config         *oauth2.Config
	client         *http.Client
	lastProcessedTime time.Time
	processWindow  time.Duration
}

func NewEmailWatcher(config *oauth2.Config, client *http.Client) *EmailWatcher {
	return &EmailWatcher{
		config:         config,
		client:         client,
		processWindow:  24 * time.Hour, // Default to 24 hours
	}
}

func (ew *EmailWatcher) loadLastProcessedTime() error {
	configDir, err := os.UserConfigDir()
	if err != nil {
		return err
	}
	
	tokenDir := filepath.Join(configDir, "ai-thing", "tokens")
	if err := os.MkdirAll(tokenDir, 0700); err != nil {
		return err
	}

	lastProcessedFile := filepath.Join(tokenDir, "last_processed_time.json")
	
	data, err := os.ReadFile(lastProcessedFile)
	if os.IsNotExist(err) {
		// If file doesn't exist, set to 24 hours ago
		ew.lastProcessedTime = time.Now().Add(-ew.processWindow)
		return nil
	} else if err != nil {
		return err
	}

	var lastTime time.Time
	if err := json.Unmarshal(data, &lastTime); err != nil {
		return err
	}

	ew.lastProcessedTime = lastTime
	return nil
}

func (ew *EmailWatcher) saveLastProcessedTime(t time.Time) error {
	configDir, err := os.UserConfigDir()
	if err != nil {
		return err
	}
	
	tokenDir := filepath.Join(configDir, "ai-thing", "tokens")
	if err := os.MkdirAll(tokenDir, 0700); err != nil {
		return err
	}

	lastProcessedFile := filepath.Join(tokenDir, "last_processed_time.json")
	
	data, err := json.Marshal(t)
	if err != nil {
		return err
	}

	return os.WriteFile(lastProcessedFile, data, 0600)
}

func (ew *EmailWatcher) authenticate(ctx context.Context) error {
	// Get the token file path
	tokenPath, err := getTokenFilePath()
	if err != nil {
		return fmt.Errorf("could not determine token file path: %v", err)
	}

	// Try to read the existing token
	tokenFile, err := os.ReadFile(tokenPath)
	var token *oauth2.Token
	if err == nil {
		if err := json.Unmarshal(tokenFile, &token); err != nil {
			log.Printf("Could not parse existing token: %v", err)
		}
	}

	// If we have a token, try to use it
	if token != nil {
		tokenSource := ew.config.TokenSource(ctx, token)
		
		// Try to refresh the token
		refreshedToken, err := tokenSource.Token()
		if err != nil {
			log.Printf("Could not refresh token: %v", err)
			token = nil
		} else {
			token = refreshedToken
			
			// Try to create service with this token
			srv, err := gmail.NewService(ctx, option.WithTokenSource(tokenSource))
			if err != nil {
				log.Printf("Failed to create Gmail service: %v", err)
				token = nil
			} else {
				// Verify token has correct permissions
				_, err = srv.Users.GetProfile("me").Do()
				if err != nil {
					log.Printf("Insufficient token permissions: %v", err)
					token = nil
				} else {
					// Token is valid, save it and return
					ew.srv = srv
					return saveToken(token)
				}
			}
		}
	}

	// If no valid token, proceed with manual authentication
	authURL := ew.config.AuthCodeURL("state", oauth2.AccessTypeOffline)
	fmt.Printf("Go to the following link in your browser: %v\n", authURL)
	fmt.Println("Enter the authorization code:")
	var code string
	fmt.Scanln(&code)

	// Exchange authorization code for token
	token, err = ew.config.Exchange(ctx, code)
	if err != nil {
		return fmt.Errorf("failed to exchange token: %v", err)
	}

	// Create Gmail service with new token
	srv, err := gmail.NewService(ctx, option.WithTokenSource(ew.config.TokenSource(ctx, token)))
	if err != nil {
		return fmt.Errorf("failed to create Gmail service: %v", err)
	}

	// Save the token
	if err := saveToken(token); err != nil {
		log.Printf("Warning: Could not save token: %v", err)
	}

	ew.srv = srv
	return nil
}

func (ew *EmailWatcher) watchEmails(ctx context.Context) error {
	if err := ew.loadLastProcessedTime(); err != nil {
		log.Printf("Error loading last processed time: %v", err)
		return err
	}

	// List unread messages
	user := "me"
	listCall := ew.srv.Users.Messages.List(user).Q(fmt.Sprintf("is:unread after:%d", ew.lastProcessedTime.Unix()))
	
	r, err := listCall.Do()
	if err != nil {
		return fmt.Errorf("unable to retrieve messages: %v", err)
	}

	processedCount := 0
	lastProcessedTime := ew.lastProcessedTime

	for _, m := range r.Messages {
		msg, err := ew.srv.Users.Messages.Get(user, m.Id).Do()
		if err != nil {
			log.Printf("Error getting message %s: %v", m.Id, err)
			continue
		}

		// Parse message timestamp
		msgTime := time.Unix(msg.InternalDate/1000, 0)
		
		// Skip if message is older than last processed time
		if msgTime.Before(ew.lastProcessedTime) {
			continue
		}

		// Update last processed time if this message is newer
		if msgTime.After(lastProcessedTime) {
			lastProcessedTime = msgTime
		}

		// Extract sender and subject
		var from, subject string
		for _, header := range msg.Payload.Headers {
			switch header.Name {
			case "From":
				from = header.Value
			case "Subject":
				subject = header.Value
			}
		}

		// Process message
		ew.processMessage(from, subject)
		processedCount++

		// Mark as read
		_, err = ew.srv.Users.Messages.Modify(user, m.Id, &gmail.ModifyMessageRequest{
			RemoveLabelIds: []string{"UNREAD"},
		}).Do()
		if err != nil {
			log.Printf("Error marking message as read: %v", err)
		}
	}

	// Save the latest processed time
	if err := ew.saveLastProcessedTime(lastProcessedTime); err != nil {
		log.Printf("Error saving last processed time: %v", err)
	}

	log.Printf("Processed %d new email(s)", processedCount)
	return nil
}

func (ew *EmailWatcher) processMessage(from, subject string) {
	log.Printf("New email from %s with subject: %s", from, subject)
	// Add your custom processing logic here
}

func getTokenFilePath() (string, error) {
	// Preferred location: ~/.config/ai-thing/tokens/gmail_token.json
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("could not get home directory: %v", err)
	}
	tokenPath := filepath.Join(homeDir, ".config", "ai-thing", "tokens", "gmail_token.json")

	// Ensure the directory exists
	if err := os.MkdirAll(filepath.Dir(tokenPath), 0700); err != nil {
		return "", fmt.Errorf("could not create token directory: %v", err)
	}

	// Fallback: current working directory
	if _, err := os.Stat(tokenPath); os.IsNotExist(err) {
		currentDir, err := os.Getwd()
		if err != nil {
			return "", fmt.Errorf("could not get current working directory: %v", err)
		}
		localTokenPath := filepath.Join(currentDir, "gmail_token.json")

		// If a token exists in the local directory, use it and move it to the preferred location
		if _, err := os.Stat(localTokenPath); err == nil {
			log.Println("Found token in local directory. Migrating to preferred location.")
			if err := os.Rename(localTokenPath, tokenPath); err != nil {
				return "", fmt.Errorf("could not migrate token: %v", err)
			}
		}
	}

	return tokenPath, nil
}

func saveToken(token *oauth2.Token) error {
	// Get the token file path
	tokenPath, err := getTokenFilePath()
	if err != nil {
		return fmt.Errorf("could not determine token file path: %v", err)
	}

	// Marshal the token to JSON
	tokenJSON, err := json.MarshalIndent(token, "", "  ")
	if err != nil {
		return fmt.Errorf("could not marshal token: %v", err)
	}

	// Write the token to file with restricted permissions
	if err := os.WriteFile(tokenPath, tokenJSON, 0600); err != nil {
		return fmt.Errorf("could not write token file %s: %v", tokenPath, err)
	}

	log.Printf("Token saved to %s", tokenPath)
	return nil
}

func init() {
	// Load .env file
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found")
	}
}

func main() {
	// Get client ID from environment
	clientID := os.Getenv("GOOGLE_CLIENT_ID")
	clientSecret := os.Getenv("GOOGLE_CLIENT_SECRET")

	// Validate environment variables
	if clientID == "" || clientSecret == "" {
		log.Fatalf("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in environment")
	}

	// OAuth 2.0 configuration
	config := &oauth2.Config{
		ClientID:     clientID,
		ClientSecret: clientSecret,
		Scopes:       []string{gmail.GmailModifyScope},
		Endpoint:     google.Endpoint,
		RedirectURL:  "urn:ietf:wg:oauth:2.0:oob",
	}

	// Create email watcher
	watcher := NewEmailWatcher(config, &http.Client{})

	// Authenticate
	ctx := context.Background()
	if err := watcher.authenticate(ctx); err != nil {
		log.Fatalf("Authentication error: %v", err)
	}

	// Watch emails
	log.Println("Starting email watcher. Press Ctrl+C to stop.")
	if err := watcher.watchEmails(ctx); err != nil {
		log.Fatalf("Error watching emails: %v", err)
	}
}
