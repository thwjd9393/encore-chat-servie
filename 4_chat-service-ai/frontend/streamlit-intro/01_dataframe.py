import numpy as np
#차트 그리기용
import pandas as pd
import streamlit as st 


st.header("st.dataframe() 예제")

# 1. 기본 DataFrame 표시
st.subheader("1. 기본 사용법")
df_simple = pd.DataFrame({
    "과일": ["사과", "바나나", "딸기", "포도"],
    "가격": [1500, 800, 2000, 3500],
    "수량": [10, 25, 15, 8],
})
st.dataframe(df_simple)
st.caption("컬럼 헤더를 클릭하여 정렬하거나, 오른쪽 위 아이콘으로 전체 화면/검색 가능")
