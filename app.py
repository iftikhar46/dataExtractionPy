import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime

# Set page configuration
st.set_page_config(
    page_title="Texas Ethics PDF Extractor",
    page_icon="📄",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #374151;
        margin-bottom: 1rem;
    }
    .success-box {
        background-color: #D1FAE5;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #10B981;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #DBEAFE;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #3B82F6;
        margin: 1rem 0;
        color: black;
    }
    .stButton>button {
        background-color: #3B82F6;
        color: white;
        font-weight: bold;
        border: none;
        padding: 0.5rem 2rem;
        border-radius: 0.5rem;
    }
    .stButton>button:hover {
        background-color: #2563EB;
    }
    </style>
""", unsafe_allow_html=True)

# Define footer patterns that should never be captured as data
FOOTER_PATTERNS = [
    "provided by Texas Ethics Commission",
    "www.ethics.state.tx.us",
    "Version V1.1",
    "Forms provided by",
    "Texas Ethics Commission"
]

# Define header patterns that should be skipped
HEADER_PATTERNS = [
    "Full name of contributor",
    "out-of-state PAC",
    "ID#:_________________________",
    "Amount of Contribution ($)",
    "Date",
    "Contributor address",
    "Principal occupation",
    "Job title",
    "See Instructions",
    "Employer",
    "SCHEDULE",
    "MONETARY POLITICAL CONTRIBUTIONS"
]

def is_footer_text(text):
    """Check if text contains footer patterns"""
    if not text:
        return False
    text_lower = text.lower()
    for pattern in FOOTER_PATTERNS:
        if pattern.lower() in text_lower:
            return True
    return False

def is_header_text(text):
    """Check if text contains header patterns"""
    if not text:
        return False
    for pattern in HEADER_PATTERNS:
        if pattern in text:
            return True
    return False

def should_skip_line(text):
    """Determine if a line should be skipped when looking for occupation/employer"""
    if not text or text.strip() == "":
        return True
    if is_footer_text(text):
        return True
    if is_header_text(text):
        return True
    if re.match(r'^\d+\.\d+$', text):  # Page numbers like "1.0"
        return True
    if re.match(r'^Sch:.*Rpt:', text):  # "Sch: 1/5 Rpt: 4/23"
        return True
    if re.match(r'^\d+ of \d+$', text):  # "3 of 23"
        return True
    return False

def extract_schedule_a1_from_pdf(pdf_file):
    """Extract Schedule A1 data from uploaded PDF"""
    all_contributions = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Find Schedule A1 pages
            schedule_a1_pages = []
            for page_num in range(len(pdf.pages)):
                page = pdf.pages[page_num]
                text = page.extract_text()
                if text and "MONETARY POLITICAL CONTRIBUTIONS" in text:
                    schedule_a1_pages.append(page_num)
            
            if not schedule_a1_pages:
                return None, "No Schedule A1 data found in the PDF"
            
            # Process each Schedule A1 page
            for page_num in schedule_a1_pages:
                page = pdf.pages[page_num]
                text = page.extract_text()
                
                # Split into lines and clean
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                # Process each contribution
                i = 0
                while i < len(lines):
                    line = lines[i]
                    
                    # Check if this line has the pattern: date, name, amount
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$([\d,]+\.\d{2})', line)
                    
                    if date_match:
                        date = date_match.group(1)
                        name_and_maybe_more = date_match.group(2)
                        amount = f"${date_match.group(3)}"
                        
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
                            if re.search(r'\d{2}/\d{2}/\d{4}\s+.*?\$[\d,]+\.\d{2}', lines[j]):
                                next_contribution_idx = j
                                search_end = min(search_end, next_contribution_idx)
                                break
                        
                        # Search for occupation/employer
                        potential_data_lines = []
                        for j in range(i + 1, search_end):
                            test_line = lines[j]
                            
                            if should_skip_line(test_line):
                                continue
                            if test_line == address:
                                continue
                            if re.search(r'\d{2}/\d{2}/\d{4}', test_line) and '$' in test_line:
                                continue
                            if ',' in test_line and re.search(r'[A-Z]{2}\s+\d', test_line):
                                continue
                            
                            potential_data_lines.append(test_line)
                        
                        # Process potential data lines
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
                            if occupation:
                                occupation = occupation.replace(pattern, "").strip()
                            if employer:
                                employer = employer.replace(pattern, "").strip()
                        
                        if occupation and occupation in ["()", "(", ")"]:
                            occupation = "No Data"
                        if employer and employer in ["()", "(", ")"]:
                            employer = "No Data"
                        
                        if not occupation or not occupation.strip():
                            occupation = "No Data"
                        if not employer or not employer.strip():
                            employer = "No Data"
                        
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
                        skip_amount = 5
                        for j in range(i + 1, min(i + 10, len(lines))):
                            if re.search(r'\d{2}/\d{2}/\d{4}\s+.*?\$[\d,]+\.\d{2}', lines[j]):
                                skip_amount = j - i
                                break
                        
                        i += skip_amount
                    else:
                        i += 1
        
        # Remove duplicates
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