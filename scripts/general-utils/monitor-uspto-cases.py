#!/usr/bin/env python3
"""
USPTO Trademark Status Monitor
Monitors specified trademark applications and sends email notifications on changes
"""

import requests
import json
import smtplib
import hashlib
import time
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional

class USPTOTrademarkMonitor:
    def __init__(self, api_key: str, email_config: Dict):
        """
        Initialize the trademark monitor
        
        Args:
            api_key: Your USPTO API key
            email_config: Dictionary with email configuration
                {
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': 587,
                    'sender_email': 'your-email@gmail.com',
                    'sender_password': 'your-app-password',
                    'recipient_email': 'notify@example.com'
                }
        """
        self.api_key = api_key
        self.email_config = email_config
        self.base_url = "https://tsdrapi.uspto.gov/ts/cd/casestatus"
        self.state_file = "trademark_states.json"
        
    def get_trademark_status(self, serial_number: str) -> Optional[Dict]:
        """
        Fetch current status of a trademark application
        
        Args:
            serial_number: The trademark serial number (without 'sn' prefix)
            
        Returns:
            Dictionary with trademark status data or None if error
        """
        # Construct the API URL
        url = f"{self.base_url}/sn{serial_number}/info.json"
        
        # Add API key to headers
        headers = {
            'X-API-Key': self.api_key,
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print(f"Rate limit exceeded for {serial_number}")
                return None
            else:
                print(f"Error fetching {serial_number}: Status {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Request error for {serial_number}: {e}")
            return None
    
    def extract_key_info(self, data: Dict) -> Dict:
        """
        Extract key information from the trademark data
        
        Args:
            data: Raw trademark data from API
            
        Returns:
            Dictionary with key information
        """
        # Navigate the JSON structure to extract relevant fields
        # Note: The actual JSON structure may vary, adjust paths accordingly
        try:
            # This is a simplified extraction - adjust based on actual API response
            info = {
                'serial_number': data.get('serialNumber', ''),
                'status': data.get('status', {}).get('statusText', ''),
                'status_date': data.get('status', {}).get('statusDate', ''),
                'mark_text': data.get('markText', ''),
                'filing_date': data.get('filingDate', ''),
                'registration_number': data.get('registrationNumber', ''),
                'registration_date': data.get('registrationDate', ''),
                'owner': data.get('owner', {}).get('name', ''),
                'last_update': datetime.now().isoformat()
            }
            return info
        except Exception as e:
            print(f"Error extracting info: {e}")
            return {}
    
    def load_previous_states(self) -> Dict:
        """Load previously saved trademark states"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state file: {e}")
                return {}
        return {}
    
    def save_states(self, states: Dict):
        """Save current trademark states"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(states, f, indent=2)
        except Exception as e:
            print(f"Error saving state file: {e}")
    
    def create_state_hash(self, info: Dict) -> str:
        """Create a hash of the trademark state for change detection"""
        # Create hash from status and key dates
        state_str = f"{info.get('status')}_{info.get('status_date')}_{info.get('registration_number')}"
        return hashlib.md5(state_str.encode()).hexdigest()
    
    def send_email_notification(self, subject: str, body: str):
        """Send email notification about trademark changes"""
        msg = MIMEMultipart()
        msg['From'] = self.email_config['sender_email']
        msg['To'] = self.email_config['recipient_email']
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html'))
        
        try:
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(
                    self.email_config['sender_email'],
                    self.email_config['sender_password']
                )
                server.send_message(msg)
                print(f"Email sent: {subject}")
        except Exception as e:
            print(f"Error sending email: {e}")
    
    def format_change_email(self, serial_number: str, old_info: Dict, new_info: Dict) -> tuple:
        """Format email for trademark status change"""
        subject = f"USPTO Trademark Update: {serial_number}"
        
        body = f"""
        <html>
        <body>
            <h2>Trademark Status Update</h2>
            <p>A change has been detected for trademark application <strong>{serial_number}</strong></p>
            
            <h3>Current Information:</h3>
            <ul>
                <li><strong>Mark:</strong> {new_info.get('mark_text', 'N/A')}</li>
                <li><strong>Status:</strong> {new_info.get('status', 'N/A')}</li>
                <li><strong>Status Date:</strong> {new_info.get('status_date', 'N/A')}</li>
                <li><strong>Filing Date:</strong> {new_info.get('filing_date', 'N/A')}</li>
                <li><strong>Registration Number:</strong> {new_info.get('registration_number', 'N/A')}</li>
                <li><strong>Registration Date:</strong> {new_info.get('registration_date', 'N/A')}</li>
                <li><strong>Owner:</strong> {new_info.get('owner', 'N/A')}</li>
            </ul>
            
            <h3>Previous Status:</h3>
            <p>{old_info.get('status', 'N/A')} (as of {old_info.get('status_date', 'N/A')})</p>
            
            <p><a href="https://tsdr.uspto.gov/#caseNumber={serial_number}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch">
            View on USPTO TSDR</a></p>
            
            <hr>
            <p><small>Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
        </body>
        </html>
        """
        
        return subject, body
    
    def monitor_trademarks(self, serial_numbers: List[str]):
        """
        Monitor a list of trademark serial numbers for changes
        
        Args:
            serial_numbers: List of trademark serial numbers to monitor
        """
        print(f"Starting trademark monitoring at {datetime.now()}")
        
        # Load previous states
        previous_states = self.load_previous_states()
        current_states = {}
        
        for serial_number in serial_numbers:
            print(f"Checking {serial_number}...")
            
            # Get current status
            data = self.get_trademark_status(serial_number)
            
            if data:
                # Extract key information
                info = self.extract_key_info(data)
                
                if info:
                    # Create state hash for comparison
                    current_hash = self.create_state_hash(info)
                    current_states[serial_number] = {
                        'hash': current_hash,
                        'info': info
                    }
                    
                    # Check for changes
                    if serial_number in previous_states:
                        if previous_states[serial_number]['hash'] != current_hash:
                            print(f"Change detected for {serial_number}!")
                            
                            # Send notification
                            subject, body = self.format_change_email(
                                serial_number,
                                previous_states[serial_number]['info'],
                                info
                            )
                            self.send_email_notification(subject, body)
                    else:
                        # First time monitoring this trademark
                        print(f"First check for {serial_number} - baseline established")
                        
                        # Optional: Send initial notification
                        subject = f"USPTO Trademark Monitoring Started: {serial_number}"
                        body = f"""
                        <html>
                        <body>
                            <h2>Monitoring Started</h2>
                            <p>Now monitoring trademark <strong>{serial_number}</strong></p>
                            <p>Current Status: {info.get('status', 'N/A')}</p>
                            <p>You will receive notifications when changes are detected.</p>
                        </body>
                        </html>
                        """
                        self.send_email_notification(subject, body)
            
            # Rate limiting - wait between requests
            time.sleep(1)
        
        # Save current states for next comparison
        self.save_states(current_states)
        print(f"Monitoring complete at {datetime.now()}")

def main():
    """Main function to run the trademark monitor"""
    
    # Configuration
    API_KEY = os.environ.get('USPTO_API_KEY', 'your-api-key-here')
    
    # Email configuration (example for Gmail)
    EMAIL_CONFIG = {
        'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
        'sender_email': os.environ.get('SENDER_EMAIL', 'your-email@gmail.com'),
        'sender_password': os.environ.get('SENDER_PASSWORD', 'your-app-password'),
        'recipient_email': os.environ.get('RECIPIENT_EMAIL', 'notify@example.com')
    }
    
    # Trademarks to monitor (extract from your URLs)
    TRADEMARKS = [
        '98325678',  # From your first URL
        '98229934'   # From your second URL
    ]
    
    # Create monitor instance
    monitor = USPTOTrademarkMonitor(API_KEY, EMAIL_CONFIG)
    
    # Run monitoring
    monitor.monitor_trademarks(TRADEMARKS)

if __name__ == "__main__":
    main()