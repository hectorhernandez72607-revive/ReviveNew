/**
 * Google Apps Script for Google Forms Integration
 * 
 * SETUP INSTRUCTIONS:
 * 1. Open your Google Form
 * 2. Click the three dots (⋮) in the top right → "Script editor"
 * 3. Paste this entire script
 * 4. Click the clock icon (Triggers) → Add trigger
 * 5. Configure:
 *    - Function: onFormSubmit
 *    - Event source: From form
 *    - Event type: On form submit
 * 6. Save and authorize the script
 * 7. Update the BACKEND_URL below with your backend URL
 * 
 * IMPORTANT: For local testing, use ngrok:
 *   1. Install ngrok: https://ngrok.com/
 *   2. Run: ngrok http 8000
 *   3. Copy the https URL (e.g., https://abc123.ngrok.io)
 *   4. Use that URL in BACKEND_URL below
 */

// ============================================
// CONFIGURATION - UPDATE FOR EACH CLIENT
// ============================================
// Each paying client has their own webhook URL. Use the same client slug
// you use in the dashboard: ?client=YOUR_CLIENT_SLUG
const BACKEND_BASE = "https://your-domain.com";  // e.g. https://abc123.ngrok-free.dev or https://api.yourapp.com
const CLIENT_SLUG = "demo";  // This client's slug (must match dashboard ?client=...)
const WEBHOOK_URL = BACKEND_BASE + "/webhook/lead/" + CLIENT_SLUG;

// ============================================
// MAIN FUNCTION - Runs when form is submitted
// ============================================
function onFormSubmit(e) {
  try {
    // Get the form response
    const formResponse = e.response;
    const itemResponses = formResponse.getItemResponses();
    
    // Initialize variables
    let name = "";
    let email = "";
    let phone = "";
    
    // Extract data from form responses
    // Adjust the field matching logic based on your form field names
    itemResponses.forEach(function(itemResponse) {
      const questionTitle = itemResponse.getItem().getTitle().toLowerCase();
      const answer = itemResponse.getResponse();
      
      // Match common field names
      if (questionTitle.includes("name") || 
          questionTitle.includes("full name") ||
          questionTitle.includes("first name") ||
          questionTitle.includes("last name")) {
        name = answer;
      }
      
      if (questionTitle.includes("email") || 
          questionTitle.includes("e-mail") ||
          questionTitle.includes("email address")) {
        email = answer;
      }
      
      if (questionTitle.includes("phone") || 
          questionTitle.includes("phone number") ||
          questionTitle.includes("telephone")) {
        phone = answer;
      }
    });
    
    // Validate required fields
    if (!name || !email) {
      Logger.log("ERROR: Missing required fields (name or email)");
      Logger.log("Form data: " + JSON.stringify({
        name: name,
        email: email,
        phone: phone
      }));
      return;
    }
    
    // Prepare payload for backend
    const payload = {
      name: name,
      email: email,
      phone: phone || "",
      source: "Google Forms"
    };
    
    // Send to backend
    const options = {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true  // Don't throw on HTTP errors
    };
    
    Logger.log("Sending lead to backend: " + JSON.stringify(payload));
    
    const response = UrlFetchApp.fetch(WEBHOOK_URL, options);
    const responseCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    if (responseCode === 200) {
      Logger.log("✅ Success! Lead sent: " + name + " (" + email + ")");
      Logger.log("Response: " + responseText);
    } else {
      Logger.log("❌ Error sending lead. Status: " + responseCode);
      Logger.log("Response: " + responseText);
      Logger.log("Check that your backend is running and accessible.");
    }
    
  } catch (error) {
    Logger.log("❌ Exception occurred: " + error.toString());
    Logger.log("Stack trace: " + error.stack);
  }
}

// ============================================
// TEST FUNCTION - Run this manually to test
// ============================================
function testWebhook() {
  // Create a mock event object for testing
  const mockEvent = {
    response: {
      getItemResponses: function() {
        return [
          {
            getItem: function() {
              return { getTitle: function() { return "Full Name"; } };
            },
            getResponse: function() { return "Test User"; }
          },
          {
            getItem: function() {
              return { getTitle: function() { return "Email Address"; } };
            },
            getResponse: function() { return "test@example.com"; }
          }
        ];
      }
    }
  };
  
  Logger.log("Running test...");
  onFormSubmit(mockEvent);
  Logger.log("Test complete. Check logs above.");
}
