import streamlit as st
import time
import os
import docx
from PyPDF2 import PdfReader
from PIL import Image, ImageEnhance
import pytesseract
import io
import re
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import extract_msg
import json
from bs4 import BeautifulSoup  # For HTML parsing

# Load environment variables
load_dotenv()

# Tesseract OCR path (for Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Session token count
if 'total_tokens' not in st.session_state:
    st.session_state.total_tokens = 0

# Estimate token count
def count_tokens(text):
    if not text:
        return 0
    return len(text) // 4 + 1

# Get Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.warning("GEMINI_API_KEY not found in .env")
    GEMINI_API_KEY = st.text_input("Enter your Gemini API key:", type="password")
    if not GEMINI_API_KEY:
        st.error("Please provide a valid Gemini API key.")
        st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# Gemini model
model = genai.GenerativeModel(
    model_name="models/gemini-1.5-flash",
    generation_config={
        "temperature": 0.0,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 1024,
    }
)

# Read file content
def read_file(uploaded_file):
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith(".msg"):
            file_bytes = io.BytesIO(uploaded_file.read())
            msg = extract_msg.Message(file_bytes)
            
            # Try extracting plain text, HTML, and RTF bodies
            msg_message = msg.body
            msg_html = msg.htmlBody
            msg_rtf = msg.rtfBody
            
            # Initialize content list
            all_content = []
            
         
            # Process HTML body if available
            if msg_html and msg_html.strip():
                try:
                    # Strip HTML tags to get plain text
                    soup = BeautifulSoup(msg_html, 'html.parser')
                    html_text = soup.get_text(separator=' ', strip=True)
                    if html_text.strip():
                        all_content.append(html_text)
                        st.write(f"**Email Body (HTML)**: {html_text[:500]}...")
                    else:
                        st.write("**Email Body (HTML)**: [Empty after parsing]")
                except Exception as e:
                    st.warning(f"Error parsing HTML body: {e}")
            else:
                st.write("**Email Body (HTML)**: [Not available]")
            
         

            # Log attachments
            if msg.attachments:
                st.write("**Attachments Found**:")
                for att in msg.attachments:
                    att_filename = att.longFilename or att.shortFilename or "Unnamed"
                    # Sanitize filename to remove invalid characters
                    att_filename = re.sub(r'[^\w\.\-]', '', att_filename)
                    st.write(f"- {att_filename}")
            else:
                st.warning("No attachments found in the email.")
                return "" if not all_content else "\n".join(all_content)[:50000]

            # Process attachments
            supported_attachments = 0
            for att in msg.attachments:
                att_filename = (att.longFilename or att.shortFilename or "Unnamed").lower()
                att_content = io.BytesIO(att.data)

                # Clean filename
                cleaned_filename = re.sub(r'[^\w\.\-]', '', att_filename)
                st.write(f"**Processing Attachment**: {cleaned_filename}")

                if cleaned_filename.endswith(".pdf"):
                    try:
                        reader = PdfReader(att_content)
                        content = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
                        if content.strip():
                            all_content.append(content)
                            supported_attachments += 1
                            st.write(f"**PDF Content Preview**: {content[:100]}...")
                        else:
                            st.warning(f"No text extracted from PDF: {cleaned_filename}")
                    except Exception as e:
                        st.error(f"Error reading PDF attachment {cleaned_filename}: {e}")
                        continue

                elif cleaned_filename.endswith(".docx"):
                    try:
                        doc = docx.Document(att_content)
                        content = "\n".join(para.text for para in doc.paragraphs)
                        if content.strip():
                            all_content.append(content)
                            supported_attachments += 1
                            st.write(f"**PDF Content Preview**: {content[:100]}...")
                        else:
                            st.warning(f"No text extracted from DOCX: {cleaned_filename}")
                    except Exception as e:
                        st.error(f"Error reading DOCX attachment {cleaned_filename}: {e}")
                        continue

                elif cleaned_filename.endswith((".png", ".jpg", ".jpeg")):
                    try:
                        image = Image.open(att_content)
                        image = ImageEnhance.Contrast(image).enhance(2.0)
                        content = pytesseract.image_to_string(image, lang='eng')
                        if content.strip():
                            all_content.append(content)
                            supported_attachments += 1
                            st.write(f"**Image Content Preview**: {content[:100]}...")
                        else:
                            st.warning(f"No text detected in image: {cleaned_filename}")
                    except Exception as e:
                        st.error(f"Error reading image attachment {cleaned_filename}: {e}")
                        continue

                else:
                    st.warning(f"Unsupported attachment: {cleaned_filename}")

            if not supported_attachments and not all_content:
                st.warning("No supported attachments (.pdf, .docx, .jpg, etc.) or email content found.")
                return ""

            if supported_attachments > 0:
                st.write(f"**Processed {supported_attachments} supported attachment(s)**")
            return "\n".join(all_content)[:50000]

        elif filename.endswith(".txt"):
            content = uploaded_file.read().decode("utf-8")
            return content[:50000]

        elif filename.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            content = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
            return content[:50000]

        elif filename.endswith(".docx"):
            doc = docx.Document(uploaded_file)
            content = "\n".join(para.text for para in doc.paragraphs)
            return content[:50000]

        elif filename.endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(uploaded_file)
            image = ImageEnhance.Contrast(image).enhance(2.0)
            content = pytesseract.image_to_string(image, lang='eng')
            if not content.strip():
                st.warning(f"No text detected in image {filename}")
                return ""
            return content[:50000]

        else:
            st.error(f"Unsupported file type: {filename}")
            return ""

    except pytesseract.TesseractNotFoundError:
        st.error("Tesseract OCR not installed or path incorrect.")
        return ""

    except Exception as e:
        st.error(f"Error reading {filename}: {e}")
        return ""

# Extract with Gemini
def extract_data_with_gemini(content, retries=3, delay=10):
    if not content:
        return None, 0, 0

    prompt = f"""
    The text below contains content from an email and multiple documents (e.g., PDFs, DOCX files).
    Extract information from each document separately and return a list of JSON objects.
    For each document, extract:
    1. Name
    2. Mobile number
    3. Address
    4. Projects done
    5. Experience (if mentioned)

    Ensure each JSON object is in the format:
    {{
        "name": "...",
        "mobile_number": "...",
        "address": "...",
        "projects": "...",
        "experience": "..."
    }}

    If no information is found for a document, return empty strings for each field.
    If the text contains multiple documents, separate them based on context or content boundaries (e.g., different resumes or sections).
    If only one document is detected, return a single JSON object in a list.

    Text: \"\"\"{content}\"\"\"
    Output format: [{...}, {...}, ...]
    """

    input_tokens = count_tokens(prompt)

    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            output_text = response.text.strip()
            
            # Sanitize the response to remove code fences or unexpected characters
            output_text = re.sub(r'^```json\n|```$', '', output_text, flags=re.MULTILINE)
            output_text = output_text.strip()

            # Debug: Log the raw output for inspection
            st.write("**Raw Gemini Output**:")
            st.code(output_text, language="json")

            output_tokens = count_tokens(output_text)
            st.session_state.total_tokens += input_tokens + output_tokens
            return output_text, input_tokens, output_tokens

        except ResourceExhausted as e:
            if attempt < retries - 1:
                st.warning(f"Rate limit hit. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                st.error(f"Failed after {retries} attempts: {e}")
                return None, input_tokens, 0
        except Exception as e:
            st.error(f"Gemini API error: {e}")
            return None, input_tokens, 0

# UI
st.title("📄 File Data Extractor using Gemini AI")
st.write("Upload files (.msg, .txt, .pdf, .docx, or image) to extract structured details.")

uploaded_files = st.file_uploader("Upload files", type=["msg", "txt", "pdf", "docx", "png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files:
    st.write("### 🧾 Select a File to Process")
    processed_files = 0

    for i, file in enumerate(uploaded_files):
        if st.button(f"Process {file.name}", key=f"process_{i}"):
            st.write(f"🔄 Processing {file.name}...")
            content = read_file(file)
            if content:
                extracted, input_tokens, output_tokens = extract_data_with_gemini(content)
                if extracted:
                    st.subheader(f"Results for {file.name}")
                    try:
                        # Parse the sanitized JSON
                        results = json.loads(extracted)
                        if isinstance(results, list):
                            for j, result in enumerate(results, 1):
                                st.write(f"**Document {j}**")
                                st.code(json.dumps(result, indent=2), language="json")
                        else:
                            st.error("Expected a list of JSON objects, but got a single object or invalid format.")
                            st.code(extracted, language="json")
                    except json.JSONDecodeError as e:
                        st.error(f"Failed to parse JSON output: {e}")
                        st.write("**Raw Output for Debugging**:")
                        st.code(extracted, language="text")
                    st.write(f"**Token Usage**")
                    st.write(f"- Input Tokens: {input_tokens}")
                    st.write(f"- Output Tokens: {output_tokens}")
                    st.write(f"- Total: {input_tokens + output_tokens}")
                else:
                    st.error(f"No data extracted from {file.name}")
                processed_files += 1
                time.sleep(10)  # Avoid hitting rate limits
            else:
                st.error(f"No content extracted from {file.name}")

    if processed_files > 0:
        st.write("### 📊 Total Token Usage")
        st.write(f"Total tokens used: **{st.session_state.total_tokens}**")