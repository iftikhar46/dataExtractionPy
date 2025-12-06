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

# Try imports with error handling
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError as e:
    PDFPLUMBER_AVAILABLE = False
    st.error(f"pdfplumber import failed: {e}")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
    # Monkey patch to fix ANTIALIAS issue if needed
    try:
        from PIL import Image
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.Resampling.LANCZOS
    except:
        pass
except ImportError as e:
    EASYOCR_AVAILABLE = False
    st.error(f"EasyOCR import failed: {e}")

st.title("📄 Texas Ethics PDF Extractor")
st.markdown("Extract Schedule A1 data from Texas Ethics Commission PDFs")

def extract_text_from_scanned_pdf(pdf_bytes):
    """Extract text from scanned PDFs using a different approach"""
    try:
        # First try: Use pdfplumber to extract any text
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            if text and len(text.strip()) > 50:
                return text, "pdfplumber"
        
        # If no text found, try a simpler OCR approach
        # We'll use pytesseract which is more reliable for this
        try:
            import pytesseract
            from pdf2image import convert_from_bytes
            
            # Convert PDF to images
            images = convert_from_bytes(pdf_bytes, dpi=200)
            
            all_text = ""
            for i, image in enumerate(images):
                # Extract text using pytesseract
                page_text = pytesseract.image_to_string(image, lang='eng')
                all_text += page_text + "\n\n"
            
            if all_text.strip():
                return all_text, "pytesseract"
        except ImportError:
            st.warning("For better OCR, install: pip install pytesseract pdf2image")
        except Exception as e:
            st.warning(f"Tesseract OCR failed: {e}")
        
        return None, None
        
    except Exception as e:
        st.error(f"PDF processing error: {str(e)}")
        return None, None

def extract_text_from_pdf_simple(pdf_bytes):
    """Simple text extraction without complex OCR"""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text if text.strip() else None
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return None

def extract_contributions(text):
    """Extract contribution data from text"""
    if not text:
        return []
    
    contributions = []
    
    # Clean the text
    text = re.sub(r'\s+', ' ', text)  # Replace multiple spaces/newlines
    
    # Pattern 1: Date Name Amount pattern
    # Look for: "06/30/2021 John Doe $1,000.00"
    pattern1 = r'(\d{2}/\d{2}/\d{4})\s+([^$]+?)\s+\$([\d,]+\.\d{2})'
    matches1 = re.findall(pattern1, text)
    
    for date, name, amount in matches1:
        # Clean name
        name = re.sub(r'[^\w\s\.,&()-]', ' ', name).strip()
        name = re.sub(r'\s+', ' ', name)
        
        # Look for address after the amount
        address = "Not found"
        # Simple search for city/state pattern after the match
        address_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5})', text[text.find(amount)+len(amount):text.find(amount)+len(amount)+200])
        if address_match:
            address = address_match.group(1)
        
        contributions.append({
            'Date': date,
            'Contributor Name': name[:100],
            'Address': address,
            'Amount': f"${amount}"
        })
    
    # Pattern 2: More flexible pattern for OCR text
    if not contributions:
        # Look for date and amount separately
        dates = re.findall(r'(\d{2}/\d{2}/\d{4})', text)
        amounts = re.findall(r'\$([\d,]+\.\d{2})', text)
        
        # Pair them up if we found both
        for i in range(min(len(dates), len(amounts))):
            # Try to find name between date and amount
            date = dates[i]
            amount = f"${amounts[i]}"
            
            # Find text between date and amount
            date_pos = text.find(date)
            amount_pos = text.find(amount)
            
            if date_pos < amount_pos:
                name_text = text[date_pos + len(date):amount_pos].strip()
                name = re.sub(r'[^\w\s\.,&()-]', ' ', name_text).strip()
                name = re.sub(r'\s+', ' ', name)
                
                if name and len(name) > 2:
                    contributions.append({
                        'Date': date,
                        'Contributor Name': name[:100],
                        'Address': "Not found",
                        'Amount': amount
                    })
    
    return contributions

def main():
    # Check for PDF processing capability
    if not PDFPLUMBER_AVAILABLE:
        st.error("""
        ❌ Required package not installed!
        
        Please make sure `pdfplumber` is in your requirements.txt:
        ```
        pdfplumber==0.10.3
        ```
        """)
        return
    
    st.markdown("""
    <div style='background-color: #e8f4fd; padding: 15px; border-radius: 10px; margin: 10px 0;'>
    <h4>📋 Supported PDF Types:</h4>
    <ul>
    <li><strong>Digital PDFs</strong> (text-based) - Best results</li>
    <li><strong>Scanned PDFs</strong> - May require manual cleanup</li>
    </ul>
    <p><em>For scanned PDFs, ensure text is clear and readable.</em></p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Upload Texas Ethics Commission PDF", type="pdf")
    
    if uploaded_file:
        # File info
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**File:** {uploaded_file.name}")
        with col2:
            st.info(f"**Size:** {uploaded_file.size / 1024:.1f} KB")
        
        if st.button("🔍 Extract Data", type="primary", use_container_width=True):
            with st.spinner("Processing PDF..."):
                pdf_bytes = uploaded_file.read()
                
                # Try simple extraction first
                text = extract_text_from_pdf_simple(pdf_bytes)
                
                if not text:
                    st.warning("⚠️ Could not extract text. The file might be scanned or encrypted.")
                    
                    # Offer alternative
                    if st.checkbox("Try advanced OCR (experimental)"):
                        with st.spinner("Trying OCR..."):
                            ocr_text, method = extract_text_from_scanned_pdf(pdf_bytes)
                            if ocr_text:
                                text = ocr_text
                                st.info(f"Used {method} for text extraction")
                            else:
                                st.error("OCR failed. Please upload a text-based PDF.")
                                return
                    else:
                        return
                
                # Show extracted text sample
                with st.expander("🔍 View extracted text sample"):
                    st.text_area("", text[:2000], height=200)
                
                # Extract contributions
                contributions = extract_contributions(text)
                
                if not contributions:
                    st.warning("""
                    ⚠️ No Schedule A1 data found.
                    
                    **Possible reasons:**
                    1. PDF doesn't contain Schedule A1
                    2. Text extraction failed
                    3. File is scanned with poor quality
                    
                    **Try:**
                    - Uploading a different file
                    - Using a text-based (not scanned) PDF
                    - Checking the text sample above
                    """)
                else:
                    # Create DataFrame
                    df = pd.DataFrame(contributions)
                    
                    # Clean and sort
                    try:
                        df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y', errors='coerce')
                        df = df.sort_values('Date')
                    except:
                        pass
                    
                    df = df.drop_duplicates()
                    
                    # Display results
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
                            df.to_excel(writer, index=False, sheet_name='Contributions')
                        output.seek(0)
                        
                        st.download_button(
                            label="💾 Download Excel",
                            data=output,
                            file_name="contributions.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    
                    with col2:
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📄 Download CSV",
                            data=csv,
                            file_name="contributions.csv",
                            mime="text/csv",
                            use_container_width=True
                        )

if __name__ == "__main__":
    main()