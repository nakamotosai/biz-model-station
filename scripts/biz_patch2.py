#!/usr/bin/env python3
"""Patch generate_site.py: shimmer + mobile CSS + true lazy loading"""
import re, json

with open("/home/ubuntu/biz-research/scripts/generate_site.py") as f:
    src = f.read()

# ===== 1. SHIMMER FIX =====
src = src.replace(".color-ribbon{display:flex;height:6px;border-bottom:3px solid var(--stroke)}",
                  ".color-ribbon{display:flex;height:10px;border-bottom:3px solid var(--stroke)}")
src = src.replace(".color-ribbon{{display:flex;height:6px;border-bottom:3px solid var(--stroke)}}",
                  ".color-ribbon{{display:flex;height:10px;border-bottom:3px solid var(--stroke)}}")
src = src.replace("rgba(255,255,255,.35) 50%", "rgba(255,255,255,.55) 50%")
src = src.replace("animation:shimmer 3s ease-in-out infinite", "animation:shimmer 1.5s ease-in-out infinite")
src = src.replace("animation:shimmer 3s ease-in-out infinite}}", "animation:shimmer 1.5s ease-in-out infinite}}")
print("1. Shimmer OK")

# ===== 2. MOBILE RELATED ITEMS CSS =====
mobile_css = """
/* mobile: related items -> simple list */
@media(max-width:720px){
  .related-grid{grid-template-columns:1fr;gap:6px}
  .related-grid .card .top .stamp,.related-grid .card .top .arrow,.related-grid .card .meta{display:none}
  .related-grid .card{padding:8px 12px;min-height:auto;border-width:2px;box-shadow:2px 2px 0 var(--shadow-c)}
  .related-grid .card .top h3{font-size:14px;line-height:1.5;letter-spacing:0}
  .related-grid .card-link{padding:0}
  .related-grid .card .top{gap:0}
}
"""
if "related-grid{grid-template-columns:1fr;gap:6px}" not in src:
    src = src.replace(
        ".sticky-bar.hide .sticky-inner{height:0;opacity:0}",
        ".sticky-bar.hide .sticky-inner{height:0;opacity:0}" + mobile_css
    )
    print("2. Mobile CSS OK")
else:
    print("2. Mobile CSS SKIP")

# ===== 3. TRUE LAZY LOADING =====
# 3a. Add data lists
src = src.replace("    agent_cards = []\n    model_data = []",
                  "    agent_cards = []\n    model_data = []\n    journey_data = []\n    scam_data = []\n    agent_data = []")
print("3a. Data lists OK")

# 3b. Add data appends (card_html -> both lists)
src = src.replace("model_cards.append(card_html)", "model_cards.append(card_html)\n        model_data.append(card_html)")
src = src.replace("journey_cards.append(card_html)", "journey_cards.append(card_html)\n        journey_data.append(card_html)")
src = src.replace("scam_cards.append(card_html)", "scam_cards.append(card_html)\n        scam_data.append(card_html)")
src = src.replace("agent_cards.append(card_html)", "agent_cards.append(card_html)\n        agent_data.append(card_html)")
print("3b. Data appends OK")

# 3c. Replace card grids with empty + JSON script
json_script = '<script id="card-data" type="application/json">' + '{{json.dumps(model_data + journey_data + scam_data + agent_data, ensure_ascii=False)}}' + '</script>'
old_grid = """    <div class="grid" id="grid-model">{''.join(model_cards)}<div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none">{''.join(journey_cards)}<div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none">{''.join(scam_cards)}<div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none">{''.join(agent_cards)}<div class="lazy-sentinel" data-grid="agent"></div></div>"""
new_grid = """    <div class="grid" id="grid-model"><div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none"><div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none"><div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none"><div class="lazy-sentinel" data-grid="agent"></div></div>
    """ + json_script
if "card-data" not in src:
    src = src.replace(old_grid, new_grid)
    print("3c. Grids OK")
else:
    print("3c. Grids SKIP")

# 3d. Replace lazy loading JS (with {{ }} f-string escaping)
old_lazy = """/* 懒加载：per-grid sentinel + per-grid hiddenPool + per-grid IO；切 tab 重启当前 grid 的 IO */
(function(){{
  var BATCH = 24;
  if(!('IntersectionObserver' in window)) return;
  var pools = {{}};      // tab -> [隐藏卡片]
  var sentinels = {{}}; // tab -> sentinel element
  var io = null;
  Object.keys(grids).forEach(function(tab){{
    var g = grids[tab];
    var s = g.querySelector('.lazy-sentinel[data-grid="'+tab+'"]');
    if(!s) return;
    var cards = [].slice.call(g.querySelectorAll('.card'));
    var hidden = cards.slice(BATCH);
    hidden.forEach(function(c){{ c.dataset.lazy='1'; c.style.display='none'; }});
    pools[tab] = hidden;
    sentinels[tab] = s;
  }});
  function observe(tab){{
    if (io) io.disconnect();
    io = new IntersectionObserver(function(entries){{
      if(entries.some(function(e){{ return e.isIntersecting; }})){{ reveal(tab); }}
    }}, {{rootMargin:'600px 0px'}});
    io.observe(sentinels[tab]);
  }}
  function reveal(tab){{
    var p = pools[tab] || [];
    var n = Math.min(BATCH, p.length);
    for(var i=0;i<n;i++){{ var c=p.shift(); c.dataset.lazy=''; c.style.display=''; }}
    if(p.length===0 && io) io.disconnect();
    if (q.value.trim() || sortSel.value || Object.keys(sel).some(function(d){{ return sel[d].size; }})) apply();
  }}
  window.revealAll = function(tab){{
    var p = pools[tab] || [];
    while(p.length){{ var c=p.shift(); c.dataset.lazy=''; c.style.display=''; }}
    if(io) io.disconnect();
  }};
  observe(active);
  // 切 tab 时重启 IO 观察新 grid 的 sentinel
  document.querySelector('.wall-ctrl').addEventListener('click', function(e){{
    var b = e.target.closest('.view-btn[data-tab]'); if(!b) return;
    var tab = b.dataset.tab;
    setTimeout(function(){{ observe(tab); }}, 50);
  }});
}})();"""

new_lazy = """/* 真懒加载：从 JSON 数据逐批创建卡片 DOM */
(function(){{
  var BATCH = 24;
  if(!('IntersectionObserver' in window)) return;
  var cardData = JSON.parse(document.getElementById('card-data').textContent) || [];
  var pools = {{}};    // tab -> [剩余卡片 HTML]
  var sentinels = {{}}; // tab -> sentinel element
  var io = null;
  // 按 tab 分组（card 的 data-type 属性确定 tab）
  var byTab = {{}};
  cardData.forEach(function(html){{
    var m = html.match(/data-type="(\\w+)"/);
    var t = m ? m[1] : 'model';
    if(!byTab[t]) byTab[t] = [];
    byTab[t].push(html);
  }});
  Object.keys(grids).forEach(function(tab){{
    var g = grids[tab];
    var s = g.querySelector('.lazy-sentinel[data-grid="'+tab+'"]');
    var data = byTab[tab] || [];
    // 首批 BATCH 张直接创建
    data.slice(0, BATCH).forEach(function(html){{ g.insertBefore(cardFromHTML(html), s); }});
    pools[tab] = data.slice(BATCH);
    sentinels[tab] = s;
  }});
  function cardFromHTML(html){{
    var d = document.createElement('div');
    d.innerHTML = html;
    return d.firstElementChild;
  }}
  function observe(tab){{
    if (io) io.disconnect();
    io = new IntersectionObserver(function(entries){{
      if(entries.some(function(e){{ return e.isIntersecting; }})){{ reveal(tab); }}
    }}, {{rootMargin:'600px 0px'}});
    io.observe(sentinels[tab]);
  }}
  function reveal(tab){{
    var p = pools[tab] || [];
    var n = Math.min(BATCH, p.length);
    var g = grids[tab];
    var s = sentinels[tab];
    for(var i=0;i<n;i++){{ g.insertBefore(cardFromHTML(p.shift()), s); }}
    if(p.length===0 && io) io.disconnect();
    if (q.value.trim() || sortSel.value || Object.keys(sel).some(function(d){{ return sel[d].size; }})) apply();
  }}
  window.revealAll = function(tab){{
    var p = pools[tab] || [];
    var g = grids[tab];
    var s = sentinels[tab];
    while(p.length){{ g.insertBefore(cardFromHTML(p.shift()), s); }}
    if(io) io.disconnect();
  }};
  observe(active);
  // 切 tab 时重启 IO 观察新 grid 的 sentinel
  document.querySelector('.wall-ctrl').addEventListener('click', function(e){{
    var b = e.target.closest('.view-btn[data-tab]'); if(!b) return;
    var tab = b.dataset.tab;
    setTimeout(function(){{ observe(tab); }}, 50);
  }});
}})();"""

if old_lazy in src:
    src = src.replace(old_lazy, new_lazy)
    print("3d. Lazy JS OK")
else:
    # Try without the comment
    print("3d. WARNING: old lazy JS not found!")
    # Show context
    idx = src.find("var BATCH = 24;")
    if idx > 0:
        print(f"    Found at {idx}, showing context:")
        print(src[idx-50:idx+300])

# 3e. Fix apply() - remove data-lazy (uses {{ }} in f-string)
old_apply = "cards.forEach(c => {{ if (visible.includes(c)) {{ if (filterOn || c.dataset.lazy !== '1') c.style.display=''; }} else c.style.display='none'; }});"
new_apply = "cards.forEach(c => {{ c.style.display=visible.includes(c)?'':'none'; }});"
if old_apply in src:
    src = src.replace(old_apply, new_apply)
    print("3e. apply() OK")
else:
    print("3e. WARNING: apply() not found!")

# 3f. Fix tab switch (uses {{ }} in f-string)
old_tab = """  tabs.forEach(x => x.classList.toggle('on', x === t));
  active = t.dataset.tab;
  Object.entries(grids).forEach(([k,g]) => g.style.display = (k === active) ? '' : 'none');
  apply();"""
new_tab = """  tabs.forEach(x => x.classList.toggle('on', x === t));
  active = t.dataset.tab;
  Object.entries(grids).forEach(([k,g]) => g.style.display = (k === active) ? '' : 'none');
  // 如果切到的 tab 还没创建首批卡片，创建之
  var g = grids[active];
  if (g && g.querySelectorAll('.card').length === 0) {{
    var p = pools[active] || [];
    var s = sentinels[active];
    if (s && p.length > 0) {{
      var n = Math.min(BATCH, p.length);
      var batch = p.splice(0, n);
      batch.forEach(function(html) {{ g.insertBefore(cardFromHTML(html), s); }});
    }}
  }}
  apply();"""
if old_tab in src:
    src = src.replace(old_tab, new_tab)
    print("3f. Tab switch OK")
else:
    print("3f. WARNING: tab switch not found!")

# Write result
with open("/home/ubuntu/biz-research/scripts/generate_site.py", "w") as f:
    f.write(src)

# Quick syntax check
import py_compile
try:
    py_compile.compile("/home/ubuntu/biz-research/scripts/generate_site.py", doraise=True)
    print("\nPython syntax OK!")
except py_compile.PyCompileError as e:
    print(f"\nSyntax error: {e}")

print("\nDone!")