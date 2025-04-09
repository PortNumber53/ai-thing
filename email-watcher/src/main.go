package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
	"google.golang.org/api/gmail/v1"
	"google.golang.org/api/option"
)

type EmailWatcher struct {
	service *gmail.Service
	config  *oauth2.Config
	token   *oauth2.Token
	lastProcessedEmailID string
}

const (
	tokenFileName = "gmail_token.json"
	tokenSubdir   = ".config/ai-thing/tokens"
	lastEmailIDFileName = "last_processed_email.json"
)

// Structure to save last processed email ID
type LastProcessedEmail struct {
	EmailID string `json:"email_id"`
}

func getTokenFilePath() (string, error) {
	// Preferred location: ~/.config/ai-thing/tokens/gmail_token.json
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("could not get home directory: %v", err)
	}
	tokenPath := filepath.Join(homeDir, tokenSubdir, tokenFileName)

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
		localTokenPath := filepath.Join(currentDir, tokenFileName)

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

func newEmailWatcher() (*EmailWatcher, error) {
	// OAuth 2.0 configuration
	config := &oauth2.Config{
		ClientID:     os.Getenv("GOOGLE_CLIENT_ID"),
		ClientSecret: os.Getenv("GOOGLE_CLIENT_SECRET"),
		Scopes:       []string{gmail.GmailReadonlyScope},
		Endpoint:     google.Endpoint,
		RedirectURL:  "urn:ietf:wg:oauth:2.0:oob",
	}

	return &EmailWatcher{
		config: config,
	}, nil
}

// loadToken attempts to load a previously saved token
func (ew *EmailWatcher) loadToken() error {
	// Get the token file path
	tokenPath, err := getTokenFilePath()
	if err != nil {
		return fmt.Errorf("could not determine token file path: %v", err)
	}

	// Try to read the token file
	tokenFile, err := os.ReadFile(tokenPath)
	if err != nil {
		return fmt.Errorf("could not read token file %s: %v", tokenPath, err)
	}

	// Unmarshal the token
	var token oauth2.Token
	if err := json.Unmarshal(tokenFile, &token); err != nil {
		return fmt.Errorf("could not parse token: %v", err)
	}

	// Check if the token is expired and can be refreshed
	tokenSource := ew.config.TokenSource(context.Background(), &token)
	refreshedToken, err := tokenSource.Token()
	if err != nil {
		return fmt.Errorf("could not refresh token: %v", err)
	}

	ew.token = refreshedToken
	return nil
}

// saveToken saves the token to a file
func (ew *EmailWatcher) saveToken() error {
	// Get the token file path
	tokenPath, err := getTokenFilePath()
	if err != nil {
		return fmt.Errorf("could not determine token file path: %v", err)
	}

	// Marshal the token to JSON
	tokenJSON, err := json.MarshalIndent(ew.token, "", "  ")
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

func (ew *EmailWatcher) authenticate() error {
	// First, try to load an existing token
	err := ew.loadToken()
	if err == nil {
		// Token loaded successfully, create service with this token
		service, err := gmail.NewService(context.Background(), option.WithTokenSource(ew.config.TokenSource(context.Background(), ew.token)))
		if err != nil {
			return fmt.Errorf("failed to create Gmail service with saved token: %v", err)
		}
		ew.service = service
		return nil
	}

	// Log the error for debugging, but proceed with manual authentication
	log.Printf("Could not load existing token: %v", err)

	// If loading token fails, proceed with manual authentication
	authURL := ew.config.AuthCodeURL("state", oauth2.AccessTypeOffline)
	fmt.Printf("Go to the following link in your browser: %v\n", authURL)
	fmt.Print("Enter authorization code: ")
	var code string
	fmt.Scanln(&code)

	// Exchange authorization code for token
	token, err := ew.config.Exchange(context.Background(), code)
	if err != nil {
		return fmt.Errorf("failed to exchange token: %v", err)
	}

	// Create Gmail service
	service, err := gmail.NewService(context.Background(), option.WithTokenSource(ew.config.TokenSource(context.Background(), token)))
	if err != nil {
		return fmt.Errorf("failed to create Gmail service: %v", err)
	}

	// Save the token for future use
	ew.token = token
	ew.service = service
	if err := ew.saveToken(); err != nil {
		log.Printf("Warning: Could not save token: %v", err)
	}

	return nil
}

func (ew *EmailWatcher) saveLastProcessedEmailID(emailID string) error {
	// Get the file path for storing last processed email ID
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("could not get home directory: %v", err)
	}
	filePath := filepath.Join(homeDir, tokenSubdir, lastEmailIDFileName)

	// Ensure the directory exists
	if err := os.MkdirAll(filepath.Dir(filePath), 0700); err != nil {
		return fmt.Errorf("could not create directory: %v", err)
	}

	// Create the struct to save
	lastEmail := LastProcessedEmail{EmailID: emailID}

	// Marshal to JSON
	jsonData, err := json.MarshalIndent(lastEmail, "", "  ")
	if err != nil {
		return fmt.Errorf("could not marshal last email ID: %v", err)
	}

	// Write to file
	if err := os.WriteFile(filePath, jsonData, 0600); err != nil {
		return fmt.Errorf("could not write last email ID file: %v", err)
	}

	return nil
}

func (ew *EmailWatcher) loadLastProcessedEmailID() (string, error) {
	// Get the file path for last processed email ID
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("could not get home directory: %v", err)
	}
	filePath := filepath.Join(homeDir, tokenSubdir, lastEmailIDFileName)

	// Read the file
	fileData, err := os.ReadFile(filePath)
	if err != nil {
		// If file doesn't exist, it's not an error - just return empty string
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", fmt.Errorf("could not read last email ID file: %v", err)
	}

	// Unmarshal the JSON
	var lastEmail LastProcessedEmail
	if err := json.Unmarshal(fileData, &lastEmail); err != nil {
		return "", fmt.Errorf("could not parse last email ID: %v", err)
	}

	return lastEmail.EmailID, nil
}

func (ew *EmailWatcher) watchEmails() error {
	// Load the last processed email ID
	lastProcessedEmailID, err := ew.loadLastProcessedEmailID()
	if err != nil {
		log.Printf("Warning: Could not load last processed email ID: %v", err)
	}

	// List unread messages
	user := "me"
	r, err := ew.service.Users.Messages.List(user).Q("is:unread").Do()
	if err != nil {
		return fmt.Errorf("unable to retrieve messages: %v", err)
	}

	// Process only new messages
	newMessagesProcessed := 0
	for _, m := range r.Messages {
		// Skip if this message has already been processed
		if m.Id == lastProcessedEmailID {
			break
		}

		// Fetch full message details
		msg, err := ew.service.Users.Messages.Get(user, m.Id).Do()
		if err != nil {
			log.Printf("Error fetching message %s: %v", m.Id, err)
			continue
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

		// Process the message
		ew.processMessage(from, subject)

		// Update last processed email ID after successful processing
		if err := ew.saveLastProcessedEmailID(m.Id); err != nil {
			log.Printf("Warning: Could not save last processed email ID: %v", err)
		}

		newMessagesProcessed++
	}

	if newMessagesProcessed == 0 {
		log.Println("No new unread emails")
	} else {
		log.Printf("Processed %d new email(s)", newMessagesProcessed)
	}

	return nil
}

func (ew *EmailWatcher) processMessage(from, subject string) {
	log.Printf("New email from %s with subject: %s", from, subject)

	// Example processing logic
	switch {
	case strings.Contains(strings.ToLower(from), "github.com"):
		log.Println("GitHub notification detected")
		// Example: Send a notification or log GitHub-related emails
		// You could add logic to parse GitHub email contents, track issues, etc.

	case strings.Contains(strings.ToLower(subject), "invoice"):
		log.Println("Invoice email detected")
		// Example: Save invoice to a specific folder or trigger accounting workflow
		// You might want to download attachments or extract invoice details

	case strings.Contains(strings.ToLower(from), "urgent@company.com"):
		log.Println("Urgent company email received")
		// Example: Send an immediate notification via SMS or push notification
		ew.sendUrgentNotification(from, subject)

	default:
		log.Println("Regular email received")
	}
}

// Example helper function for sending urgent notifications
func (ew *EmailWatcher) sendUrgentNotification(from, subject string) {
	// Placeholder for sending urgent notifications
	// In a real-world scenario, you might:
	// - Send an SMS
	// - Push notification to a mobile app
	// - Send a Slack/Discord message
	log.Printf("URGENT: Email from %s with subject '%s' requires immediate attention!", from, subject)
}

func main() {
	// Create email watcher
	watcher, err := newEmailWatcher()
	if err != nil {
		log.Fatalf("Failed to create email watcher: %v", err)
	}

	// Authenticate
	if err := watcher.authenticate(); err != nil {
		log.Fatalf("Authentication error: %v", err)
	}

	// Start watching emails
	log.Println("Starting email watcher. Press Ctrl+C to stop.")
	if err := watcher.watchEmails(); err != nil {
		log.Fatalf("Error watching emails: %v", err)
	}
}
