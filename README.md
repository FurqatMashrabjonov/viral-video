# uzcaption

O'zbek tilidagi talking-head videolarni tozalab, rang grading qilib, so'z-so'z
animatsion subtitr bilan qaytaradigan backend (MVP).

## Setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`ffmpeg` (libass bilan) va `ffprobe` PATH da bo'lishi shart:

```bash
brew install ffmpeg   # macOS
ffmpeg -version | grep libass   # tekshirish
```

### `.env`

```
ELEVENLABS_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
PEXELS_API_KEY=your-key-here
```

`.env.example` ga qarang. `.env` gitga commit qilinmaydi (`.gitignore` da bor).

`ELEVENLABS_API_KEY` majburiy (transkripsiya). `GEMINI_API_KEY` ixtiyoriy — usiz
`analyze.py` heuristika rejimida ishlaydi (kesim, zoom, raqam-kalit so'zlar), faqat
hook sarlavha, semantik kalit so'zlar va B-roll so'rovlari chiqmaydi.
`PEXELS_API_KEY` faqat B-roll sozlamasi yoqilganda kerak (standart — o'chiq),
[pexels.com/api](https://www.pexels.com/api/) dan bepul olinadi.

## CLI orqali ishlatish

```bash
# yakka enhance (audio+rang+subtitr), --compare bilan yonma-yon video ham chiqadi
.venv/bin/python enhance.py input.mp4 output.mp4 --ass output/my.ass --compare

# to'liq pipeline: Scribe -> normalize -> ASS -> enhance, bitta chaqiruvda
.venv/bin/python -c "from pipeline import run_pipeline; print(run_pipeline('input.mp4', style_name='warm_karaoke'))"
```

## API va web UI orqali ishlatish

```bash
cd web && npm install && npm run build && cd ..
.venv/bin/uvicorn api:app --reload
```

`http://127.0.0.1:8000/` — React ilovasi (yuklash, jonli progress, sozlamalar
paneli, subtitr muharriri). Ishlab chiqishda `cd web && npm run dev` alohida
port ochadi va `/api` so'rovlarini backendga proksi qiladi (`vite.config.ts`).

Endpointlar:

| Method | Path | Vazifa |
|---|---|---|
| GET | `/api/projects` | loyihalar ro'yxati |
| POST | `/api/projects` | video yuklash + ingest, `{"project_id"}` qaytaradi |
| GET | `/api/projects/{id}` | loyiha + reja + renderlar |
| PUT | `/api/projects/{id}/plan` | tahrirlangan rejani saqlash |
| POST | `/api/projects/{id}/render` | sozlamalar bilan render, `{"render_id"}` |
| GET | `/api/renders/{id}` | holat, progress, sozlamalar |
| GET | `/api/renders/{id}/video` | tayyor video (mp4) |
| GET | `/api/schema` | sozlamalar sxemasi + standartlar |
| GET | `/api/projects/{id}/stream` | SSE: jonli bosqich va progress |
| GET | `/api/projects/{id}/events` | jurnaldagi barcha hodisalar |

Navbat hozircha bitta ishchi bilan in-process (`ThreadPoolExecutor`). Ko'p
ishchi/qayta ishga tushganda saqlanishi kerak bo'lsa — Celery/RQ ga
o'tkaziladi (kodda `ponytail:` izohi bilan belgilangan).

## Yangi style qo'shish

`styles/*.yaml` — style = data, kod emas, `settings.py` diskdan avtomatik
o'qiydi (yangi fayl qo'shilsa `GET /api/schema`da darhol paydo bo'ladi, kod
o'zgartirish shart emas). 5 ta tayyor: `warm_karaoke`, `bold_pop`,
`clean_minimal`, `hormozi`, `bold_highlight`.

Uchta rejim (`mode`):
- `karaoke` — butun ibora ko'rinadi, aytilgan so'z rang bilan to'ladi (`\k`)
- `pop` — har so'z alohida, kattalashib kiradi
- `highlight` — butun ibora ko'rinadi, aytilayotgan so'zning **foni**
  yoqiladi-o'chadi, o'z vaqtiga qadab (`subtitles.py:_highlight_tags`) — real
  render bilan tekshirilgan: ikkita so'z, ikkita mustaqil oyna, har biri faqat
  o'z vaqtida faol.

Umumiy maydonlar: `font`/`font_bold`, `font_size`, ranglar (`[r,g,b]`),
`outline_width`, `margin_v`/`margin_h`, qatorlash (`max_words_per_line`,
`max_chars_per_line`), pop animatsiyasi (`pop_duration_ms`, `pop_scale_from`),
`uppercase` (matnni KATTA HARFGA o'giradi — faqat ko'rinishda, saqlangan
so'zga tegmaydi, kalit so'z moslashtirishga ta'sir qilmaydi).

Yangi shrift kerak bo'lsa — `fonts/` papkaga qo'shib, style yaml da
`font`/`font_bold` nomini fayl ichidagi shrift nomiga moslashtiring
(`fc-scan fonts/X.ttf | grep family` bilan tekshiring). Oʻzbek belgilar
(`ʻ`, kirill Ў/Қ/Ғ/Ҳ) borligini `fontTools` bilan tasdiqlang — **Anton va
Bebas Neue bu tekshiruvdan o'tmadi** (kirill umuman yo'q, Bebas Neue’da
apostrof ham yo'q), shuning uchun `hormozi` stili o'rniga Montserrat Black
ishlatadi — bir xil og'ir/siqilgan ko'rinish, lekin to'liq oʻzbek+kirill
qamrovi bilan.

## Yangi LUT qo'shish

`tools/make_lut.py` — 3 ta placeholder warm LUT generatsiya qiladi
(`luts/*.cube`, 33³, o'z yasalgan, CC0). Qo'lda grading qilingan LUT
qo'shsangiz, faylni `luts/` ga qo'ying va `enhance.py --lut path/to.cube`
yoki `run_pipeline(..., lut_path=...)` bilan ko'rsating. Faqat CC0/o'z
LUT — litsenziyasi noaniq LUT ishlatilmaydi.

## Ikki faza: ingest va render

Transkripsiya bir marta, render cheksiz marta. Scribe marjinal xarajatning ~98%
ini yeydi, shuning uchun foydalanuvchi sozlamani o'zgartirsa yoki subtitrdagi
xatoni tuzatsa, transkripsiya **qayta ishlamasligi shart**.

```python
from pipeline import ingest, render

project_id = ingest("video.mp4")            # qimmat: Scribe + Gemini
render(project_id)                          # arzon: faqat CPU
render(project_id, {"zoom": False})         # yana arzon
render(project_id, {"style": "bold_pop"})   # yana arzon
```

Holat SQLite'da (`data/uzcaption.db`), videolar diskda (`data/media/`) —
bazaga BLOB sifatida yozilmaydi, aks holda baza fayli shishadi va videoni
oddiy range-request oqimi sifatida berish qiyinlashadi.

`test_pipeline_smoke.py` shu xususiyatni qo'riqlaydi: `ingest` bir marta
chaqiriladi, keyin ikkita render va bitta tahrirdan so'ng Scribe chaqiruvi
soni hali ham 1 bo'lishi kerak.

Xarajat logi ikkalasini alohida yozadi — `INGEST` qatorida Scribe narxi,
`RENDER` qatorida faqat CPU.

## Jonli progress (SSE)

Bosqichlar `events` jadvaliga yoziladi, xotiraga emas — brauzer render o'rtasida
uzilib qayta ulansa, o'tkazib yuborganini qayta o'qiy oladi.

```
GET /api/projects/{id}/stream    # text/event-stream
GET /api/projects/{id}/events    # o'sha jurnal, oddiy JSON
```

Har freym o'z qator `id` sini olib yuradi. Brauzer qayta ulanganda uni
`Last-Event-ID` sarlavhasida qaytaradi va oqim aynan o'sha joydan davom etadi —
teshik qolmaydi.

**Nega SSE, WebSocket emas:** progress faqat serverdan klientga oqadi.
WebSocket hech kim ishlatmaydigan qaytish kanalini qo'shadi.

Bosqichlar: `probe → audio → transcribe → plan → enrich → ready →
subtitles → render → done`. `ready` oqimni yopmaydi — u ingest'ni tugatadi,
lekin keyin render keladi va klient hali kuzatib turibdi.

ffmpeg progressi soniyasiga bir necha marta keladi; jurnalga har 5% da bitta
qator yoziladi, aks holda bosqich qatorlari ko'milib ketardi.

## Sozlamalar (`settings.py`)

Foydalanuvchi boshqaradigan har bir narsa **bitta joyda** e'lon qilinadi:
`settings.py`. `GET /api/schema` uni JSON sifatida beradi, frontend shundan
boshqaruvlarni chizadi. Ikkinchi ro'yxat yuritilsa, u albatta uzoqlashadi va
natija "tugma bor, lekin hech nimaga ta'sir qilmaydi" bo'ladi.

21 maydon, 6 guruh: Subtitr, Hook, Zoom, Effekt, Rang, Audio.

`merge()` — ishonch chegarasi. Qiymatlar HTTP orqali keladi va ffmpeg filter
grafiga tushadi, shuning uchun: raqamlar e'lon qilingan oraliqqa qisiladi,
select faqat diskda mavjud faylni nomlashi mumkin, notanish kalitlar tashlab
yuboriladi.

Maydon bu yerga faqat render uni **haqiqatan qo'llaganda** qo'shiladi.
`cut_silence` ataylab yo'q — `analyze.py` kesimlarni hisoblay oladi, lekin
`enhance.py` ularni qo'llamaydi.

Zoom va sfx joylashuvi so'zlarning sof funksiyasi, shuning uchun render paytida
joriy sozlamalardan **qayta hisoblanadi** — oraliqni o'zgartirish Scribe'ga
qaytishni talab qilmaydi.

## Edit plan (`analyze.py`)

Scribe so'z vaqtlaridan tahrir rejasini quradi — render'dan **oldin** ko'z bilan
tekshirish mumkin bo'lgan JSON:

```python
from analyze import build_edit_plan, llm_enrich, save_plan
plan = build_edit_plan(words, source_duration=90.0)
plan = llm_enrich(plan)          # ixtiyoriy: hook + semantik kalit so'zlar
save_plan(plan, "output/edit_plan.json")
```

Reja tarkibi: `cuts` (jimlik kesimlari), `words` (kesilgan timeline'ga
ko'chirilgan, `keyword` bayrog'i bilan), `zooms`, `hook`.

Jimlik alohida `silencedetect` passisiz aniqlanadi — Scribe'ning so'z vaqtlari
orasidagi bo'shliq ta'rifi bo'yicha jimlik. Kesim timeline'ni qisqartirgani uchun
har bir so'z vaqti qayta hisoblanadi (`remap_time`); bu yerdagi xato subtitrni
butun videoda siljitadi, shuning uchun `test_analyze.py` shu matematikani
alohida qamrab oladi.

## Sound effect qo'shish

`tools/make_sfx.py` uchta effekt generatsiya qiladi (`sfx/pop.wav`, `whoosh.wav`,
`ding.wav`) — ffmpeg sintezidan, o'z yasalgan, CC0. Har biri ikki bosqichda
quriladi: avval render, keyin cho'qqi o'lchanadi va **-6 dB** ga normalizatsiya
qilinadi, aks holda sintezlar 20 dB dan ortiq farq qiladi va bitta effektga
sozlangan miks darajasi qolganlarini eshitilmas qiladi. Shovqin manbasiga
`seed` berilgan, shuning uchun build takrorlanuvchan.

Effektlar `analyze.py` belgilagan kalit so'zlarga tushadi: raqamga `ding`,
qolganiga `pop`, kamida 1.5 soniya oraliq bilan. Miks darajasi
`enhance.SFX_VOLUME` (standart 0.35). O'chirish: `run_pipeline(..., sfx=False)`.

## B-roll (`pexels.py`)

Standart **o'chiq** — sifat riski borligi sababli (foydalanuvchi ongli
ravishda yoqadi, `settings.broll`).

Gemini transkriptdagi aniq, ko'rgazmali tushunchalarni (masalan "ofisda
uchrashuv", "mashinada shahar bo'ylab") topib, har biriga inglizcha 1-3 so'zlik
qidiruv so'rovi yozadi (`broll_spans`). Render paytida `pexels.py` shu so'rov
bilan Pexels'dan klip qidiradi, eng yaqin aspekt nisbatli va 800px dan
past renditsiyani tanlaydi (2-3 soniyalik overlay uchun 4K shart emas), va
video ustiga **PiP** sifatida qo'yadi — kadr balandligining yuqori 58% qismida,
pastda prezenter va subtitr zonasi ochiq qoladi. Hech qachon to'liq ekran emas.

B-roll'ga asosiy videoning **o'zi LUT'i, o'zi kuchida** qo'llaniladi — rang
mos kelishi uchun. Ko'rsatish davomiyligi qat'iy qisqa (`BROLL_DISPLAY_SECONDS`,
standart 1.6s) — zoom'dan farqli, gap davomiyligiga cho'zilmaydi, chunki bu
tez urg'u ("flash"), diqqatni tortish emas. Soni video uzunligiga qarab
cheklanadi (`broll_max_per_min`, standart 2.5/daqiqa).

Ikki qatlamli kesh: qidiruv natijasi (`data/broll_cache/search_*.json`,
24 soat TTL) va yuklangan fayl (`data/broll_cache/clip_*.mp4`, muddatsiz,
URL xeshi bilan) — bir xil so'rov qayta render'da qayta yuklanmaydi.
Pexels topilmasa yoki API xato bersa, o'sha B-roll jimgina o'tkazib
yuboriladi — butun render yiqilmaydi.

## Testlar

```bash
.venv/bin/python test_normalize.py        # apostrof/kod-almashish testlari
.venv/bin/python test_analyze.py          # kesim, vaqt remap, zoom oraliq
.venv/bin/python test_subtitles.py        # kalit so'z teglari, hook
.venv/bin/python test_enhance.py          # zoom ifodasi, sfx audio grafi, broll PiP grafi
.venv/bin/python test_pexels.py           # renditsiya tanlash, kesh yo'llari (tarmoqsiz)
.venv/bin/python test_settings.py         # sxema butunligi, qiymat validatsiyasi
.venv/bin/python test_events.py           # hodisa jurnali, SSE qayta ulanish
.venv/bin/python test_pipeline_smoke.py   # 5s sintetik klip, Scribe mock qilingan
```

## Xarajat logi

Har bir `run_pipeline()` chaqiruvi `logs/cost_log.jsonl` ga bitta qator
qo'shadi: Scribe daqiqa/narx + ffmpeg CPU soniya/narx + jami USD/UZS
(`cost.py`). UZS kursi va CPU narxi placeholder — real infratuzilma
narxlariga moslashtiring.

## Docker

```bash
cp .env.example .env   # kalitlarni to'ldiring
docker compose up --build
```

Ikki bosqichli image: `web` bosqichi React bundle'ni quradi (Node yakuniy
image'da qolmaydi), `api` bosqichi ffmpeg+libass+shriftlar bilan uni beradi.
SQLite va media `data` nomli hajmda — konteyner qayta qurilsa ham saqlanadi.

## Nima qurilmagan (backlog)

**Ataylab chiqarilgan:**

- **Face tracking / auto-reframe** — kirish allaqachon kadrlangan 9:16, yuz
  markazda. Face tracking 16:9 ni 9:16 ga qayta kadrlash uchun mavjud; bizda
  yo'q muammoni hal qilgan bo'lardi. Markazga tortilgan punch-in zoom o'rnini
  bosadi.
- **GPU yoritish / matting** (BiRefNet, RVM) — GPU worker tier talab qiladi va
  qisqa video trendi haddan pardozlangan ko'rinishdan uzoqlashmoqda.
- **Uzun videodan shorts kesish**, **AI avatar / ovoz klonlash** — boshqa
  mahsulot.
- **Jimlik va filler so'z kesish** — `analyze.py` kesimlarni hisoblay oladi
  (`cut_silence=True`) va vaqt remap testlar bilan qoplangan, lekin render
  ularni qo'llamaydi va pipeline'da o'chiq.

**Hali qurilmagan:** to'lov (Payme/Click), GPT-4o fallback.
