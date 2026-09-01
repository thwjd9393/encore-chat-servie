import streamlit as st

# =========================
# 카운터 1
# =========================

if "count1" not in st.session_state:
    st.session_state.count1 = 0

st.subheader("카운터 1 - 가로 배치")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("증가", key="increase1"):
        st.session_state.count1 += 1

with col2:
    if st.button("감소", key="decrease1"):
        st.session_state.count1 -= 1

with col3:
    if st.button("리셋", key="reset1"):
        st.session_state.count1 = 0

st.write(f"현재 카운트: {st.session_state.count1}")


# =========================
# 카운터 2
# =========================

if "count2" not in st.session_state:
    st.session_state.count2 = 0

st.subheader("카운터 2 - 세로 배치")

if st.button("증가", key="increase2"):
    st.session_state.count2 += 1

if st.button("감소", key="decrease2"):
    st.session_state.count2 -= 1

if st.button("리셋", key="reset2"):
    st.session_state.count2 = 0

st.write(f"현재 카운트: {st.session_state.count2}")