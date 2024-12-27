import sys
from pathlib import Path
import logging
import re

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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
import os
from app.bot.docusign_integration import send_document_for_signing, check_envelope_status
from app.bot.config import TELEGRAM_TOKEN
from app.bot.excel_service import ExcelService
from app.bot.translation import TEXTS

# States for conversation
LANGUAGE, VIEW_PITCH, FULL_NAME, INVESTMENT_AMOUNT, EMAIL_WALLET, CONFIRM_SIGNING, TRANSACTION_HASH, WALLET_ADDRESS = range(8)

# Available languages
LANGUAGES = {
    'English 🇬🇧': 'en',
    'Русский 🇷🇺': 'ru',
    '中文 🇨🇳': 'zh',
    'Indonesia 🇮🇩': 'id',
    'Filipino 🇵🇭': 'fil',
    'Tiếng Việt 🇻🇳': 'vi'
}

def is_valid_email(email):
    """Validate email format and convert to lowercase"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.lower()) is not None

def is_valid_hash(hash_str):
    """Validate transaction hash format"""
    pattern = r'^0x[a-fA-F0-9]{64}$'
    return re.match(pattern, hash_str) is not None

def is_valid_wallet(wallet):
    """Validate wallet address format"""
    pattern = r'^0x[a-fA-F0-9]{40}$'
    return re.match(pattern, wallet) is not None

def is_valid_name(name):
    """Validate full name format (English letters only)"""
    # Check if name contains only English letters and spaces
    pattern = r'^[A-Za-z\s]+$'
    
    # Additional checks
    if not re.match(pattern, name):
        return False
    
    # Check if name has at least two parts (first and last name)
    parts = name.strip().split()
    if len(parts) < 2:
        return False
        
    # Check minimum length for each part
    if any(len(part) < 2 for part in parts):
        return False
    
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the conversation and ask for language."""
    keyboard = [
        [InlineKeyboardButton(lang, callback_data=code)] 
        for lang, code in LANGUAGES.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        TEXTS['welcome']['en'],  # Only English welcome message
        reply_markup=reply_markup
    )
    return LANGUAGE

async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection and send pitch deck link."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['language'] = query.data
    
    # Select pitch deck link based on language
    if query.data == 'ru':
        pitch_deck_link = "https://drive.google.com/file/d/1TTR_AcJ8Q_nPYf5zO1ZpqVVrDBx0RPn3/view?usp=sharing"
    else:
        # Default to English version for other languages
        pitch_deck_link = "https://drive.google.com/file/d/1sHlPIp8_baVQ2KhU5OUaepG7g0bElLvO/view?usp=sharing"
    
    keyboard = [[
        InlineKeyboardButton(
            TEXTS['reviewed_button'][query.data],
            callback_data="reviewed"
        )
    ]]
    
    await query.message.reply_text(
        TEXTS['pitch_deck'][query.data] + "\n\n" + pitch_deck_link,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return VIEW_PITCH

async def pitch_reviewed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pitch deck review confirmation and ask for full name."""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data['language']
    await query.message.reply_text(TEXTS['enter_name'][lang])
    return FULL_NAME

async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle full name and validate it."""
    name = update.message.text
    lang = context.user_data['language']
    
    if not is_valid_name(name):
        await update.message.reply_text(TEXTS['invalid_name'][lang])
        return FULL_NAME
    
    context.user_data['full_name'] = name
    
    await update.message.reply_text(TEXTS['enter_amount'][lang])
    return INVESTMENT_AMOUNT

async def investment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle investment amount and validate it."""
    amount = update.message.text
    lang = context.user_data['language']
    
    # Validate that amount contains only numbers
    if not amount.isdigit():
        await update.message.reply_text(TEXTS['invalid_amount'][lang])
        return INVESTMENT_AMOUNT
    
    # Convert to integer and validate minimum amount
    amount_int = int(amount)
    if amount_int < 10000:  # Changed to $10,000
        await update.message.reply_text(TEXTS['minimum_amount'][lang])
        return INVESTMENT_AMOUNT
    
    context.user_data['investment_amount'] = amount
    
    await update.message.reply_text(TEXTS['enter_email'][lang])
    return EMAIL_WALLET

async def email_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle email and send DocuSign envelope."""
    email = update.message.text.lower()  # Convert to lowercase
    lang = context.user_data['language']
    
    if not is_valid_email(email):
        await update.message.reply_text(TEXTS['invalid_email'][lang])
        return EMAIL_WALLET
    
    context.user_data['email'] = email  # Store lowercase email
    
    try:
        envelope_id = await send_document_for_signing(
            email,
            context.user_data['investment_amount'],
            lang
        )
        context.user_data['envelope_id'] = envelope_id
        
        keyboard = [[
            InlineKeyboardButton(
                TEXTS['document_signed_button'][lang],
                callback_data="signed"
            )
        ]]
        
        await update.message.reply_text(
            TEXTS['document_sent'][lang],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM_SIGNING
        
    except Exception as e:
        logger.error(f"Error sending document: {str(e)}")  # Add error logging
        await update.message.reply_text(TEXTS['document_error'][lang])
        return ConversationHandler.END

async def confirm_signing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle signing confirmation and ask for transaction hash."""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data['language']
    await query.message.reply_text(TEXTS['enter_hash'][lang])
    return TRANSACTION_HASH

async def transaction_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle transaction hash and ask for wallet address."""
    hash_value = update.message.text
    lang = context.user_data['language']
    
    # Add hash format example and validation
    if not is_valid_hash(hash_value):
        await update.message.reply_text(TEXTS['invalid_hash'][lang])
        return TRANSACTION_HASH
    
    context.user_data['transaction_hash'] = hash_value
    
    await update.message.reply_text(TEXTS['enter_wallet'][lang])
    return WALLET_ADDRESS

async def wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Final step - handle wallet address and record data."""
    wallet = update.message.text
    lang = context.user_data['language']
    
    if not is_valid_wallet(wallet):
        await update.message.reply_text(TEXTS['invalid_wallet'][lang])
        return WALLET_ADDRESS
    
    context.user_data['wallet_address'] = wallet
    
    try:
        user_data = {
            'telegram_id': update.effective_user.id,
            'full_name': context.user_data.get('full_name', ''),
            'investment_amount': context.user_data.get('investment_amount'),
            'email': context.user_data.get('email'),
            'envelope_id': context.user_data.get('envelope_id'),
            'transaction_hash': context.user_data.get('transaction_hash'),
            'wallet_address': wallet
        }
        
        excel_service = context.application.bot_data['excel_service']
        await excel_service.record_user_data(user_data)
        
        await update.message.reply_text(TEXTS['success'][lang])
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(TEXTS['record_error'][lang])
        return ConversationHandler.END

def main():
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Initialize Excel service
    excel_service = ExcelService()
    
    # Store excel_service in application's context
    application.bot_data['excel_service'] = excel_service
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_choice)],
            VIEW_PITCH: [CallbackQueryHandler(pitch_reviewed, pattern="^reviewed$")],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
            INVESTMENT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, investment_amount)],
            EMAIL_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_wallet)],
            CONFIRM_SIGNING: [CallbackQueryHandler(confirm_signing, pattern="^(signed|check_status)$")],
            TRANSACTION_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, transaction_hash)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_address)],
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main() 