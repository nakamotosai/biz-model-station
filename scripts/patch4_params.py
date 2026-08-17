"""patch4_params.py: 用户 2026-08-13 最终参数全量写入（桌面 t-* + 手机 tm-*）"""
FP = "/home/ubuntu/biz-research/scripts/generate_site.py"

with open(FP) as f:
    src = f.read()

# ===== 桌面参数 =====
# t-height=160 → .pick-b min-height（面板 special-case: 同时 height:auto;max-height:none 解锁 .pick 基类）
# t-pad=34 → padding 四边全等 34px（面板 special-case: padding vpx vpx vpx）
# t-gap=28 → .picks-grid gap
# t-ct=48 → .pick-b-count b font-size
# t-nm=40 → .pick-b-name font-size
# t-sub=15 → .pick-b-sub font-size
# t-btn=14 → .pick-b-btn font-size

repls = [
    # 1. .pick-b: min-height 160 (不变) + padding 34px 四边全等
    ("padding:8px;min-height:160px;height:auto;max-height:none",
     "padding:34px;min-height:160px;height:auto;max-height:none"),
    # 2. .picks-grid gap 28
    ("grid-template-columns:repeat(4,minmax(0,1fr));gap:12px",
     "grid-template-columns:repeat(4,minmax(0,1fr));gap:28px"),
    # 3. .pick-b-count b font-size 48
    (".pick-b-count b{{font-family:\"Maple Mono NF CN\",\"Maple Mono\",Consolas,monospace;font-size:46px",
     ".pick-b-count b{{font-family:\"Maple Mono NF CN\",\"Maple Mono\",Consolas,monospace;font-size:48px"),
    # 4. .pick-b-name font-size 40
    (".pick-b-name{{margin-top:0;font-size:28px",
     ".pick-b-name{{margin-top:0;font-size:40px"),
    # 5. .pick-b-sub font-size 15
    (".pick-b-sub{{max-width:280px;font-size:14px",
     ".pick-b-sub{{max-width:280px;font-size:15px"),
    # 6. .pick-b-btn font-size 14
    (".pick-b-btn{{flex:none;align-self:flex-end;margin-top:0;padding:6px 18px;border:3px solid var(--stroke);box-shadow:4px 4px 0 var(--shadow-c);font-family:Noto Sans SC,Microsoft YaHei,sans-serif;font-size:10px",
     ".pick-b-btn{{flex:none;align-self:flex-end;margin-top:0;padding:6px 18px;border:3px solid var(--stroke);box-shadow:4px 4px 0 var(--shadow-c);font-family:Noto Sans SC,Microsoft YaHei,sans-serif;font-size:14px"),
]

for old, new in repls:
    n = src.count(old)
    assert n == 1, f"锚点不唯一({n}): {old[:60]}"
    src = src.replace(old, new)

# ===== 手机参数（720px media query 内）=====
# tm-h=180 → .pick-b min-height 120→180
# tm-pad=22 → padding 16→22 四边全等
# tm-gap=22 → .picks-grid gap 24→22
# tm-btn=48 → .pick-b-btn width 32→48（箭头模式）

mobile_repls = [
    (".pick{{height:auto;max-height:none}} .pick-b{{min-height:120px;padding:16px;gap:6px}",
     ".pick{{height:auto;max-height:none}} .pick-b{{min-height:180px;padding:22px;gap:6px}"),
    (".picks-grid{{grid-template-columns:1fr 1fr;gap:24px}",
     ".picks-grid{{grid-template-columns:1fr 1fr;gap:22px}"),
    (".pick-b-btn{{position:absolute;bottom:6px;right:6px;width:32px;height:28px",
     ".pick-b-btn{{position:absolute;bottom:6px;right:6px;width:48px;height:28px"),
]

for old, new in mobile_repls:
    n = src.count(old)
    assert n == 1, f"手机锚点不唯一({n}): {old[:60]}"
    src = src.replace(old, new)

with open(FP, "w") as f:
    f.write(src)

# 终验
checks = [
    "padding:34px;min-height:160px;height:auto;max-height:none",
    "gap:28px",
    "font-size:48px",
    "font-size:40px",
    "font-size:15px",
    "font-size:14px",
    "min-height:180px;padding:22px;gap:6px",
    "width:48px;height:28px",
]
for c in checks:
    assert c in src, f"终验失败: {c}"
print("OK: 桌面+手机全部参数已写入")