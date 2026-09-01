import pandas as pd
import streamlit as st

st.title("API 로그 대시보드")

# 판다스 시간에 만든 파일을 읽는다.
df = pd.read_csv("clean_logs.csv")
print(df.head())

# TODO 1. 숫자 세 개를 나란히 보여준다.
#         힌트: col1, col2, col3 = st.columns(3)
#               col1.metric("전체 요청 수", f"{len(df):,}")
col1, col2, col3 = st.columns(3)
col1.metric("전체 요청 수", f"{len(df):,}")

col2.metric("전체 응답 시간", f"{df['duration_ms'].mean():.1f}ms")

col2.metric("에러율", f"{(df['status_code'] >= 400 ).mean() * 100:.1f}%")

st.divider()

# TODO 2. 엔드포인트별 호출 수를 막대그래프로 그린다.
#         힌트: st.bar_chart(df["endpoint"].value_counts())
st.subheader("엔드포인트별 호출 수")
print("endpoint 종류:", df["endpoint"].nunique())
print("endpoint 건수 계산:", df["endpoint"].value_counts())

st.bar_chart(df["endpoint"].value_counts())

# TODO 3. 날짜별 요청 수를 선그래프로 그린다.
#         힌트: 날짜 열을 먼저 만든 뒤 st.line_chart(...)
st.subheader("날짜별 요청 수")
df["시각"] = pd.to_datetime(df["ts"])

result = df["시각"].dt.date.value_counts().sort_index()

print(result)

st.line_chart(result)
# st.line_chart(...)


# 표로 한 번 더
st.subheader("엔드포인트별 평균 응답시간 (ms)")
st.dataframe(df.groupby("endpoint")["duration_ms"].mean().round(1))
