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
6. CSV + özet + maliyet (token kullanımı)

## Dersler
- nav/header/footer metni makaleye karışınca anchor'lar çöker → HTMLParser
  nav-atlaması şart
- trailing-slash redirect sayfaları (sitemap URL'siz) → /'lı tekrar dene
- openssl 3.x `NotAfter:` (1.x `notAfter=` değil) — nöbet toplayıcı için

MIT
