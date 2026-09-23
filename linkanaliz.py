#!/usr/bin/env python3
"""
nocturn-linkanaliz — Jev destekli internal link analiz aracı.
CODE → adayları bul (sitemap + TF-IDF) · JEV → semantik karar (0-1) · CODE → uygula.
Stdlib only. Jev'e aritmetik verilmez; eşik bu dosyada (--esik).
"""
import argparse, csv, json, math, os, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

UA = {"User-Agent": "nocturn-linkanaliz/0.1 (+https://nocturndev.com)"}
STOP = set("ve veya ile bir bu şu o da de ki mi ama fakat için gibi olarak olan daha çok az en ne nasıl neden var yok değil the of and to in a is for on with as by at from your can".split())

def getir(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

class Sayfa(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.basliklar, self.parcalar, self.linkler = "", [], [], []
        self._tag, self._atla = None, 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"): self._atla += 1; return
        # NAV/HASAR atlamasi (gerçek vaka, 2026-09-24 — blog.rust-lang.org
        # testinde anchor adaylarının HEPSİ "Rust Blog Rust Install" çıktı:
        # menü metni makale metnine karışıyordu). nav/header/footer/aside
        # içeriği makale gövdesi değildir.
        if tag in ("nav", "header", "footer", "aside"): self._atla += 1; return
        if tag == "title" and not self._tag: self._tag = "title"
        elif tag in ("h1", "h2", "h3") and not self._tag: self._tag = tag
        elif tag == "a":
            d = dict(attrs)
            if d.get("href"): self.linkler.append(d["href"])
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav", "header", "footer", "aside") and self._atla:
            self._atla -= 1
        if self._tag and tag in ("title", "h1", "h2", "h3"): self._tag = None
    def handle_data(self, veri):
        v = veri.strip()
        if not v or self._atla: return
        if self._tag == "title": self.title += " " + v
        elif self._tag in ("h1", "h2", "h3"): self.parcalar.append(v)
        else: self.parcalar.append(v)

def ayristir(url, html):
    p = Sayfa()
    try: p.feed(html)
    except Exception: pass
    p.close()
    host = urllib.parse.urlparse(url).netloc
    iceri = set()
    for h in p.linkler:
        mut = urllib.parse.urljoin(url, h.split("#")[0])
        if urllib.parse.urlparse(mut).netloc == host and urllib.parse.urlparse(mut).path not in ("", "/"):
            iceri.add(mut.rstrip("/"))
    return {"url": url.rstrip("/"), "title": " ".join((p.title or "").split()),
            "basliklar": [b for b in p.parcalar if b in p.basliklar] or p.parcalar[:3],
            "metin": re.sub(r"\s+", " ", " ".join(p.parcalar))[:8000],
            "linkler": sorted(iceri)}

# ——— sitemap ———
def sitemap_adaylari(site, limit):
    site = site.rstrip("/")
    adaylar = [f"{site}/sitemap.xml", f"{site}/sitemap_index.xml", f"{site}/sitemap-index.xml"]
    try:
        for satir in getir(site + "/robots.txt", 15).splitlines():
            if satir.lower().startswith("sitemap:"):
                adaylar.insert(0, satir.split(":", 1)[1].strip())
    except Exception:
        pass
    urls, incelenen = [], set()
    while adaylar and len(urls) < limit * 2 and len(incelenen) < 8:
        sm = adaylar.pop(0)
        if sm in incelenen: continue
        incelenen.add(sm)
        try: icerik = getir(sm)
        except Exception: continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", icerik)
        if "<sitemapindex" in icerik:
            adaylar.extend(locs[:25]); continue
        for u in locs:
            u = u.strip()
            if u.startswith(site) and not re.search(r"\.(xml|jpg|jpeg|png|webp|pdf|svg|gif)$", u) and u.rstrip("/") != site:
                urls.append(u)
        if len(urls) >= limit * 2: break
    gorulen, temiz = set(), []
    for u in urls:
        if u not in gorulen:
            gorulen.add(u); temiz.append(u)
        if len(temiz) >= limit: break
    return temiz

# ——— TF-IDF ———
def tokenize(metin):
    return [w for w in re.findall(r"[a-zçğıöşüà-ÿ]{3,}", metin.lower()) if w not in STOP]

def vektor(metin):
    say = {}
    for w in tokenize(metin): say[w] = say.get(w, 0) + 1
    top = math.sqrt(sum(v * v for v in say.values())) or 1
    return {k: v / top for k, v in say.items()}

def cosine(a, b):
    if len(a) > len(b): a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())

# ——— cümle/anchor ———
def cumleler(metin):
    return [c.strip() for c in re.split(r"(?<=[.!?])\s+|\n+", metin) if 60 < len(c) < 360]

def en_iyi_cumle(metin, hedef_set):
    en, skor = None, 0
    for c in cumleler(metin):
        ortak = sum(1 for k in hedef_set if k in c.lower())
        if ortak > skor: en, skor = c, ortak
    return en

def anchor_adayi(cumle, hedef_set):
    kelimeler = [w for w in re.findall(r"[a-zçğıöşüA-ZÇĞİÖŞÜ]{3,}", cumle) if w.lower() in hedef_set]
    return " ".join(kelimeler[:4]) if kelimeler else None

# ——— Jev (AI Gateway üzerinden) ———
def jev_kararlar(ciftler, model, esik):
    base = os.environ.get("AI_GATEWAY_URL", "https://ai.nocturndev.com").rstrip("/")
    key = os.environ.get("AI_GATEWAY_KEY", "")
    if not key: sys.exit("AI_GATEWAY_KEY yok — ai.nocturndev.com kapısının anahtarı lazım")
    kabul, toplam, kullanim = [], 0, {"input_tokens": 0, "output_tokens": 0}
    for parca in [ciftler[i:i + 12] for i in range(0, len(ciftler), 12)]:
        state, questions = {}, {}
        for i, c in enumerate(parca):
            state[f"aday_{i}"] = (f"KAYNAK MAKALE: başlık={c['kaynak_baslik']}\n"
                                  f"İLGİLİ CÜMLE: {c['cumle'][:420]}\n"
                                  f"HEDEF SAYFA: başlık={c['hedef_baslik']} · url={c['hedef_url']}")
            questions[f"m{i}"] = {"type": "noul", "instructions":
                "aday_{i}: iki blog yazısı arasındaki internal link önerisidir. Kaynak makaleden hedef "
                "sayfaya link vermek okuyucuya GERÇEKTEN fayda sağlar mı? Aynı konuda olmak yetmez; "
                "hedef sayfa o cümlede merak edilen konuyu derinleştirmeli. 0-1 olasılık döndür."}
        body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
        req = urllib.request.Request(f"{base}/jev/v1/systemone", data=body,
            headers={"Content-Type": "application/json", "X-Gateway-Key": key,
                     "Authorization": "Bearer " + os.environ.get("AI_GATEWAY_KEY", "")}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                yanit = json.loads(r.read().decode())
        except Exception as e:
            print(f"  [jev] parça atlandı: {e}", file=sys.stderr); continue
        u = yanit.get("usage", {})
        kullanim["input_tokens"] += u.get("input_tokens", 0)
        kullanim["output_tokens"] += u.get("output_tokens", 0)
        for i, c in enumerate(parca):
            a = (yanit.get("answers") or {}).get(f"m{i}") or {}
            if a.get("type") == "noul" and isinstance(a.get("noul"), (int, float)):
                skor = min(1.0, max(0.0, float(a["noul"])))
                if skor >= esik: kabul.append({**c, "jev": skor})
        print(f"  [jev] parça: {len(parca)} aday kararlandı")
    return kabul, kullanim


# ——— Internal PageRank + Orphan tespiti ———
def pagerank_analiz(sayfalar, damping=0.85, tur=40):
    """İç link grafiği üzerinde PageRank + orphan sayfa tespiti.

    Dangling node (dışa çıkan sıfır link) kütlesi PageRank'ı çeker —
    klasik çözüm: kütle tüm düğümlere eşit dağıtılır.
    """
    # URL normalize: trailing slash uyuşmazlığı grafiği koparıyordu (29 sahte
    # orphan — gerçek vaka: blog.rust-lang.org sayfaları /'lı, linkler /'sız).
    norm = lambda u: u.rstrip("/")
    url2sayfa = {norm(s["url"]): s for s in sayfalar}
    kenarlar = {}
    for s in sayfalar:
        hedefler = set()
        for l in s["linkler"]:
            hedef = norm(l)
            if hedef in url2sayfa and hedef != norm(s["url"]):
                hedefler.add(hedef)
        kenarlar[norm(s["url"])] = sorted(hedefler)
    dugumler = [norm(s["url"]) for s in sayfalar]
    pr = {u: 1.0 / len(dugumler) for u in dugumler}
    giris = {u: 0 for u in dugumler}
    for u, hedefler in kenarlar.items():
        for h in hedefler: giris[h] += 1
    for _ in range(tur):
        damla = sum(pr[u] for u in dugumler if not kenarlar[u]) / len(dugumler)
        yeni = {u: damla + (1 - damping) / len(dugumler) for u in dugumler}
        for u in dugumler:
            if kenarlar[u]:
                pay = damping * pr[u] / len(kenarlar[u])
                for h in kenarlar[u]: yeni[h] += pay
        pr = yeni
    orfanlar = sorted(u for u in dugumler if giris[u] == 0)
    return pr, giris, orfanlar, dugumler

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site"); ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--esik", type=float, default=0.7)
    ap.add_argument("--model", default="jev-latest"); ap.add_argument("--csv", default="link-analiz.csv")
    a = ap.parse_args()
    t0 = time.time()
    urls = sitemap_adaylari(a.site, a.limit)
    print(f"sitemap: {len(urls)} sayfa bulundu")
    sayfalar = []
    for u in urls:
        try:
            s = ayristir(u, getir(u))
            if len(s["metin"]) < 200 and not u.endswith("/"):  # redirect sayfası → /'lı dene
                s = ayristir(u + "/", getir(u + "/"))
            sayfalar.append({**s, "url": s["url"]})
        except Exception as e:
            print(f"  atlandı: {u} ({str(e)[:50]})")
    print(f"sayfa: {len(sayfalar)} ayrıştırıldı")
    for s in sayfalar: s["vektor"] = vektor(s["title"] + " " + " ".join(s["basliklar"]) + " " + s["metin"][:3000])

    ciftler, gorulen = [], set()
    for i, kaynak in enumerate(sayfalar):
        adaylar = []
        for j, hedef in enumerate(sayfalar):
            if i == j: continue
            if hedef["url"] in kaynak["linkler"]: continue  # zaten link var
            benzerlik = cosine(kaynak["vektor"], hedef["vektor"])
            if benzerlik >= 0.06: adaylar.append((benzerlik, hedef))
        adaylar.sort(key=lambda x: x[0], reverse=True)
        hedef_set = set()
        for benzerlik, hedef in adaylar[:3]:
            anahtar = (kaynak["url"], hedef["url"])
            if anahtar in gorulen: continue
            hedef_set.update(tokenize(hedef["title"] + " " + " ".join(hedef["basliklar"]))[:12])
            cumle = en_iyi_cumle(kaynak["metin"], hedef_set)
            if not cumle: continue
            anchor = anchor_adayi(cumle, hedef_set)
            if not anchor: continue
            gorulen.add(anahtar)
            ciftler.append({"kaynak_url": kaynak["url"], "kaynak_baslik": kaynak["title"] or kaynak["url"],
                            "hedef_url": hedef["url"], "hedef_baslik": hedef["title"] or hedef["url"],
                            "cumle": cumle, "anchor": anchor, "benzerlik": round(benzerlik, 2)})
    print(f"aday çift: {len(ciftler)} (TF-IDF ön-filtre sonrası — Jev'e yalnız bunlar gidiyor)")
    kabul, kullanim = jev_kararlar(ciftler, a.model, a.esik)

    pr, giris, orfanlar, dugumler = pagerank_analiz(sayfalar)
    orfan_not = (f"⚠️ ORPHAN SAYFA: {len(orfanlar)} sayfanın içten linki YOK "
                 f"({', '.join(u.split('/')[-1] or u for u in orfanlar[:5])})") if orfanlar else                 "✓ orphan sayfa yok — her sayfaya içeriden en az bir link var"
    print("\n" + orfan_not)

    tarih = time.strftime("%Y-%m-%d")
    csv_yol = f"link-oneri-{a.site.replace('https://','').replace('/','_')}-{tarih}.csv"
    with open(csv_yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["kaynak_url", "hedef_url", "cümle", "anchor", "jev_skor", "benzerlik"])
        w.writeheader()
        for k in sorted(kabul, key=lambda x: -x["jev"]):
            w.writerow({"kaynak_url": k["kaynak_url"], "hedef_url": k["hedef_url"],
                        "cümle": k["cumle"], "anchor": k["anchor"],
                        "jev_skor": round(k["jev"], 2), "benzerlik": k["benzerlik"]})
    sure = round(time.time() - t0, 1)
    print(f"\n✓ KABUL EDİLEN LINK ÖNERİSİ: {len(kabul)} (aday {len(ciftler)}, eşik {a.esik})")
    for k in sorted(kabul, key=lambda x: -x["jev"])[:8]:
        print(f"  {round(k['jev'],2)}  {k['kaynak_url']} → {k['hedef_url']}")
        print(f"        anchor: {k['anchor']}")
    print(f"\nCSV: {csv_yol}")
    print(f"Jev kullanımı: {kullanim['input_tokens']} in / {kullanim['output_tokens']} out · süre {sure}s")
    pr_yol = f"pagerank-{a.site.replace('https://','').replace('/','_')}-{tarih}.csv"
    with open(pr_yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["url", "pagerank", "ic_giris", "orphan"])
        for u in sorted(dugumler, key=lambda x: -pr[x]):
            w.writerow([u, round(pr[u], 5), giris[u], "EVET" if giris[u] == 0 else ""])
    print(f"PageRank CSV: {pr_yol} (top 3: " + ", ".join(
        f"{u.split('/')[-1]} {round(pr[u],4)}" for u in sorted(dugumler, key=lambda x: -pr[x])[:3]) + ")")

if __name__ == "__main__":
    main()
