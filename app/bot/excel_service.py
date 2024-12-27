import gspread
from google.oauth2.service_account import Credentials
import logging
from datetime import datetime
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class ExcelService:
    def __init__(self):
        # Define the scope
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/drive'
        ]

        try:
            # Get the path to the key file (using key_shet.json)
            key_path = Path(__file__).parent.parent.parent / 'key_shet.json'
            
            if not os.path.exists(key_path):
                raise FileNotFoundError(f"Google Sheets key file not found at: {key_path}")
                
            logger.debug(f"Loading credentials from: {key_path}")
            
            # Load credentials from service account file
            creds = Credentials.from_service_account_file(
                str(key_path),
                scopes=scope
            )
            
            # Authorize the client
            self.client = gspread.authorize(creds)
            
            # Get the spreadsheet
            self.spreadsheet = self.client.open_by_url(
                "https://docs.google.com/spreadsheets/d/1VsPPVPRl-ZsyzHLmQEYtFmn7NpPXqwxrUgjzTJcCYdQ/edit#gid=0"
            )
            
            # Get the first worksheet
            self.worksheet = self.spreadsheet.get_worksheet(0)
            logger.info("Successfully initialized Google Sheets connection")
            
        except Exception as e:
            logger.error(f"Error initializing Excel service: {str(e)}", exc_info=True)
            raise

    async def record_user_data(self, user_data):
        """
        Record user data to Google Sheets
        
        Args:
            user_data (dict): Dictionary containing user information
        """
        try:
            # First, set up the headers if they don't exist
            headers = [
                "Date",                  # Timestamp
                "Telegram ID",           # User's Telegram ID
                "Full Name",            # User's full name in English
                "Investment Amount $",   # Investment Amount in USD
                "Email",                # Email address
                "DocuSign Envelope ID", # DocuSign tracking
                "DocuSign View Link",   # Link to view the document
                "Transaction Hash",     # Blockchain transaction
                "Wallet Address"        # EVM wallet address
            ]
            
            # Check if headers exist and add them if they don't
            if self.worksheet.row_values(1) != headers:
                self.worksheet.insert_row(headers, 1)
            
            # Prepare row data
            docusign_view_link = f"https://apps-d.docusign.com/send/documents/details/{user_data.get('envelope_id', '')}"
            
            row_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Date
                user_data.get('telegram_id', ''),              # Telegram ID
                user_data.get('full_name', ''),               # Full Name
                user_data.get('investment_amount', ''),        # Investment Amount
                user_data.get('email', ''),                    # Email
                user_data.get('envelope_id', ''),              # DocuSign Envelope ID
                docusign_view_link,                            # DocuSign View Link
                user_data.get('transaction_hash', ''),         # Transaction Hash
                user_data.get('wallet_address', '')            # Wallet Address
            ]
            
            # Append the row
            self.worksheet.append_row(row_data)
            logger.info(f"Recorded data for user {user_data.get('telegram_id')}")
            
        except Exception as e:
            logger.error(f"Error recording user data: {str(e)}", exc_info=True)
            raise 