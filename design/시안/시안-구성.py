"""분리된 여섯 시안을 대화용 미리보기 하나로 조합한다."""
from pathlib import Path
import argparse
import base64
from PIL import Image

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=HERE / "냉장고한끼-미리보기.html",
                    help="완성한 미리보기를 저장할 경로")
args = parser.parse_args()
ORIGINAL = HERE / "음식사진-원본.png"
WEB_IMAGE = HERE / "음식사진-미리보기.jpg"
if not ORIGINAL.exists():
    raise FileNotFoundError(f"시안에 필요한 원본 이미지가 없습니다: {ORIGINAL}")
# 웹 표시용 인코딩만 변경한다. 원본의 구성과 픽셀 크기는 그대로 둔다.
if not WEB_IMAGE.exists():
    with Image.open(ORIGINAL) as image:
        image.convert("RGB").save(WEB_IMAGE, quality=82, optimize=True)
encoded = base64.b64encode(WEB_IMAGE.read_bytes()).decode("ascii")
parts = [
    "시안-공통.html",
    "시안-01-싱그러운주방.html",
    "시안-02-따뜻한식탁.html",
    "시안-03-매거진.html",
    "시안-04-알뜰냉장고.html",
    "시안-05-나이트키친.html",
    "시안-06-즐거운한끼.html",
]
fragment = "\n".join((HERE / name).read_text(encoding="utf-8") for name in parts)
fragment += f"\n<style>#hk-studio{{--food-atlas:url('data:image/jpeg;base64,{encoded}')}}</style>\n"
fragment += "<script>\n" + (HERE / "시안-동작.js").read_text(encoding="utf-8") + "\n</script>\n"
if len(fragment.encode("utf-8")) > 1_000_000:
    raise ValueError("미리보기의 1MB 제한을 넘었습니다.")
destination = args.output.resolve()
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(fragment, encoding="utf-8")
print(f"시안: {destination}")
print(f"용량: {len(fragment.encode('utf-8')):,} bytes")
