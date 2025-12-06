import streamlit as st

st.title("Test App")
st.write("If this works, then Streamlit is installed correctly!")

# check if pandas is installed
try:
    import pandas as pd
    st.write("Pandas is installed")
except ImportError:
    st.write("Pandas is not installed")