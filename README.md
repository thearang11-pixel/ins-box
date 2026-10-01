# ins-box

텍스트 둘레에 상자를 그려주는 작은 파이썬 패키지예요. 한글처럼 폭이 넓은 문자도 줄이 맞게 그려요.

```python
from ins_box import box

print(box("안녕하세요\nhello"))
```

```
┌────────────┐
│ 안녕하세요 │
│ hello      │
└────────────┘
```

## 테스트 실행

```bash
pip install pytest
pytest
```

`main` 브랜치에 푸시하거나 PR을 열면 GitHub Actions에서 테스트가 자동으로 실행돼요.
