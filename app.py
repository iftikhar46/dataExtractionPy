import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime
# NEW IMPORTS
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

# ... [Keep your set_page_config and CSS styles exactly as they are] ...

# ... [Keep your FOOTER_PATTERNS and HEADER_PATTERNS exactly as they are] ...

# ... [Keep is_footer_text, is_header_text, should_skip_line exactly as they are] ...

def get_text_from_page(page, pdf_bytes, page_num):
    """
    Try to extract text normally. If empty, perform OCR.
    """
    # 1. Try native extraction (fast, accurate for digital PDFs)
    text = page.extract_text()
    
    # 2. If text is found and looks substantial, return it
    if text and len(text.strip()) > 50:
        return text

    # 3. Fallback: OCR (Scanned PDF)
    try:
        # Convert specific page to image (page_num is 0-indexed, pdf2image uses 1-indexed)
        images = convert_from_bytes(
            pdf_bytes, 
            first_page=page_num+1, 
            last_page=page_num+1,
            dpi=300 # High DPI helps with accuracy
        )
        
        if images:
            # Use Tesseract to get text
            # layout preserver works better for tables usually
            ocr_text = pytesseract.image_to_string(images[0], config='--psm 6') 
            return ocr_text
    except Exception as e:
        print(f"OCR Failed for page {page_num}: {e}")
        return ""
    
    return ""

def extract_schedule_a1_from_pdf(pdf_file):
    """Extract Schedule A1 data from uploaded PDF (Digital or Scanned)"""
    all_contributions = []
    
    try:
        # Read file bytes once to usage in both pdfplumber and pdf2image
        pdf_bytes = pdf_file.getvalue()
        
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            
            # Create a progress bar since OCR is slow
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for page_num in range(total_pages):
                # Update progress
                status_text.text(f"Scanning page {page_num + 1} of {total_pages}...")
                progress_bar.progress((page_num + 1) / total_pages)
                
                page = pdf.pages[page_num]
                
                # Intelligent Extraction (Native or OCR)
                text = get_text_from_page(page, pdf_bytes, page_num)
                
                # Clean text to ensure regex works on OCR'd text
                # OCR often confuses | for I or 1, and inserts random newlines
                if not text:
                    continue

                # Check if this page is relevant
                if "MONETARY POLITICAL CONTRIBUTIONS" in text or "Schedule A1" in text:
                    
                    # Process lines similar to before
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        
                        # Regex modified slightly to be more lenient for OCR errors
                        # e.g., allow spaces in amount, maybe allow missing $
                        date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?([\d,]+\.\d{2})', line)
                        
                        if date_match:
                            date = date_match.group(1)
                            name_and_maybe_more = date_match.group(2)
                            amount = f"${date_match.group(3)}" # standardized format
                            
                            # Extract just the name
                            name = name_and_maybe_more
                            name = re.sub(r'\(ID#:.*?\)', '', name).strip()
                            
                            # Initialize variables
                            address = "No Data"
                            city = "No Data"
                            state = "No Data"
                            zipcode = "No Data"
                            occupation = "No Data"
                            employer = "No Data"
                            
                            # Look for address in next 3 lines
                            for j in range(1, 4):
                                if i + j < len(lines):
                                    test_line = lines[i + j]
                                    # Check for address pattern (City, ST ZIP)
                                    if ',' in test_line and re.search(r'[A-Z]{2}\s+\d', test_line):
                                        address = test_line
                                        
                                        # Parse address
                                        addr_parts = address.split(',')
                                        if len(addr_parts) >= 2:
                                            city = addr_parts[0].strip()
                                            state_zip = addr_parts[1].strip()
                                            sz_parts = state_zip.split()
                                            if len(sz_parts) >= 2:
                                                state = sz_parts[0]
                                                zipcode = sz_parts[1]
                                        break
                            
                            # Find occupation and employer
                            search_end = min(i + 15, len(lines))
                            
                            # Look for next contribution to know where to stop
                            next_contribution_idx = -1
                            for j in range(i + 1, min(i + 20, len(lines))):
                                if re.search(r'\d{2}/\d{2}/\d{4}\s+.*?\d+\.\d{2}', lines[j]):
                                    next_contribution_idx = j
                                    search_end = min(search_end, next_contribution_idx)
                                    break
                            
                            potential_data_lines = []
                            for j in range(i + 1, search_end):
                                test_line = lines[j]
                                
                                if should_skip_line(test_line):
                                    continue
                                if test_line == address:
                                    continue
                                if re.search(r'\d{2}/\d{2}/\d{4}', test_line) and re.search(r'\d+\.\d{2}', test_line):
                                    continue
                                if ',' in test_line and re.search(r'[A-Z]{2}\s+\d', test_line):
                                    continue
                                
                                potential_data_lines.append(test_line)
                            
                            # Logic to assign occupation/employer from found lines
                            if potential_data_lines:
                                if len(potential_data_lines) == 1:
                                    data_line = potential_data_lines[0]
                                    if ' ' in data_line:
                                        parts = data_line.split(maxsplit=1)
                                        if len(parts) == 2:
                                            occupation = parts[0]
                                            employer = parts[1]
                                    else:
                                        occupation = data_line
                                elif len(potential_data_lines) >= 2:
                                    occupation = potential_data_lines[0]
                                    employer = potential_data_lines[1]
                            
                            # Final cleanup
                            for pattern in HEADER_PATTERNS:
                                if occupation: occupation = occupation.replace(pattern, "").strip()
                                if employer: employer = employer.replace(pattern, "").strip()
                            
                            if occupation in ["()", "(", ")", "No Data"]: occupation = "No Data"
                            if employer in ["()", "(", ")", "No Data"]: employer = "No Data"
                            
                            all_contributions.append({
                                'Date': date,
                                'Contributor Name': name,
                                'Address': address,
                                'City': city,
                                'State': state,
                                'Zip': zipcode,
                                'Occupation': occupation,
                                'Employer': employer,
                                'Amount': amount,
                                'Page': page_num + 1
                            })
                            
                            # Skip ahead
                            skip_amount = 1 # Fallback
                            for j in range(i + 1, min(i + 10, len(lines))):
                                if re.search(r'\d{2}/\d{2}/\d{4}\s+.*?\d+\.\d{2}', lines[j]):
                                    skip_amount = j - i
                                    break
                            if skip_amount > 1:
                                i += skip_amount
                            else:
                                i += 1
                        else:
                            i += 1
            
            # Clear progress bar
            status_text.empty()
            progress_bar.empty()

        # Deduplication logic
        unique_contributions = []
        seen = set()
        for contrib in all_contributions:
            key = (contrib['Date'], contrib['Contributor Name'], contrib['Amount'])
            if key not in seen:
                seen.add(key)
                unique_contributions.append(contrib)
        
        return unique_contributions, None
        
    except Exception as e:
        return None, f"Error processing PDF: {str(e)}"

def main():
    # Header
    st.markdown('<h1 class="main-header">📄 Texas Ethics Commission PDF Extractor</h1>', unsafe_allow_html=True)
    
    # Description
    st.markdown("""
    <div class="info-box">
    <strong>ℹ️ About this tool:</strong> This application extracts Schedule A1 (Monetary Political Contributions) 
    data from Texas Ethics Commission PDF files and exports it to Excel format.
    </div>
    """, unsafe_allow_html=True)
    
    # File upload section
    st.markdown('<h3 class="sub-header">📤 Upload PDF File</h3>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf", label_visibility="collapsed")
    
    if uploaded_file is not None:
        # Show file info
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**File:** {uploaded_file.name}")
        with col2:
            st.info(f"**Size:** {uploaded_file.size / 1024:.2f} KB")
        
        # Process button
        if st.button("🚀 Extract Data", type="primary"):
            with st.spinner("Processing PDF... This may take a few seconds."):
                # Extract data
                contributions, error = extract_schedule_a1_from_pdf(uploaded_file)
                
                if error:
                    st.error(f"❌ {error}")
                elif not contributions:
                    st.warning("⚠️ No Schedule A1 data found in the uploaded PDF.")
                else:
                    # Create DataFrame
                    df = pd.DataFrame(contributions)
                    
                    # Sort by date and page
                    df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%Y', errors='coerce')
                    df = df.sort_values(['Date', 'Page'])
                    df = df.drop('Page', axis=1)
                    
                    # Display success message
                    st.markdown(f"""
                    <div class="success-box">
                    <strong>✅ Success!</strong> Extracted <strong>{len(df)} contributions</strong> from the PDF.
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display preview
                    st.markdown('<h3 class="sub-header">📋 Data Preview</h3>', unsafe_allow_html=True)
                    st.dataframe(df.head(10), use_container_width=True)
                    
                    # Calculate total
                    total = 0
                    for amt in df['Amount']:
                        clean_amt = str(amt).replace('$', '').replace(',', '')
                        try:
                            total += float(clean_amt)
                        except:
                            pass
                    
                    # Display stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Contributions", len(df))
                    with col2:
                        st.metric("Total Amount", f"${total:,.2f}")
                    with col3:
                        date_range = f"{df['Date'].min().strftime('%m/%d/%Y')} to {df['Date'].max().strftime('%m/%d/%Y')}"
                        st.metric("Date Range", date_range)
                    
                    # Prepare Excel file for download
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Schedule_A1')
                    
                    output.seek(0)
                    
                    # Download button
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"Schedule_A1_Data_{timestamp}.xlsx"
                    
                    st.download_button(
                        label="📥 Download Excel File",
                        data=output,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    # Also show CSV option
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download CSV File",
                        data=csv,
                        file_name=f"Schedule_A1_Data_{timestamp}.csv",
                        mime="text/csv"
                    )
    
    # Instructions sidebar
    with st.sidebar:
        st.markdown("## 📖 Instructions")
        st.markdown("""
        1. **Upload** a Texas Ethics Commission PDF file
        2. **Click** the 'Extract Data' button
        3. **Preview** the extracted data
        4. **Download** as Excel or CSV
        
        ---
        
        **📊 Extracted Fields:**
        - Date
        - Contributor Name
        - Address (with City, State, ZIP)
        - Occupation
        - Employer
        - Amount
        
        ---
        
        **✅ Supported Format:**
        Texas Ethics Commission Schedule A1
        (Monetary Political Contributions)
        
        ---
        
        **⚠️ Note:**
        Only extracts data from pages containing
        "MONETARY POLITICAL CONTRIBUTIONS"
        """)
        
        # Add a reset button
        if st.button("🔄 Clear & Upload New"):
            st.rerun()

if __name__ == "__main__":
    main()