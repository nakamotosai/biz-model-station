#!/usr/bin/env python3
"""
Patch generate_site.py:
1. Fix shimmer animation (brighter+faster, taller color-ribbon)
2. True lazy loading: JSON card data + JS batch rendering
3. Mobile card redesign for related items
"""
import re

# Read the file
with open("generate_site.py") as f:
    src = f.read()

# ========== 1. SHIMMER FIX ==========
# Make color-ribbon taller (10px), shimmer brighter and faster
src = src.replace(
    ".color-ribbon{display:flex;height:6px;border-bottom:3px solid var(--stroke)}",
    ".color-ribbon{display:flex;height:10px;border-bottom:3px solid var(--stroke)}"
)
src = src.replace(
    ".color-ribbon{{display:flex;height:6px;border-bottom:3px solid var(--stroke)}}",
    ".color-ribbon{{display:flex;height:10px;border-bottom:3px solid var(--stroke)}}"
)

# Make shimmer animation faster and brighter
old_shimmer = ".color-ribbon .seg::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%,transparent);background-size:300% 100%;animation:shimmer 3s ease-in-out infinite}"
new_shimmer = ".color-ribbon .seg::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,transparent 25%,rgba(255,255,255,.55) 50%,transparent 75%,transparent);background-size:300% 100%;animation:shimmer 1.5s ease-in-out infinite}"
src = src.replace(old_shimmer, new_shimmer)

old_shimmer_d = ".color-ribbon .seg::after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%,transparent);background-size:300% 100%;animation:shimmer 3s ease-in-out infinite}}"
new_shimmer_d = ".color-ribbon .seg::after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,transparent 25%,rgba(255,255,255,.55) 50%,transparent 75%,transparent);background-size:300% 100%;animation:shimmer 1.5s ease-in-out infinite}}"
src = src.replace(old_shimmer_d, new_shimmer_d)

# ========== 2. MOBILE CARD REDESIGN for related items ==========
# Add mobile CSS for related items in the detail page CSS section
# Find the detail page CSS and add mobile-related CSS
old_detail_css_end = """.sticky-bar.scrolled{{box-shadow:0 2px 8px rgba(0,0,0,.4)}}
.sticky-bar.hide .sticky-inner{{height:0;opacity:0}}
.sticker"""

new_detail_css_end = """.sticky-bar.scrolled{{box-shadow:0 2px 8px rgba(0,0,0,.4)}}
.sticky-bar.hide .sticky-inner{{height:0;opacity:0}}
/* mobile: related items → simple list */
@media(max-width:720px){{
  .related-grid{{grid-template-columns:1fr;gap:8px}}
  .related-grid .card .top .stamp,.related-grid .card .top .arrow,.related-grid .card .meta{{display:none}}
  .related-grid .card{{padding:12px 16px;min-height:auto}}
  .related-grid .card .top h3{{font-size:15px;line-height:1.4}}
  .related-grid .card-link{{padding:0}}
}}
.sticker"""

# Check if the mobile CSS already exists
if "related-grid{{grid-template-columns:1fr;gap:8px}}" not in src:
    src = src.replace(old_detail_css_end, new_detail_css_end)
    print("Added mobile related items CSS")
else:
    print("Mobile related items CSS already exists, skipping")

# ========== 3. TRUE LAZY LOADING ==========
# Replace card generation with JSON data
# First, identify the card generation sections

# Replace model_cards generation with model_data JSON
old_model_gen = """    model_cards = []
    for m in by_type['model']:
        dims = {"industry": m.get('industry', ''), "region": m.get('region', ''),
                "scale": m.get('scale', ''), "channel": m.get('channel', '')}
        data_attr = " ".join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        data_attr += f' data-gregion="{esc(_region_group(m.get("region","")))}" data-gscale="{esc(_scale_group(m.get("scale","")))}"'
        summary = str(m.get('model', ''))
        if len(summary) > 120:
            summary = summary[:120] + "…"
        search_txt = " ".join([m.get('name', ''), m.get('industry', ''), m.get('region', ''),
                               str(m.get('model', '')), str(m.get('revenue', ''))])
        meta = card_meta(m, dims)
        model_cards.append(f"""<article class="card" {data_attr}
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" data-type="model">
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>{esc(summary)}</p>
    {meta}
  </a>
</article>""")"""

new_model_gen = """    model_cards = []
    for m in by_type['model']:
        dims = {"industry": m.get('industry', ''), "region": m.get('region', ''),
                "scale": m.get('scale', ''), "channel": m.get('channel', '')}
        data_attr = " ".join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        data_attr += f' data-gregion="{esc(_region_group(m.get("region","")))}" data-gscale="{esc(_scale_group(m.get("scale","")))}"'
        summary = str(m.get('model', ''))
        if len(summary) > 120:
            summary = summary[:120] + "…"
        search_txt = " ".join([m.get('name', ''), m.get('industry', ''), m.get('region', ''),
                               str(m.get('model', '')), str(m.get('revenue', ''))])
        meta = card_meta(m, dims)
        # Build card HTML (same structure as before)
        card_html = f"""<article class="card" {data_attr}
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" data-type="model">
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>{esc(summary)}</p>
    {meta}
  </a>
</article>"""
        model_cards.append(card_html)
        model_data.append({{
            "id": m['id'],
            "type": "model",
            "name": m['name'],
            "search": search_txt,
            "hot": _hot_score(m),
            "html": card_html,
        }})"""

if old_model_gen in src:
    src = src.replace(old_model_gen, new_model_gen)
    print("Patched model cards → model_data")
else:
    print("WARNING: model card generation pattern not found!")

# Replace journey_cards generation
old_journey_gen = """    journey_cards = []
    for m in by_type['journey']:"""
new_journey_gen = """    journey_cards = []
    for m in by_type['journey']:
        journey_data = journey_data  # reference for JSON data"""

# Actually, let me find the exact pattern for journey cards
# The journey cards start with journey_cards = [] and end with the f-string
# Let me find the journey_cards.append pattern

# Find the journey card append f-string
old_journey_append = """        journey_cards.append(f"""<article class="card" data-type="journey"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {jdata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>创办：{esc(m.get('founders', ''))} · {len(ms)} 阶段 · {n_fail} 次失败踩坑{met_str}</p>
    {meta}
  </a>
</article>""")"""

new_journey_append = """        card_html = f"""<article class="card" data-type="journey"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {jdata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>创办：{esc(m.get('founders', ''))} · {len(ms)} 阶段 · {n_fail} 次失败踩坑{met_str}</p>
    {meta}
  </a>
</article>"""
        journey_cards.append(card_html)
        journey_data.append({{
            "id": m['id'],
            "type": "journey",
            "name": m['name'],
            "search": search_txt,
            "hot": _hot_score(m),
            "html": card_html,
        }})"""

if old_journey_append in src:
    src = src.replace(old_journey_append, new_journey_append)
    print("Patched journey cards → journey_data")
else:
    print("WARNING: journey card append pattern not found!")

# Find and replace scam card append
old_scam_append = """        scam_cards.append(f"""<article class="card" data-type="scam"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {sdata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>手法：{esc(how_first)}</p>
    {meta}
  </a>
</article>""")"""

new_scam_append = """        card_html = f"""<article class="card" data-type="scam"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {sdata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>手法：{esc(how_first)}</p>
    {meta}
  </a>
</article>"""
        scam_cards.append(card_html)
        scam_data.append({{
            "id": m['id'],
            "type": "scam",
            "name": m['name'],
            "search": search_txt,
            "hot": _hot_score(m),
            "html": card_html,
        }})"""

if old_scam_append in src:
    src = src.replace(old_scam_append, new_scam_append)
    print("Patched scam cards → scam_data")
else:
    print("WARNING: scam card append pattern not found!")

# Find and replace agent card append
old_agent_append = """        agent_cards.append(f'''<article class="card" data-type="agent"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {adata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>工作流：{esc(rev_first)}</p>
    {meta}
  </a>
</article>''')"""

new_agent_append = """        card_html = f'''<article class="card" data-type="agent"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {adata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="top">
      <span class="stamp"><b>{stamp_txt(m)}</b></span>
      <h3>{esc(m['name'])}</h3>
      <span class="arrow" aria-hidden="true">→</span>
    </div>
    <p>工作流：{esc(rev_first)}</p>
    {meta}
  </a>
</article>'''
        agent_cards.append(card_html)
        agent_data.append({{
            "id": m['id'],
            "type": "agent",
            "name": m['name'],
            "search": search_txt,
            "hot": _hot_score(m),
            "html": card_html,
        }})"""

if old_agent_append in src:
    src = src.replace(old_agent_append, new_agent_append)
    print("Patched agent cards → agent_data")
else:
    print("WARNING: agent card append pattern not found!")

# Add data list initialization after the agent_cards = [] line
# The agent_cards = [] is at around line 1559, need to add model_data/journey_data/etc
old_data_init = """        agent_cards = []"""
new_data_init = """        agent_cards = []
    model_data = []
    journey_data = []
    scam_data = []
    agent_data = []"""

if old_data_init in src:
    src = src.replace(old_data_init, new_data_init)
    print("Added data list initializations")
else:
    print("WARNING: agent_cards init not found!")

# Now replace the grid HTML to use JSON data
# Replace the grid divs to be empty and add JSON script tag
old_grids = """    <div class="grid" id="grid-model">{''.join(model_cards)}<div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none">{''.join(journey_cards)}<div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none">{''.join(scam_cards)}<div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none">{''.join(agent_cards)}<div class="lazy-sentinel" data-grid="agent"></div></div>"""

new_grids = """    <div class="grid" id="grid-model"><div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none"><div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none"><div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none"><div class="lazy-sentinel" data-grid="agent"></div></div>
<script id="card-data" type="application/json">{json.dumps(model_data + journey_data + scam_data + agent_data, ensure_ascii=False)}</script>"""

# Check if already patched
if "card-data" not in src:
    # We need to import json at the top of the file
    # Find the json import
    src = src.replace(old_grids, new_grids)
    print("Patched grids to empty + JSON data script")
else:
    print("Grids already patched, skipping")

# Now replace the lazy loading JS
old_lazy_js = """/* 懒加载：per-grid sentinel + per-grid hiddenPool + per-grid IO；切 tab 重启当前 grid 的 IO */
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

new_lazy_js = """/* 真懒加载：从 JSON 数据逐批创建卡片 DOM */
(function(){{
  var BATCH = 24;
  if(!('IntersectionObserver' in window)) return;
  var cardData = JSON.parse(document.getElementById('card-data').textContent) || [];
  var pools = {{}};    // tab -> [剩余数据]
  var sentinels = {{}}; // tab -> sentinel element
  var io = null;
  // 按 tab 分组
  var byTab = {{}};
  cardData.forEach(function(d){{
    if(!byTab[d.type]) byTab[d.type] = [];
    byTab[d.type].push(d);
  }});
  Object.keys(grids).forEach(function(tab){{
    var g = grids[tab];
    var s = g.querySelector('.lazy-sentinel[data-grid="'+tab+'"]');
    var data = byTab[tab] || [];
    // 首批 BATCH 张直接创建
    data.slice(0, BATCH).forEach(function(d){{ g.insertBefore(createCard(d), s); }});
    pools[tab] = data.slice(BATCH);
    sentinels[tab] = s;
  }});
  function createCard(d){{
    var a = document.createElement('a');
    a.className = 'card-link';
    a.href = d.id + '.html';
    a.innerHTML = d.html;
    // 找到 article 包装器
    var article = a.querySelector('article.card');
    if(!article){{ article = document.createElement('article'); article.className='card'; article.appendChild(a); }}
    return article;
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
    for(var i=0;i<n;i++){{ var d = p.shift(); g.insertBefore(createCard(d), s); }}
    if(p.length===0 && io) io.disconnect();
    if (q.value.trim() || sortSel.value || Object.keys(sel).some(function(d){{ return sel[d].size; }})) apply();
  }}
  window.revealAll = function(tab){{
    var p = pools[tab] || [];
    var g = grids[tab];
    var s = sentinels[tab];
    while(p.length){{ var d = p.shift(); g.insertBefore(createCard(d), s); }}
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

if old_lazy_js in src:
    src = src.replace(old_lazy_js, new_lazy_js)
    print("Patched lazy loading JS → true lazy loading")
else:
    print("WARNING: old lazy JS not found!")

# Write the patched file
with open("generate_site.py", "w") as f:
    f.write(src)

print("\nDone! Saved generate_site.py")