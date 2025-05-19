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
from bs4 import BeautifulSoup
import json
import mysql.connector
from mysql.connector import Error
import pandas as pd

# Load environment variables
load_dotenv()

# Set Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Initialize session state
if 'total_tokens' not in st.session_state:
    st.session_state.total_tokens = 0
if 'table_data' not in st.session_state:
    st.session_state.table_data = None

def count_tokens(text):
    return len(text) // 4 + 1 if text else 0

# MySQL Database Configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Siyara@191988")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "geminidocument")

# Initialize MySQL connection
def init_db():
    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        if connection.is_connected():
            cursor = connection.cursor()
            # Create table with auto-incrementing ID
            create_table_query = """
            CREATE TABLE IF NOT EXISTS extracted_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255),
                number VARCHAR(50),
                professional_summary TEXT,
                project_name TEXT,
                skills TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_table_query)
            connection.commit()
            return connection, cursor
    except Error as e:
        st.error(f"❌ Database connection failed: {e}")
        return None, None

# Load Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.warning("GEMINI_API_KEY not found in .env")
    GEMINI_API_KEY = st.text_input("Enter your Gemini API key:", type="password")
    if not GEMINI_API_KEY:
        st.stop()
genai.configure(api_key=GEMINI_API_KEY)

# Configure Gemini model
model = genai.GenerativeModel(
    model_name="models/gemini-1.5-flash",
    generation_config={
        "temperature": 0.0,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 1024,
    }
)

# Read and extract content
def read_file(uploaded_file):
    filename = uploaded_file.name.lower()
    all_content = []
    try:
        if filename.endswith(".msg"):
            file_bytes = io.BytesIO(uploaded_file.read())
            msg = extract_msg.Message(file_bytes)
            subject = msg.subject or "[No Subject]"
            st.write(f"📧 Email Subject: {subject}")
            html_text, plain_text = "", ""

            if msg.htmlBody:
                soup = BeautifulSoup(msg.htmlBody, 'html.parser')
                html_text = soup.get_text(separator=' ', strip=True)
                all_content.append(html_text)
                st.write(f"📨 Email Body (HTML): {html_text[:300]}...")
            elif msg.body:
                plain_text = msg.body
                all_content.append(plain_text)
                st.write(f"📨 Email Body: {plain_text[:300]}...")

            if msg.attachments:
                st.write("📎 Attachments:")
                for att in msg.attachments:
                    fname = re.sub(r'[^\w\.\-]', '', att.longFilename or att.shortFilename or "Unnamed")
                    att_content = io.BytesIO(att.data)
                    st.write(f"- {fname}")
                    if fname.endswith(".pdf"):
                        reader = PdfReader(att_content)
                        content = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
                        if content.strip():
                            all_content.append(content)
                    elif fname.endswith(".docx"):
                        doc = docx.Document(att_content)
                        content = "\n".join(p.text for p in doc.paragraphs)
                        if content.strip():
                            all_content.append(content)
                    elif fname.endswith((".jpg", ".jpeg", ".png")):
                        image = Image.open(att_content)
                        image = ImageEnhance.Contrast(image).enhance(2.0)
                        content = pytesseract.image_to_string(image, lang='eng')
                        if content.strip():
                            all_content.append(content)
                    else:
                        st.warning(f"⚠ Unsupported attachment type: {fname}")
            return "\n".join(all_content)[:50000]
        elif filename.endswith(".txt"):
            return uploaded_file.read().decode("utf-8")[:50000]
        elif filename.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())[:50000]
        elif filename.endswith(".docx"):
            doc = docx.Document(uploaded_file)
            return "\n".join(p.text for p in doc.paragraphs)[:50000]
        elif filename.endswith((".jpg", ".jpeg", ".png")):
            image = Image.open(uploaded_file)
            image = ImageEnhance.Contrast(image).enhance(2.0)
            content = pytesseract.image_to_string(image, lang='eng')
            return content[:50000] if content.strip() else ""
        else:
            st.error(f"❌ Unsupported file type: {filename}")
            return ""
    except Exception as e:
        st.error(f"❌ Error processing file: {e}")
        return ""

# Gemini Extraction
def extract_data_with_gemini(content, retries=3, delay=10):
    if not content:
        return None, 0, 0
    prompt = f"""
The text below contains content from an email and documents. Extract structured data and return as a list of JSON objects with the following keys:
- name
- email
- number
- professional_summary
- project_name
- skills
Ensure all field values are strings (convert lists to comma-separated strings if needed).
Format:
[
    {{
        "name": "...",
        "email": "...",
        "number": "...",
        "professional_summary": "...",
        "project_name": "...",
        "skills": "..."
    }},
    ...
]
Text: {content}
"""
    input_tokens = count_tokens(prompt)
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            result = re.sub(r'^json\n?|```json|```', '', result, flags=re.MULTILINE).strip()
            output_tokens = count_tokens(result)
            st.session_state.total_tokens += input_tokens + output_tokens
            return result, input_tokens, output_tokens
        except ResourceExhausted:
            if attempt < retries - 1:
                st.warning("⏳ Rate limit hit. Retrying...")
                time.sleep(delay)
                delay *= 2
            else:
                st.error("❌ Gemini API quota exhausted.")
                return None, input_tokens, 0
        except Exception as e:
            st.error(f"❌ Gemini error: {e}")
            return None, input_tokens, 0

# Detect email intent
def detect_email_intent(content):
    prompt = (
        "Read the email content below and identify the main intent or purpose in one line.\n"
        "Examples: Invitation for interview, Rejection letter, Offer letter, Request for documents, Acknowledgement, General update\n\n"
        f"Email Content:\n\"\"\"\n{content}\n\"\"\"\n\nRespond with only the intent."
    )
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.warning(f"⚠ Intent detection failed: {e}")
        return "Unknown"

# Convert list values to strings
def convert_lists_to_strings(record):
    return {k: ", ".join(v) if isinstance(v, list) else str(v) for k, v in record.items()}

# Check for duplicate data
def is_duplicate(record, connection, cursor):
    try:
        # Convert lists to strings
        record = convert_lists_to_strings(record)
        query = """
        SELECT COUNT(*) FROM extracted_data 
        WHERE name = %s AND email = %s AND number = %s
        """
        values = (
            record.get("name", ""),
            record.get("email", ""),
            record.get("number", "")
        )
        cursor.execute(query, values)
        count = cursor.fetchone()[0]
        return count > 0
    except Exception as e:
        st.warning(f"⚠ Error checking duplicates: {e}")
        return False

# Store data in MySQL
def store_data_in_db(data, connection, cursor):
    try:
        parsed = json.loads(data)
        inserted = False
        for record in parsed:
            # Convert lists to strings
            record = convert_lists_to_strings(record)
            if is_duplicate(record, connection, cursor):
                st.info(f"ℹ Skipped storing duplicate record for {record.get('name', 'Unknown')}")
                continue
            insert_query = """
            INSERT INTO extracted_data (name, email, number, professional_summary, project_name, skills)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            values = (
                record.get("name", ""),
                record.get("email", ""),
                record.get("number", ""),
                record.get("professional_summary", ""),
                record.get("project_name", ""),
                record.get("skills", "")
            )
            cursor.execute(insert_query, values)
            inserted = True
        if inserted:
            connection.commit()
        return inserted
    except json.JSONDecodeError:
        st.error("❌ Failed to parse JSON. Data not stored.")
        return False
    except Exception as e:
        st.error(f"❌ Database storage error: {e}")
        return False

# Fetch IDs from database
def fetch_ids(connection, cursor):
    try:
        cursor.execute("SELECT id FROM extracted_data")
        return [str(row[0]) for row in cursor.fetchall()]
    except Exception as e:
        st.error(f"❌ Error fetching IDs: {e}")
        return []

# Fetch record by ID
def fetch_record_by_id(record_id, connection, cursor):
    try:
        query = """
        SELECT name, email, number, professional_summary, project_name, skills
        FROM extracted_data WHERE id = %s
        """
        cursor.execute(query, (record_id,))
        result = cursor.fetchone()
        if result:
            return {
                "Name": result[0] or "N/A",
                "Email": result[1] or "N/A",
                "Number": result[2] or "N/A",
                "Professional Summary": result[3] or "N/A",
                "Project Name": result[4] or "N/A",
                "Skills": result[5] or "N/A"
            }
        return None
    except Exception as e:
        st.error(f"❌ Error fetching record: {e}")
        return None

# UI Layout
st.title("📄 Gemini Document Extractor")
st.write("Upload files to extract and store details, or view stored records.")

# Initialize database
connection, cursor = init_db()
if not connection or not cursor:
    st.stop()

# Tabs for Upload and View
tab1, tab2 = st.tabs(["📤 Upload Documents", "📋 View Records"])

with tab1:
    uploaded_files = st.file_uploader(
        "Upload your documents:",
        type=["msg", "txt", "pdf", "docx", "jpg", "png", "jpeg"],
        accept_multiple_files=True
    )

    if uploaded_files:
        for i, file in enumerate(uploaded_files):
            if st.button(f"Process {file.name}", key=f"btn_{i}"):
                st.write(f"📂 Reading `{file.name}`...")
                file.seek(0)
                content = read_file(file)

                # Email Intent
                st.markdown("### 🤠 Email Intent")
                intent = detect_email_intent(content)
                st.write(f"🔍 Intent: **{intent}**")

                # Extract data
                st.markdown("### ✨ Extracting with Gemini")
                result, in_tokens, out_tokens = extract_data_with_gemini(content)
                if result:
                    try:
                        parsed = json.loads(result)
                        st.success("✅ Data extracted successfully!")
                        # Store in database
                        if store_data_in_db(result, connection, cursor):
                            st.success("✅ Data stored in database successfully!")
                        else:
                            st.info("ℹ No new data stored (possible duplicates).")
                        st.write(f"🔢 Tokens used: {in_tokens + out_tokens} (Prompt: {in_tokens}, Response: {out_tokens})")
                        st.write(f"🔁 Total session tokens: {st.session_state.total_tokens}")
                    except json.JSONDecodeError:
                        st.error("❌ Failed to parse extraction result. Data not stored.")
                else:
                    st.error("❌ Data extraction failed.")

with tab2:
    st.markdown("### 🔍 View Stored Records")
    ids = fetch_ids(connection, cursor)
    
    # Define table headers
    headers = ["Name", "Email", "Number", "Professional Summary", "Project Name", "Skills"]
    
    # Initialize table data if not set
    if st.session_state.table_data is None:
        st.session_state.table_data = pd.DataFrame([["N/A"] * len(headers)], columns=headers)
    
    # Create a placeholder for the table
    table_placeholder = st.empty()
    
    # Display the table in the placeholder
    table_placeholder.table(st.session_state.table_data)
    
    if ids:
        selected_id = st.selectbox("Select Record ID:", ["Select an ID"] + ids)
        if st.button("View Record"):
            if selected_id == "Select an ID":
                st.error("❌ Please select a valid record ID.")
                # Reset table to headers with N/A values
                st.session_state.table_data = pd.DataFrame([["N/A"] * len(headers)], columns=headers)
            else:
                record = fetch_record_by_id(selected_id, connection, cursor)
                if record:
                    # Update the same table with the new record values
                    st.session_state.table_data = pd.DataFrame([record], columns=headers)
                else:
                    st.error("❌ Record not found.")
                    # Reset table to headers with N/A values
                    st.session_state.table_data = pd.DataFrame([["N/A"] * len(headers)], columns=headers)
            
            # Update the table in the placeholder
            table_placeholder.table(st.session_state.table_data)
    else:
        st.info("ℹ No records found in the database.")

# Close database connection
if connection and connection.is_connected():
    cursor.close()
    connection.close()