# nocturn-linkanaliz

**Jev destekli internal link analiz aracı** — sitemap topla, TF-IDF ile süz,
Jev'e yalnız semantik kararı sor, CSV/markdown raporla.

Mimari: `CODE → adayları bul · JEV → karar ver · CODE → uygula`
("Jev refleks, LLM beyin" — her şeyi AI'a yaptırmak yerine:
kod adayları bulur, LLM yalnız anlam gerektiren kararı verir.)

## Kullanım

```bash
export AI_GATEWAY_KEY=...      # ai.nocturndev.com kapısı
python3 linkanaliz.py https://blog.ornek.com --limit 30 --esik 0.6
```

Çıktı: `link-oneri-<site>-<tarih>.csv` — kaynak, hedef, cümle, anchor, skor.

## Nasıl çalışır

1. robots.txt + sitemap → makaleler
2. Her sayfadan title/H1-H3/gövde + mevcut internal linkler
3. TF-IDF cosine → benzer makale çiftleri önceden süzülür (LLM'e n×n gitmez!)
4. Kaynak makalede hedef konuyla ilgili en iyi cümle + anchor adayı
5. **Jev**: "bu link gerçekten faydalı mı?" 0-1 → eşik üstü kabul
6. **Internal PageRank** + **orphan page tespiti** (kimse link vermemiş sayfalar) + CSV
7. Jev kabul edilen öneriler, orphan sayfaları düzeltir — döngü kapanır

## Dersler
- nav/header/footer metni makaleye karışınca anchor'lar çöker → HTMLParser
  nav-atlaması şart
- trailing-slash redirect sayfaları (sitemap URL'siz) → /'lı tekrar dene
- openssl 3.x `NotAfter:` (1.x `notAfter=` değil) — nöbet toplayıcı için

MIT

## Canlı doğrulama (blog.rust-lang.org, 30 sayfa)

```
aday çift: 90 (TF-IDF ön-filtre — 870 karşılaştırma yerine)
Jev kararları: 7 toplu çağrı · 21.9k in / 1.5k out token · 8 saniye
kabul: 7 link önerisi · ORPHAN: 29 sayfa tespit edildi
PageRank top: 1.0-Timeline 0.37 · Rust-1.0 0.20
```
