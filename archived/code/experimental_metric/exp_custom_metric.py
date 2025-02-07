import streamlit as st

st.write("# Custom Metric Example")

# Custom CSS for the metric component
st.markdown(
    """
    <style>
    .metric-container {
        background-color:#4d4d4d;
        padding: 15px;
        border-radius:15px;
        display:inline-block;
        width:200px;
        text-align:center;
        font-family:'Arial', sans-serif;
        display:flex;
        flex-direction:row;
        justify-content:center;
        align-items:center;
        gap:50px;
    }
    .metric-value {
        font-size:30px;
        font-weight:bold;
        color:white;
    }
    .metric-delta {
        font-size:18px;
        color:red;
    }
    .metric-sub {
        font-size:14px;
        color:gray;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

m1, m2, *_ = st.columns([0.25, 0.25, 0.25, 0.25], gap="medium")

# Example metric display
with m1:
    st.markdown(
        """
    <div class="metric-container">
        <div class="metric-value">169</div>
        <div>
        <div class="metric-delta">-3.4% <span style="color: gray;">&#x25BC;</span></div>
        <div class="metric-sub">Moy. 175*<br>Moy. 160**</div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

# Example metric display
with m2:
    st.markdown(
        """
    <div class="metric-container">
        <div class="metric-value">169</div>
        <div>
        <div class="metric-delta">-3.4% <span style="color: gray;">&#x25BC;</span></div>
        <div class="metric-sub">Moy. 175*<br>Moy. 160**</div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
