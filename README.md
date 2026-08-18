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
```

`.env.example` ga qarang. `.env` gitga commit qilinmaydi (`.gitignore` da bor).

`ELEVENLABS_API_KEY` majburiy (transkripsiya). `GEMINI_API_KEY` ixtiyoriy — usiz
`analyze.py` heuristika rejimida ishlaydi (kesim, zoom, raqam-kalit so'zlar), faqat
hook sarlavha va semantik kalit so'zlar chiqmaydi.

## CLI orqali ishlatish

```bash
# yakka enhance (audio+rang+subtitr), --compare bilan yonma-yon video ham chiqadi
.venv/bin/python enhance.py input.mp4 output.mp4 --ass output/my.ass --compare

# to'liq pipeline: Scribe -> normalize -> ASS -> enhance, bitta chaqiruvda
.venv/bin/python -c "from pipeline import run_pipeline; print(run_pipeline('input.mp4', style_name='warm_karaoke'))"
```

## API orqali ishlatish

```bash
.venv/bin/uvicorn api:app --reload
```

`http://127.0.0.1:8000/` — brauzerda ochiladigan test UI (video yukla, style
tanla, natijani ko'r).

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
| GET | `/api/settings/defaults` | standart sozlamalar |

Eski bir martalik oqim ham ishlaydi (`/process`, `/status/{id}`,
`/result/{id}`) — mavjud test UI shundan foydalanadi.

Navbat hozircha bitta ishchi bilan in-process (`ThreadPoolExecutor`). Ko'p
ishchi/qayta ishga tushganda saqlanishi kerak bo'lsa — Celery/RQ ga
o'tkaziladi (kodda `ponytail:` izohi bilan belgilangan).

## Yangi style qo'shish

`styles/*.yaml` — style = data, kod emas. Namuna uchun
`styles/warm_karaoke.yaml` ga qarang. Maydonlar: `mode` (`karaoke` yoki
`pop`), `font`/`font_bold`, `font_size`, ranglar (`[r,g,b]`), `outline_width`,
`margin_v`/`margin_h`, qatorlash (`max_words_per_line`, `max_chars_per_line`)
yoki pop animatsiyasi (`pop_duration_ms`, `pop_scale_from`).

Yangi shrift kerak bo'lsa — `fonts/` papkaga qo'shib, style yaml da
`font`/`font_bold` nomini fayl ichidagi shrift nomiga moslashtiring
(`fc-scan fonts/X.ttf | grep family` bilan tekshiring). Oʻzbek belgilar
(`ʻ`, kirill Ў/Қ/Ғ/Ҳ) borligini `fontTools` bilan tasdiqlang.

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

## Testlar

```bash
.venv/bin/python test_normalize.py        # apostrof/kod-almashish testlari
.venv/bin/python test_analyze.py          # kesim, vaqt remap, zoom oraliq
.venv/bin/python test_subtitles.py        # kalit so'z teglari, hook
.venv/bin/python test_enhance.py          # zoom ifodasi, sfx audio grafi
.venv/bin/python test_pipeline_smoke.py   # 5s sintetik klip, Scribe mock qilingan
```

## Xarajat logi

Har bir `run_pipeline()` chaqiruvi `logs/cost_log.jsonl` ga bitta qator
qo'shadi: Scribe daqiqa/narx + ffmpeg CPU soniya/narx + jami USD/UZS
(`cost.py`). UZS kursi va CPU narxi placeholder — real infratuzilma
narxlariga moslashtiring.

## Demo skriptlar (rivojlanish jarayonida yozilgan)

- `demo_milestone2.py` — normalize -> ASS -> ffmpeg burn (karaoke + pop)
- `demo_milestone3.py` — sintetik qorong'i/shovqinli klip -> enhance -> compare
- `demo_milestone4.py` — FastAPI to'liq oqim, Scribe mock qilingan

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

**Hali qurilmagan:** to'lov (Payme/Click), GPT-4o fallback, B-roll (Pexels),
emoji avtomatik qo'yish.
