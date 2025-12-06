import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime
import tempfile
import os

# Set page config FIRST
st.set_page_config(
    page_title="Texas Ethics PDF Extractor",
    page_icon="📄",
    layout="wide"
)

# Try imports
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except:
    PDFPLUMBER_AVAILABLE = False
    st.warning("pdfplumber not available")

try:
    import easyocr
    from pdf2image import convert_from_bytes
    from PIL import Image
    EASYOCR_AVAILABLE = True
except:
    EASYOCR_AVAILABLE = False
    st.warning("EasyOCR not fully installed")

st.title("📄 Texas Ethics PDF Extractor")
st.markdown("Supports both text-based and scanned PDFs")

def extract_text_with_easyocr(pdf_bytes):
    """Extract text from scanned PDF using EasyOCR"""
    try:
        # Initialize EasyOCR reader (do this once)
        if 'reader' not in st.session_state:
            st.session_state.reader = easyocr.Reader(['en'])
        
        reader = st.session_state.reader
        
        # Convert PDF to images
        with st.spinner("Converting PDF to images..."):
            images = convert_from_bytes(pdf_bytes)
        
        all_text = ""
        progress_bar = st.progress(0)
        
        with st.spinner("Performing OCR on pages..."):
            for i, image in enumerate(images):
                # Perform OCR
                results = reader.readtext(image, detail=0)  # detail=0 returns only text
                page_text = " ".join(results)
                all_text += page_text + "\n\n"
                
                # Update progress
                progress_bar.progress((i + 1) / len(images))
        
        return all_text
    except Exception as e:
        st.error(f"EasyOCR Error: {str(e)}")
        return None

def extract_text_from_pdf(pdf_bytes):
    """Try multiple methods to extract text"""
    
    # Method 1: Try pdfplumber first (for text-based PDFs)
    text_from_pdfplumber = ""
    if PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_from_pdfplumber += page_text + "\n"
        except Exception as e:
            st.warning(f"pdfplumber failed: {str(e)}")
    
    # Check if we got meaningful text from pdfplumber
    if text_from_pdfplumber and len(text_from_pdfplumber.strip()) > 100:
        return text_from_pdfplumber, "pdfplumber"
    
    # Method 2: Try EasyOCR (for scanned PDFs)
    if EASYOCR_AVAILABLE:
        text_from_ocr = extract_text_with_easyocr(pdf_bytes)
        if text_from_ocr and len(text_from_ocr.strip()) > 100:
            return text_from_ocr, "easyocr"
    
    return None, None

def extract_contributions_from_text(text):
    """Extract Schedule A1 data from OCR/text"""
    contributions = []
    
    if not text:
        return contributions
    
    # Clean up text - replace common OCR errors
    text = text.replace('|', 'I').replace('l', 'I').replace('[', '(').replace(']', ')')
    
    # Look for contribution patterns
    # Pattern for: Date Name Amount
    # Example: "06/30/2021 John Doe $1,000.00"
    
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Look for date patterns (more flexible for OCR)
        date_pattern = r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})'
        date_match = re.search(date_pattern, line)
        
        if date_match:
            date = date_match.group(1)
            # Standardize date format
            date = date.replace('-', '/').replace('.', '/')
            
            # Look for amount in same line
            amount_patterns = [
                r'\$\s*([\d,]+\.\d{2})',
                r'USD\s*([\d,]+\.\d{2})',
                r'([\d,]+\.\d{2})\s*USD',
                r'([\d,]+\.\d{2})\s*dollars',
            ]
            
            amount = None
            for pattern in amount_patterns:
                amt_match = re.search(pattern, line, re.IGNORECASE)
                if amt_match:
                    amount = f"${amt_match.group(1)}"
                    break
            
            if amount:
                # Extract name (text between date and amount)
                # Remove date and amount from line to get name
                name_line = line.replace(date, '').replace(amount, '')
                # Clean up name
                name = re.sub(r'[^\w\s\.,&()-]', ' ', name_line).strip()
                name = re.sub(r'\s+', ' ', name)  # Remove extra spaces
                
                # Look for address in next few lines
                address = "Not found"
                for j in range(1, min(5, len(lines) - i)):
                    next_line = lines[i + j].strip()
                    # Check for address patterns
                    if re.search(r',\s*[A-Z]{2}', next_line) or re.search(r'[A-Z]{2}\s+\d', next_line):
                        address = next_line
                        break
                
                contributions.append({
                    'Date': date,
                    'Contributor Name': name[:100],
                    'Address': address,
                    'Amount': amount
                })
    
    return contributions

def main():
    # Instructions
    st.markdown("""
    <div style='background-color: #e8f4fd; padding: 15px; border-radius: 10px; margin: 10px 0;'>
    <h4>📋 How to use:</h4>
    <ol>
    <li>Upload a Texas Ethics Commission PDF (text-based or scanned)</li>
    <li>Click "Extract Data"</li>
    <li>Preview and download results</li>
    </ol>
    <p><em>Note: OCR processing for scanned PDFs may take 30-60 seconds per page.</em></p>
    </div>
    """, unsafe_allow_html=True)
    
    if not EASYOCR_AVAILABLE:
        st.error("""
        ⚠️ OCR engine not available. For scanned PDF support:
        1. Make sure requirements.txt includes: easyocr, pdf2image, Pillow
        2. Redeploy the app on Streamlit Cloud
        """)
    
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_file:
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**File:** {uploaded_file.name}")
        with col2:
            st.info(f"**Size:** {uploaded_file.size / 1024:.1f} KB")
        
        if st.button("🚀 Extract Data", type="primary", use_container_width=True):
            with st.spinner("Processing PDF..."):
                pdf_bytes = uploaded_file.read()
                
                # Extract text
                text, method = extract_text_from_pdf(pdf_bytes)
                
                if not text:
                    st.error("❌ Could not extract text. The file might be corrupt or very low quality.")
                    return
                
                # Show method used
                if method == "easyocr":
                    st.success("📸 Using OCR (scanned/Image PDF detected)")
                    st.info("OCR may have errors. Check the preview below.")
                else:
                    st.success("💾 Using text extraction (digital PDF detected)")
                
                # Show sample of extracted text
                with st.expander("🔍 View extracted text sample", expanded=False):
                    st.text_area("First 2000 characters:", text[:2000], height=200)
                
                # Extract contributions
                contributions = extract_contributions_from_text(text)
                
                if not contributions:
                    st.warning("⚠️ No contributions found. The PDF might not contain Schedule A1 data.")
                    
                    # Show debugging info
                    with st.expander("Debug info"):
                        # Count dates found
                        dates = re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', text)
                        st.write(f"Dates found: {len(dates)}")
                        if dates:
                            st.write(f"Sample dates: {dates[:5]}")
                        
                        # Count dollar amounts
                        amounts = re.findall(r'\$\s*[\d,]+\.\d{2}', text)
                        st.write(f"Dollar amounts found: {len(amounts)}")
                        if amounts:
                            st.write(f"Sample amounts: {amounts[:5]}")
                else:
                    # Create DataFrame
                    df = pd.DataFrame(contributions)
                    
                    # Clean up
                    df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y', errors='coerce')
                    df = df.sort_values('Date')
                    df = df.drop_duplicates()
                    
                    # Display results
                    st.success(f"✅ Found {len(df)} contributions")
                    
                    # Preview
                    st.subheader("📊 Data Preview")
                    st.dataframe(df.head(15), use_container_width=True)
                    
                    # Download section
                    st.subheader("📥 Download")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Excel download
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Contributions')
                        output.seek(0)
                        
                        st.download_button(
                            label="💾 Download Excel",
                            data=output,
                            file_name=f"{uploaded_file.name.split('.')[0]}_extracted.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    
                    with col2:
                        # CSV download
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📄 Download CSV",
                            data=csv,
                            file_name=f"{uploaded_file.name.split('.')[0]}_extracted.csv",
                            mime="text/csv",
                            use_container_width=True
                        )

if __name__ == "__main__":
    main()