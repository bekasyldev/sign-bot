import sys
from pathlib import Path
import logging
import os

# Get the project root directory
ROOT_DIR = Path(__file__).parent.parent.parent

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent.parent))

from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, SignHere, Tabs, Recipients
import base64
from app.jwt_config import DS_JWT
from app.jwt_helpers import create_api_client, get_jwt_token, get_private_key
from app.eSignature.examples.eg002_signing_via_email import Eg002SigningViaEmailController

async def send_document_for_signing(signer_email, investment_amount, language):
    """Send document for signing via DocuSign."""
    try:
        # Fix paths by making them relative to project root
        private_key_path = os.path.join(ROOT_DIR, DS_JWT["private_key_file"])
        
        # Check if required files exist
        if not os.path.exists(private_key_path):
            raise FileNotFoundError(f"Private key file not found at: {private_key_path}")
            
        # Update paths to correct location
        docx_path = os.path.join(ROOT_DIR, "app", "static", "demo_documents", DS_JWT["doc_docx"])
        pdf_path = os.path.join(ROOT_DIR, "app", "static", "demo_documents", DS_JWT["doc_pdf"])
        
        if not os.path.exists(docx_path):
            raise FileNotFoundError(f"DOCX file not found at: {docx_path}")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

        # Initialize API client
        api_client = ApiClient()
        api_client.set_base_path(DS_JWT["authorization_server"])
        api_client.set_oauth_host_name(DS_JWT["authorization_server"])

        # Get private key and encode properly
        try:
            private_key = get_private_key(private_key_path).encode("ascii").decode("utf-8")
        except Exception as e:
            raise Exception(f"Error reading private key: {str(e)}")

        try:
            # Get JWT token
            token_response = get_jwt_token(
                private_key,
                ["signature", "impersonation"],
                DS_JWT["authorization_server"],
                DS_JWT["ds_client_id"],
                DS_JWT["ds_impersonated_user_id"]
            )
            access_token = token_response.access_token
        except Exception as e:
            raise Exception(f"Error getting JWT token: {str(e)}")

        try:
            # Get user info and account ID
            user_info = api_client.get_user_info(access_token)
            account_id = user_info.get_accounts()[0].account_id
            base_path = user_info.get_accounts()[0].base_uri + "/restapi"
        except Exception as e:
            raise Exception(f"Error getting user info: {str(e)}")

        # Prepare arguments exactly as in jwt_console.py
        args = {
            "account_id": account_id,
            "base_path": base_path,
            "access_token": access_token,
            "envelope_args": {
                "signer_email": signer_email,
                "signer_name": signer_email,
                "status": "sent",
                "cc_email": None,
                "cc_name": None
            }
        }

        try:
            # Use the working example controller
            result = Eg002SigningViaEmailController.worker(
                args,
                DS_JWT["doc_docx"],
                DS_JWT["doc_pdf"]
            )
            return result["envelope_id"]
        except Exception as e:
            raise Exception(f"Error creating envelope: {str(e)}")
        
    except Exception as e:
        logger.error(f"DocuSign Error: {str(e)}", exc_info=True)
        raise

async def check_envelope_status(envelope_id):
    """Check if the envelope has been signed."""
    try:
        # Initialize DocuSign client
        api_client = ApiClient()
        api_client.set_base_path(DS_JWT["authorization_server"])
        
        # Get JWT token
        private_key = get_private_key(DS_JWT["private_key_file"])
        token_response = get_jwt_token(
            private_key,
            ["signature", "impersonation"],
            DS_JWT["authorization_server"],
            DS_JWT["ds_client_id"],
            DS_JWT["ds_impersonated_user_id"]
        )
        access_token = token_response.access_token
        
        # Get user info and account ID
        user_info = api_client.get_user_info(access_token)
        account_id = user_info.get_accounts()[0].account_id
        base_path = user_info.get_accounts()[0].base_uri + "/restapi"
        
        # Create new api client with the updated base path
        api_client = ApiClient()
        api_client.set_base_path(base_path)
        api_client.set_default_header("Authorization", f"Bearer {access_token}")
        
        # Get envelope status
        envelopes_api = EnvelopesApi(api_client)
        envelope = envelopes_api.get_envelope(account_id, envelope_id)
        
        # Return True if envelope is completed
        return envelope.status == "completed"
        
    except Exception as e:
        logger.error(f"Error checking envelope status: {str(e)}", exc_info=True)
        raise