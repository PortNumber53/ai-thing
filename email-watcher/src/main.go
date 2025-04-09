package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"github.com/joho/godotenv"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
	"google.golang.org/api/gmail/v1"
	"google.golang.org/api/option"
	"os/signal"
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
		return fmt.Errorf("could not get user config directory: %w", err)
	}
	
	tokenDir := filepath.Join(configDir, "ai-thing", "tokens")
	if err := os.MkdirAll(tokenDir, 0700); err != nil {
		return fmt.Errorf("could not create token directory: %w", err)
	}

	lastProcessedFile := filepath.Join(tokenDir, "last_processed_time.json")
	
	data, err := os.ReadFile(lastProcessedFile)
	if os.IsNotExist(err) {
		// If file doesn't exist, set to 24 hours ago
		ew.lastProcessedTime = time.Now().Add(-ew.processWindow)
		return nil
	} else if err != nil {
		return fmt.Errorf("could not read last processed file: %w", err)
	}

	var lastTime time.Time
	if err := json.Unmarshal(data, &lastTime); err != nil {
		return fmt.Errorf("could not unmarshal last processed time: %w", err)
	}

	ew.lastProcessedTime = lastTime
	return nil
}

func (ew *EmailWatcher) saveLastProcessedTime(t time.Time) error {
	configDir, err := os.UserConfigDir()
	if err != nil {
		return fmt.Errorf("could not get user config directory: %w", err)
	}
	
	tokenDir := filepath.Join(configDir, "ai-thing", "tokens")
	if err := os.MkdirAll(tokenDir, 0700); err != nil {
		return fmt.Errorf("could not create token directory: %w", err)
	}

	lastProcessedFile := filepath.Join(tokenDir, "last_processed_time.json")
	
	data, err := json.Marshal(t)
	if err != nil {
		return fmt.Errorf("could not marshal time: %w", err)
	}

	if err := os.WriteFile(lastProcessedFile, data, 0600); err != nil {
		return fmt.Errorf("could not write last processed time file: %w", err)
	}

	return nil
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
					// Token is valid, save it and update service
					ew.srv = srv
					err = saveToken(token)
					if err != nil {
						log.Printf("Warning: Could not save token: %v", err)
					}
					return nil
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
	// Create a channel to handle interrupts
	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt, syscall.SIGTERM)

	// Create a ticker to periodically check for new emails
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for {
		// Check if Gmail service is initialized
		if ew.srv == nil {
			return fmt.Errorf("Gmail service is not initialized. Please authenticate first")
		}

		if err := ew.loadLastProcessedTime(); err != nil {
			log.Printf("Error loading last processed time: %v", err)
			return err
		}

		// List unread messages
		user := "me"
		query := fmt.Sprintf("is:unread after:%d", ew.lastProcessedTime.Unix())
		listCall := ew.srv.Users.Messages.List(user).Q(query)
		
		r, err := listCall.Do()
		if err != nil {
			return fmt.Errorf("unable to retrieve messages for user %s with query %q: %w", user, query, err)
		}

		processedCount := 0
		lastProcessedTime := ew.lastProcessedTime

		for _, m := range r.Messages {
			// Fetch the full message details
			msg, err := ew.srv.Users.Messages.Get(user, m.Id).Do()
			if err != nil {
				log.Printf("Error fetching message details: %v", err)
				continue
			}

			// Extract sender and subject
			from := ""
			subject := ""
			for _, header := range msg.Payload.Headers {
				if header.Name == "From" {
					from = header.Value
				}
				if header.Name == "Subject" {
					subject = header.Value
				}
			}

			// Process the message
			ew.processMessage(from, subject)
			processedCount++

			// Update last processed time
msgTime := time.UnixMilli(msg.InternalDate)
			if msgTime.After(lastProcessedTime) {
				lastProcessedTime = msgTime
			}

			// Mark message as read
			_, err = ew.srv.Users.Messages.Modify(user, m.Id, &gmail.ModifyMessageRequest{
				RemoveLabelIds: []string{"UNREAD"},
			}).Do()
			if err != nil {
log.Printf("Error marking message %s as read: %v", m.Id, err)
			}
		}

		// Save the latest processed time
		if err := ew.saveLastProcessedTime(lastProcessedTime); err != nil {
			log.Printf("Error saving last processed time: %v", err)
		}

		if processedCount > 0 {
			log.Printf("Processed %d new email(s)", processedCount)
		}

		// Wait for either the next ticker interval or an interrupt
		select {
		case <-ticker.C:
			// Continue to next iteration to check for emails
			continue
		case <-interrupt:
			log.Println("Interrupt received, stopping email watcher")
			return nil
		}
	}
}

func (ew *EmailWatcher) processMessage(from, subject string) {
	log.Printf("New email from %s with subject: %s", from, subject)
	// Add your custom processing logic here
}

func getTokenFilePath() (string, error) {
	// Preferred location: ~/.config/ai-thing/tokens/gmail_token.json
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("could not get home directory: %w", err)
	}
	tokenPath := filepath.Join(homeDir, ".config", "ai-thing", "tokens", "gmail_token.json")

	// Ensure the directory exists
	if err := os.MkdirAll(filepath.Dir(tokenPath), 0700); err != nil {
		return "", fmt.Errorf("could not create token directory: %w", err)
	}

	// Fallback: current working directory
	if _, err := os.Stat(tokenPath); os.IsNotExist(err) {
		currentDir, err := os.Getwd()
		if err != nil {
			return "", fmt.Errorf("could not get current working directory: %w", err)
		}
		localTokenPath := filepath.Join(currentDir, "gmail_token.json")

		// If a token exists in the local directory, use it and move it to the preferred location
		if _, err := os.Stat(localTokenPath); err == nil {
			log.Println("Found token in local directory. Migrating to preferred location.")
			if err := os.Rename(localTokenPath, tokenPath); err != nil {
				return "", fmt.Errorf("could not migrate token: %w", err)
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
