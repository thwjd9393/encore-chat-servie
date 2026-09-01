import streamlit as st
import pandas as pd

st.title("위젯의 key 와 Session State")

# 1. key 를 주면 입력한 값이 st.session_state["nickname"] 에 자동으로 담긴다.
st.text_input("닉네임", key="nickname")

# 2. selectbox 는 보이는 글자와 실제 값을 다르게 둘 수 있다.
fruits = {"a": "사과", "b": "바나나", "c": "체리"}
st.selectbox(
    "과일",
    options=list(fruits),               # 실제 값은 a / b / c
    format_func=lambda key: fruits[key],  # 화면에 보이는 것은 사과 / 바나나 / 체리
    key="fruit",
)

st.divider()

# 3. 세션 상태에 무엇이 담겼는지 그대로 본다.
st.write("session_state 에 담긴 것")
st.write(dict(st.session_state))

st.title("Streamlit 기능 맛보기")
st.write("Streamlit의 다양한 기능을 사용해 간단한 인터랙티브 앱을 만들어 봅시다.")

st.divider()

st.header("1. 사용자 이름 입력")
user_name = st.text_input("이름을 입력해주세요:", placeholder="예: 홍길동")
if user_name:
    st.success(f"안녕하세요, {user_name}님! 만나서 반갑습니다.")
else:
    st.info("위 입력창에 이름을 입력해보세요.")

st.divider()

st.header("2. 좋아하는 숫자 선택")
favorite_number = st.slider("가장 좋아하는 숫자를 선택하세요:", min_value=0, max_value=100, value=42)
st.write(f"당신이 가장 좋아하는 숫자는 {favorite_number} 이군요.")

st.divider()

st.header("3. 간단한 데이터 시각화")
if favorite_number > 0:
    chart_data = pd.DataFrame({
        'x': range(favorite_number + 1),
        '제곱 값': [x**2 for x in range(favorite_number + 1)]
    })
    chart_data = chart_data.set_index('x')
    st.line_chart(chart_data)
else:
    st.caption("좋아하는 숫자를 1 이상으로 선택하면 차트가 표시됩니다.")

st.divider()

st.sidebar.header("사이드바 영역")
sidebar_checkbox = st.sidebar.checkbox("사이드바 옵션 활성화", value=True)
if sidebar_checkbox:
    st.sidebar.success("사이드바 옵션이 활성화되었습니다.")