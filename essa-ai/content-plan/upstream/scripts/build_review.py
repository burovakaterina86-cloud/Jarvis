"""Страница просмотра тестового прогона: python build_review.py <run_dir>"""
import json, sys, os, html
run = sys.argv[1]
NICHES = [("ai", "Нейросети в контенте и маркетинге"), ("psy", "Психолог")]
def k(n):
    n = n or 0
    return f"{n/1e6:.1f} млн" if n >= 1e6 else f"{n/1e3:.1f} тыс" if n >= 1e3 else str(int(n))
e = lambda s: html.escape(str(s or ""))
parts = []
nav = []
for code, title in NICHES:
    p = os.path.join(run, f"{code}_selection.json")
    if not os.path.exists(p): continue
    s = json.load(open(p, encoding="utf-8"))
    top, ns, rej = s.get("top15", []), s.get("no_speech", []), s.get("rejected", [])
    nav.append(f'<a href="#{code}">{e(title)}</a>')
    cards = []
    for i, r in enumerate(top, 1):
        slot = r.get("slot", "")
        badge = {"воронка": "b-funnel", "аутлаер": "b-out"}.get(slot, "b-strong")
        x = f' · ×{r["x_author"]} к норме автора' if r.get("x_author") else ""
        lm = f'<div class="lm"><b>Лид-магнит:</b> {e(r["lead_magnet_idea"])}</div>' if r.get("lead_magnet_idea") else ""
        cards.append(f'''<article class="card">
  <div class="num">{i}</div>
  <div class="body">
    <div class="meta"><span class="badge {badge}">{e(slot)}</span><span class="fmt">{e(r.get("format"))}</span></div>
    <h3>{e(r.get("topic_ru"))}</h3>
    <p class="hook">«{e(r.get("hook_ru"))}»</p>
    <p class="why">{e(r.get("why"))}</p>{lm}
    <div class="stats"><span>💬 {k(r.get("comments"))}</span><span>▶ {k(r.get("views"))}</span><span>{e(r.get("age_days"))} дн.{e(x)}</span></div>
    <a class="link" href="{e(r.get("url"))}" target="_blank" rel="noopener">@{e(r.get("author"))} — открыть рилс ↗</a>
  </div></article>''')
    ns_rows = "".join(f'<tr><td>{"⭐ " if r.get("wow") else ""}<a href="{e(r.get("url"))}" target="_blank">@{e(r.get("author"))}</a></td><td>{e(r.get("topic_ru"))}</td><td>{k(r.get("comments"))}</td><td>{k(r.get("views"))}</td></tr>' for r in ns)
    reasons = {}
    for r in rej: reasons.setdefault(r.get("reason", "—").split(":")[0].strip(), 0); reasons[r.get("reason", "—").split(":")[0].strip()] += 1
    rej_rows = "".join(f'<tr><td><a href="https://www.instagram.com/reel/{e(r.get("code"))}/" target="_blank">@{e(r.get("author"))}</a></td><td>{k(r.get("comments"))}</td><td>{e(r.get("reason"))}</td></tr>' for r in rej)
    parts.append(f'''<section id="{code}">
<h2>{e(title)}</h2>
<p class="sum">В плане: <b>{len(top)}</b> · без речи: <b>{len(ns)}</b> · отсеяно по тексту: <b>{len(rej)}</b></p>
<div class="cards">{"".join(cards)}</div>
<details><summary>Рилсы без речи — отдельный список ({len(ns)})</summary><div class="tw"><table><tr><th>Автор</th><th>О чём</th><th>Комм.</th><th>Просм.</th></tr>{ns_rows}</table></div></details>
<details><summary>Отсеяно ({len(rej)})</summary><div class="tw"><table><tr><th>Автор</th><th>Комм.</th><th>Причина</th></tr>{rej_rows}</table></div></details>
</section>''')
page = f'''<title>Контент-план 2.0 · тест рилсов</title>
<style>
:root{{--bg:#0B0E13;--card:#12161D;--line:#232A35;--text:#E8ECF2;--muted:#8A94A6;--acc:#FFD84D;--funnel:#FF8A4C;--out:#6FD3A0}}
*{{box-sizing:border-box}} body{{background:var(--bg);color:var(--text);font:15px/1.5 "Segoe UI",system-ui,sans-serif;margin:0;padding:32px 16px}}
.wrap{{max-width:980px;margin:0 auto}} h1{{font-size:28px;margin:0 0 6px}} .lead{{color:var(--muted);margin:0 0 18px}}
nav a{{color:var(--acc);margin-right:18px;text-decoration:none}} h2{{font-size:22px;margin:40px 0 4px;border-bottom:1px solid var(--line);padding-bottom:8px}}
.sum{{color:var(--muted)}} .cards{{display:grid;gap:12px}}
.card{{display:flex;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}}
.num{{font-size:22px;font-weight:700;color:var(--acc);min-width:28px}} .body{{flex:1;min-width:0}}
.meta{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:4px}} .badge{{font-size:12px;padding:2px 8px;border-radius:99px;font-weight:600;color:#0B0E13}}
.b-funnel{{background:var(--funnel)}} .b-out{{background:var(--out)}} .b-strong{{background:#9FB4FF}} .fmt{{font-size:12px;color:var(--muted)}}
h3{{margin:2px 0 4px;font-size:17px}} .hook{{margin:0 0 4px;color:#C9D1DD;font-style:italic}} .why{{margin:0 0 6px;color:var(--muted)}}
.lm{{background:#1B1A12;border-left:3px solid var(--acc);padding:6px 10px;border-radius:6px;margin:6px 0}}
.stats{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:13px;margin:6px 0}} .link{{color:var(--acc);text-decoration:none;font-weight:600}}
details{{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px}} summary{{cursor:pointer;font-weight:600}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;margin-top:8px;font-size:13px}} td,th{{border-top:1px solid var(--line);padding:6px;text-align:left;vertical-align:top}} td a{{color:var(--acc)}}
</style>
<div class="wrap"><h1>Тестовый прогон: рилсы на неделю</h1>
<p class="lead">15.09.2026 · свежие за 14 дней · англоязычный рынок · отбор по цифрам → расшифровка → отбор по тексту</p>
<nav>{"".join(nav)}</nav>{"".join(parts)}</div>'''
out = os.path.join(run, "review.html")
open(out, "w", encoding="utf-8").write(page)
print(out)
