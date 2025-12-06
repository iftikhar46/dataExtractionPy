import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime
import numpy as np

# Set page config
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
    st.error("pdfplumber not available")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except:
    EASYOCR_AVAILABLE = False
    st.error("EasyOCR not available")

st.title("📄 Texas Ethics PDF Extractor")
st.markdown("Supports both text-based and scanned PDFs")

def pdf_to_images_with_pdfplumber(pdf_bytes):
    """Convert PDF to images using pdfplumber (no poppler needed)"""
    try:
        import pdfplumber
        from PIL import Image
        import io as io_module
        
        images = []
        with pdfplumber.open(io_module.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                # Convert page to image
                im = page.to_image(resolution=150)  # Lower resolution for speed
                # Convert to PIL Image
                pil_image = im.original
                images.append(pil_image)
        return images
    except Exception as e:
        st.error(f"PDF to image conversion failed: {str(e)}")
        return None

def extract_text_with_easyocr(pdf_bytes):
    """Extract text from scanned PDF using EasyOCR"""
    try:
        # Initialize EasyOCR reader
        if 'reader' not in st.session_state:
            st.session_state.reader = easyocr.Reader(['en'])
        
        reader = st.session_state.reader
        
        # Convert PDF to images using pdfplumber
        with st.spinner("Converting PDF pages to images..."):
            images = pdf_to_images_with_pdfplumber(pdf_bytes)
            
            if not images:
                return None
        
        all_text = ""
        total_pages = len(images)
        
        # Create progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, image in enumerate(images):
            status_text.text(f"Processing page {i+1} of {total_pages}...")
            
            # Perform OCR
            results = reader.readtext(np.array(image), detail=0)  # Convert PIL to numpy array
            page_text = " ".join(results)
            all_text += page_text + "\n\n"
            
            # Update progress
            progress_bar.progress((i + 1) / total_pages)
        
        status_text.text("OCR complete!")
        return all_text
    except Exception as e:
        st.error(f"EasyOCR Error: {str(e)}")
        return None

def extract_text_from_pdf(pdf_bytes):
    """Try multiple methods to extract text"""
    
    # Method 1: Try direct text extraction first
    if PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                
                if text and len(text.strip()) > 100:
                    return text, "pdfplumber"
        except Exception as e:
            st.warning(f"Direct text extraction failed: {str(e)}")
    
    # Method 2: Try OCR
    if EASYOCR_AVAILABLE:
        text = extract_text_with_easyocr(pdf_bytes)
        if text and len(text.strip()) > 100:
            return text, "easyocr"
    
    return None, None

def extract_contributions_from_text(text):
    """Extract Schedule A1 data from text"""
    contributions = []
    
    if not text:
        return contributions
    
    # Clean text - common OCR fixes
    text = text.replace('|', 'I').replace('[', '(').replace(']', ')').replace('‘', "'").replace('’', "'")
    
    # Look for patterns
    # Try to find date-amount pairs
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for date
        date_patterns = [
            r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',  # MM/DD/YYYY
            r'(\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})',    # YYYY/MM/DD
        ]
        
        date = None
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                date = match.group(1)
                # Standardize format
                date = date.replace('-', '/').replace('.', '/')
                
                # Convert YYYY/MM/DD to MM/DD/YYYY if needed
                if re.match(r'\d{4}/\d{1,2}/\d{1,2}', date):
                    parts = date.split('/')
                    date = f"{parts[1]}/{parts[2]}/{parts[0]}"
                break
        
        if date:
            # Look for amount in current or next lines
            amount = None
            search_lines = [line] + lines[i+1:i+3]
            
            for search_line in search_lines:
                amount_patterns = [
                    r'\$\s*([\d,]+\.\d{2})',
                    r'([\d,]+\.\d{2})\s*\$',
                    r'USD\s*([\d,]+\.\d{2})',
                    r'([\d,]+\.\d{2})\s*USD',
                ]
                
                for pattern in amount_patterns:
                    match = re.search(pattern, search_line, re.IGNORECASE)
                    if match:
                        amount = f"${match.group(1)}"
                        break
                if amount:
                    break
            
            if amount:
                # Extract name
                name = line.replace(date, '').replace(amount, '')
                name = re.sub(r'[^\w\s\.,&()-]', ' ', name).strip()
                name = re.sub(r'\s+', ' ', name)
                
                if not name or len(name) < 2:
                    # Try to get name from next line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if not re.search(r'\$\s*[\d,]+\.\d{2}', next_line) and not re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', next_line):
                            name = next_line[:100]
                
                # Look for address
                address = "Not found"
                for j in range(1, min(6, len(lines) - i)):
                    test_line = lines[i + j].strip()
                    if re.search(r',\s*[A-Z]{2}', test_line) or re.search(r'[A-Z]{2}\s+\d', test_line):
                        address = test_line
                        break
                
                contributions.append({
                    'Date': date,
                    'Contributor Name': name[:100] if name else "Unknown",
                    'Address': address,
                    'Amount': amount
                })
        
        i += 1
    
    return contributions

def main():
    # Check requirements
    if not PDFPLUMBER_AVAILABLE:
        st.error("❌ pdfplumber is required but not installed. Add it to requirements.txt")
        return
    
    if not EASYOCR_AVAILABLE:
        st.warning("⚠️ EasyOCR not available. Scanned PDFs won't work. Add 'easyocr' to requirements.txt")
    
    st.markdown("""
    <div style='background-color: #e8f4fd; padding: 15px; border-radius: 10px; margin: 10px 0; color:black;'>
    <h4>📋 How to use:</h4>
    <ol>
    <li>Upload a Texas Ethics Commission PDF</li>
    <li>Click "Extract Data"</li>
    <li>Wait for processing (scanned PDFs take longer)</li>
    <li>Preview and download results</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf", label_visibility="collapsed")
    
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
                    st.error("❌ Could not extract text from PDF.")
                    return
                
                # Show method
                if method == "easyocr":
                    st.success("📸 Using OCR (scanned PDF)")
                else:
                    st.success("💾 Using text extraction")
                
                # Extract data
                contributions = extract_contributions_from_text(text)
                
                if not contributions:
                    st.warning("⚠️ No contributions found. Showing extracted text for debugging:")
                    with st.expander("View extracted text"):
                        st.text(text[:3000])
                else:
                    # Create DataFrame
                    df = pd.DataFrame(contributions)
                    
                    # Try to parse dates
                    try:
                        df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y', errors='coerce')
                        df = df.sort_values('Date')
                    except:
                        pass
                    
                    df = df.drop_duplicates()
                    
                    # Display
                    st.success(f"✅ Found {len(df)} contributions")
                    
                    # Preview
                    st.subheader("📊 Data Preview")
                    st.dataframe(df.head(20), use_container_width=True)
                    
                    # Download
                    st.subheader("📥 Download")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False)
                        output.seek(0)
                        
                        st.download_button(
                            label="💾 Download Excel",
                            data=output,
                            file_name="extracted_data.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    
                    with col2:
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📄 Download CSV",
                            data=csv,
                            file_name="extracted_data.csv",
                            mime="text/csv",
                            use_container_width=True
                        )

if __name__ == "__main__":
    main()