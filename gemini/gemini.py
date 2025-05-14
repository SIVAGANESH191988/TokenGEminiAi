import streamlit as st
import time
from email import message_from_bytes
from email.policy import default
import google.generativeai as genai
import os
import docx  # pip install python-docx
from PyPDF2 import PdfReader  # pip install PyPDF2
from google.api_core.exceptions import ResourceExhausted
from PIL import Image, ImageEnhance  # pip install Pillow
import pytesseract  # pip install pytesseract
import io
from dotenv import load_dotenv  # pip install python-dotenv

# Load environment variables from .env file
load_dotenv()

# Set Tesseract path explicitly for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Initialize session state for token tracking
if 'total_tokens' not in st.session_state:
    st.session_state.total_tokens = 0

# ========== TOKEN COUNT FUNCTION ==========
def count_tokens(text):
    """Estimate token count based on character length (1 token ≈ 4 characters)."""
    if not text:
        return 0
    return len(text) // 4 + 1  # Add 1 to account for small texts

# ========== CONFIGURE GEMINI ==========
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Fallback: Prompt for API key if not found in environment
if not GEMINI_API_KEY:
    st.warning("GEMINI_API_KEY not found in environment variables.")
    GEMINI_API_KEY = st.text_input("Enter your Gemini API key:", type="password")
    if not GEMINI_API_KEY:
        st.error("Please provide a valid Gemini API key to continue.")
        st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# Use Gemini 1.5 Flash for higher free-tier rate limits
model = genai.GenerativeModel(
    model_name="models/gemini-1.5-flash",
    generation_config={
        "temperature": 0.0,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 1024,
    }
)

# ========== FILE READER FUNCTION ==========
def read_file(uploaded_file):
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith(".msg"):
            email_message = message_from_bytes(uploaded_file.read(), policy=default)
            content = email_message.get_body(preferencelist=("plain", "html")).get_content()
        elif filename.endswith(".txt"):
            content = uploaded_file.read().decode("utf-8")
        elif filename.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            content = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
        elif filename.endswith(".docx"):
            doc = docx.Document(uploaded_file)
            content = "\n".join(para.text for para in doc.paragraphs)
        elif filename.endswith((".png", ".jpg", ".jpeg")):
            # Process image files with OCR
            image = Image.open(uploaded_file)
            # Enhance image for better OCR
            image = ImageEnhance.Contrast(image).enhance(2.0)
            content = pytesseract.image_to_string(image, lang='eng')
            if not content.strip():
                st.warning(f"No text detected in image {filename}")
                return ""
        else:
            st.error(f"Unsupported file type: {filename}")
            return ""
        # Limit content to reduce token usage (e.g., first 10,000 characters)
        return content[:10000]
    except pytesseract.TesseractNotFoundError:
        st.error(f"Tesseract OCR is not installed or not found at {pytesseract.pytesseract.tesseract_cmd}. Please install Tesseract and verify the path.")
        return ""
    except Exception as e:
        st.error(f"Error reading file {filename}: {e}")
        return ""

# ========== GEMINI DATA EXTRACTOR ==========
def extract_data_with_gemini(content, retries=3, delay=10):
    if not content:
        return None, 0, 0
    prompt = f"""
    Extract the following information from the text below in JSON format:
    1. Name
    2. Mobile number
    3. Address
    4. Projects done
    5. Experience (if mentioned)

    Ensure the output is always in the format:
    {{
        "name": "...",
        "mobile_number": "...",
        "address": "...",
        "projects": "...",
        "experience": "..."
    }}

    If no information is found, return empty strings for each field.

    Text: \"\"\"{content}\"\"\"
    """
    # Estimate input tokens
    input_tokens = count_tokens(prompt)
    
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            output_text = response.text.strip()
            # Estimate output tokens
            output_tokens = count_tokens(output_text)
            # Update total token count
            st.session_state.total_tokens += input_tokens + output_tokens
            return output_text, input_tokens, output_tokens
        except ResourceExhausted as e:
            if attempt < retries - 1:
                st.warning(f"Rate limit hit, retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                st.error(f"Failed after {retries} attempts: {e}")
                return None, input_tokens, 0
        except Exception as e:
            st.error(f"Gemini API error: {e}")
            return None, input_tokens, 0

# ========== STREAMLIT UI ==========
st.title("📄 File Data Extractor using Gemini AI")
st.write("Upload files (email, text, PDF, Word, or images) to extract structured details: name, contact, address, projects, experience.")

uploaded_files = st.file_uploader("Upload files (any type)", accept_multiple_files=True)

if uploaded_files:
    st.write("### 🧾 Select a File to Process")
    processed_files = 0
    # Process one file at a time to avoid rate limits
    for i, file in enumerate(uploaded_files):
        if st.button(f"Process {file.name}", key=f"process_{i}"):
            st.write(f"🔄 Processing {file.name} (API call #{i+1})...")
            content = read_file(file)
            if content:
                extracted, input_tokens, output_tokens = extract_data_with_gemini(content)
                if extracted:
                    st.subheader(f"Results for {file.name}")
                    st.code(extracted, language="json")
                    # Display token counts for this extraction
                    st.write(f"**Token Usage for {file.name}**")
                    st.write(f"- Input Tokens: {input_tokens}")
                    st.write(f"- Output Tokens: {output_tokens}")
                    st.write(f"- Total Tokens for this file: {input_tokens + output_tokens}")
                else:
                    st.error(f"No data extracted from {file.name}")
                time.sleep(10)  # Increased delay to avoid per-minute limits
                processed_files += 1
            else:
                st.error(f"No content extracted from {file.name}")

    # Display total token count after processing
    if processed_files > 0:
        st.write("### 📊 Total Token Usage")
        st.write(f"Total tokens used across all extractions: **{st.session_state.total_tokens}**")