"""patch3_desktop_params.py: 桌面 t-* 参数写入 generate_site.py（锚点替换）"""
import re

FP = "/home/ubuntu/biz-research/scripts/generate_site.py"

with open(FP) as f:
    src = f.read()

# 1. .pick-b: padding 22px→8px top, min-height 300→160, +height:auto;max-height:none 解锁 .pick 基类固定高度
old1 = "padding:22px 22px 18px;min-height:300px"
new1 = "padding:8px 22px 18px;min-height:160px;height:auto;max-height:none"
assert src.count(old1) == 1, f"锚点1 不唯一: {src.count(old1)}"
src = src.replace(old1, new1)

# 2. .picks-grid gap: 22→12
old2 = "grid-template-columns:repeat(4,minmax(0,1fr));gap:22px"
new2 = "grid-template-columns:repeat(4,minmax(0,1fr));gap:12px"
assert src.count(old2) == 1, f"锚点2 不唯一: {src.count(old2)}"
src = src.replace(old2, new2)

# 3. .pick-b-btn font-size: 15→10
old3 = "font-size:15px;font-weight:800;text-align:center"
new3 = "font-size:10px;font-weight:800;text-align:center"
assert src.count(old3) == 1, f"锚点3 不唯一: {src.count(old3)}"
src = src.replace(old3, new3)

# 4. 手机 media query 的 .pick 解锁（保持现状不变）
# 手机段已有: .pick{height:auto;max-height:none} .pick-b{min-height:120px;padding:16px;gap:6px}
# 不需要改

with open(FP, "w") as f:
    f.write(src)

# 终验
assert "padding:8px 22px 18px;min-height:160px;height:auto;max-height:none" in src, "断言1失败"
assert "gap:12px" in src and "font-size:10px;font-weight:800" in src, "断言2/3失败"
# 手机端保持不变
assert "min-height:120px;padding:16px;gap:6px" in src, "手机参数被意外改动"
print("OK: 桌面参数已写入，手机参数未动")