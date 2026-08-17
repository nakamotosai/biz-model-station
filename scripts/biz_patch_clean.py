#!/usr/bin/env python3
"""Clean patch for biz.saaaai.com generator"""
import subprocess, sys

# Restore from backup
subprocess.run(["cp", 
    "/home/ubuntu/biz-research/backups/generate_site.py.pre-lazyload-20260816-181958",
    "/home/ubuntu/biz-research/scripts/generate_site.py"], check=True)

with open("/home/ubuntu/biz-research/scripts/generate_site.py") as f:
    src = f.read()

# ===== 1. SHIMMER FIX =====
src = src.replace("height:6px;border-bottom:3px solid var(--stroke)}", "height:10px;border-bottom:3px solid var(--stroke)}")
src = src.replace("{{display:flex;height:6px;border-bottom:3px solid var(--stroke)}}", "{{display:flex;height:10px;border-bottom:3px solid var(--stroke)}}")
src = src.replace("rgba(255,255,255,.35) 50%", "rgba(255,255,255,.55) 50%")
src = src.replace("animation:shimmer 3s ease-in-out infinite", "animation:shimmer 1.5s ease-in-out infinite")
src = src.replace("animation:shimmer 3s ease-in-out infinite}}", "animation:shimmer 1.5s ease-in-out infinite}}")
print("1. Shimmer OK")

# ===== 2. MOBILE RELATED ITEMS CSS =====
mobile = """
/* mobile: related items */
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
        ".sticky-bar.hide .sticky-inner{height:0;opacity:0}" + mobile
    )
    print("2. Mobile CSS OK")
else:
    print("2. Mobile CSS SKIP")

# ===== 3. CARD POOL APPROACH =====
# Replace grid HTML: move cards to hidden pool
old_grid = """    <div class="grid" id="grid-model">{''.join(model_cards)}<div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none">{''.join(journey_cards)}<div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none">{''.join(scam_cards)}<div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none">{''.join(agent_cards)}<div class="lazy-sentinel" data-grid="agent"></div></div>"""
new_grid = """    <div class="grid" id="grid-model"><div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none"><div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none"><div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none"><div class="lazy-sentinel" data-grid="agent"></div></div>
    <div id="card-pool" style="display:none">{''.join(model_cards + journey_cards + scam_cards + agent_cards)}</div>"""
if "card-pool" not in src:
    src = src.replace(old_grid, new_grid)
    print("3a. Card pool OK")
else:
    print("3a. Card pool SKIP")

# Replace lazy loading JS
# Must use {{ }} escaping for the f-string template
old_lazy_start = "/* 懒加载：per-grid sentinel"
old_lazy_end = "}})();\n</script>"

new_lazy_body = """  /* 真懒加载：从 card-pool 按需移到 grid */
(function(){{
  var BATCH = 24;
  if(!('IntersectionObserver' in window)) return;
  var pool = document.getElementById('card-pool');
  var pools = {{}};      // tab -> [待移卡片]
  var sentinels = {{}}; // tab -> sentinel element
  var io = null;
  Object.keys(grids).forEach(function(tab){{
    var g = grids[tab];
    var s = g.querySelector('.lazy-sentinel[data-grid="'+tab+'"]');
    if(!s) return;
    var cards = [].slice.call(pool.querySelectorAll('.card[data-type="'+tab+'"]'));
    cards.slice(0, BATCH).forEach(function(c){{ g.insertBefore(c, s); }});
    pools[tab] = cards.slice(BATCH);
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
    var g = grids[tab];
    var s = sentinels[tab];
    for(var i=0;i<n;i++){{ g.insertBefore(p.shift(), s); }}
    if(p.length===0 && io) io.disconnect();
    if (q.value.trim() || sortSel.value || Object.keys(sel).some(function(d){{ return sel[d].size; }})) apply();
  }}
  window.revealAll = function(tab){{
    var p = pools[tab] || [];
    var g = grids[tab];
    var s = sentinels[tab];
    while(p.length){{ g.insertBefore(p.shift(), s); }}
    if(io) io.disconnect();
  }};
  observe(active);
  document.querySelector('.wall-ctrl').addEventListener('click', function(e){{
    var b = e.target.closest('.view-btn[data-tab]'); if(!b) return;
    var tab = b.dataset.tab;
    setTimeout(function(){{ observe(tab); }}, 50);
  }});
}})();"""

start_idx = src.find(old_lazy_start)
end_idx = src.find(old_lazy_end, start_idx)
if start_idx > 0 and end_idx > 0:
    end_idx = end_idx + len(old_lazy_end)
    old_lazy = src[start_idx:end_idx]
    src = src[:start_idx] + new_lazy_body + src[end_idx:]
    print("3b. Lazy JS OK")
else:
    print("3b. Lazy JS NOT FOUND!")

# Fix apply() - remove data-lazy
# The actual format is: cards.forEach(c => {{ if (visible.includes(c)) {{ if (filterOn || c.dataset.lazy !== '1') c.style.display=''; }} else {{ c.style.display='none'; }} }});
old_apply = "cards.forEach(c => {{ if (visible.includes(c)) {{ if (filterOn || c.dataset.lazy !== '1') c.style.display=''; }} else {{ c.style.display='none'; }} }});"
new_apply = "cards.forEach(c => {{ c.style.display=visible.includes(c)?'':'none'; }});"
if old_apply in src:
    src = src.replace(old_apply, new_apply)
    print("3c. apply() OK")
else:
    # Try without the else {{ }}
    old_apply2 = "cards.forEach(c => {{ if (visible.includes(c)) {{ if (filterOn || c.dataset.lazy !== '1') c.style.display=''; }} else c.style.display='none'; }});"
    if old_apply2 in src:
        src = src.replace(old_apply2, new_apply)
        print("3c. apply() OK (v2)")
    else:
        print("3c. apply() NOT FOUND!")
        # Debug
        for i, line in enumerate(src.split("\n")):
            if "c.dataset.lazy" in line:
                print(f"  Line {i}: {line.strip()[:120]}")

# Fix tab switch
old_tab = """  tabs.forEach(x => x.classList.toggle('on', x === t));
  active = t.dataset.tab;
  Object.entries(grids).forEach(([k,g]) => g.style.display = (k === active) ? '' : 'none');
  apply();"""
new_tab = """  tabs.forEach(x => x.classList.toggle('on', x === t));
  active = t.dataset.tab;
  Object.entries(grids).forEach(([k,g]) => g.style.display = (k === active) ? '' : 'none');
  if (grids[active].querySelectorAll('.card').length === 0) {{
    var p = pools[active] || [];
    var s = sentinels[active];
    if (s && p.length > 0) {{
      var n = Math.min(BATCH, p.length);
      for (var i=0; i<n; i++) {{ grids[active].insertBefore(p.shift(), s); }}
    }}
  }}
  apply();"""
if old_tab in src:
    src = src.replace(old_tab, new_tab)
    print("3d. Tab switch OK")
else:
    print("3d. Tab switch NOT FOUND!")
    # Debug
    for i, line in enumerate(src.split("\n")):
        if "x.classList.toggle" in line:
            print(f"  Line {i}: {line.strip()[:120]}")

# Write
with open("/home/ubuntu/biz-research/scripts/generate_site.py", "w") as f:
    f.write(src)

# Syntax check
import py_compile
try:
    py_compile.compile("/home/ubuntu/biz-research/scripts/generate_site.py", doraise=True)
    print("\nPython syntax OK!")
except py_compile.PyCompileError as e:
    print(f"\nSyntax error: {e}")

print("\nDone!")