# HVAC Calculator — Foydalanuvchi qo'llanmasi (O'zbekcha)

Issiqlik yo'qotishlari, issiqlik kirimi, ventilyatsiya, **tutun chiqarib
yuborish**, **havo bosimi (СПВ)**, **issiq suv ta'minoti (ГВС)**,
**energetik pasport**, **havo o'tkazgich va isitish quvurlarini
tanlash**, **shudring nuqtasini tekshirish** uchun Revit ma'lumotlari
asosida hisoblash dasturi.

**Me'yoriy hujjatlar:** СП 50.13330, СП 60.13330, СП 7.13130, СП 30.13330,
СП 131.13330, **КМК 2.04.05-22 (O'zbekiston)**, NFPA 92 (AQSh).

---

## Mundarija

1. [O'rnatish va ishga tushirish](#1-ornatish-va-ishga-tushirish)
2. [Umumiy ish jarayoni](#2-umumiy-ish-jarayoni)
3. [Tablar bo'yicha qadamlar](#3-tablar-boyicha-qadamlar)
4. [Tutun chiqarish — me'yor tanlash](#4-tutun-chiqarish--meyor-tanlash)
5. [Excel va PDF eksport](#5-excel-va-pdf-eksport)
6. [Tipik xatolar va ularning yechimi](#6-tipik-xatolar-va-ularning-yechimi)
7. [O'zbekiston uchun tavsiya etilgan sozlamalar](#7-ozbekiston-uchun-tavsiya-etilgan-sozlamalar)
8. [Tezkor klaviatura yorliqlari](#8-tezkor-klaviatura-yorliqlari)

---

## 1. O'rnatish va ishga tushirish

### Kerakli dasturlar

- **Python 3.10 yoki yangiroq**
- **Revit 2024+** (geometriyani eksport qilish uchun)
- **Dynamo** (Revit ichidagi skript ishga tushirish uchun)

### Kutubxonalarni o'rnatish

Buyruqlar satrida (CMD yoki PowerShell):

```bash
pip install -r requirements.txt
# yoki qo'lda:
pip install PySide6 matplotlib openpyxl reportlab python-docx
```

| Kutubxona     | Vazifasi                          | Majburiymi |
|---------------|-----------------------------------|------------|
| PySide6       | GUI (Qt6) — oyna rejimi uchun     | Ha         |
| matplotlib    | Grafiklar (10-tab), i-d diagramma | Ha         |
| openpyxl      | Excelga eksport (14 varaq)        | Ha         |
| reportlab     | PDF hisoboti                      | Ha         |
| python-docx   | Word (.docx) eksporti             | Ha         |

Ishlab chiqish vositalari (`pytest`, `ruff`, `mypy`) — `requirements-dev.txt`
faylida, dasturni ishlatish uchun kerak emas.

### Dasturni ishga tushirish

**GUI rejimida (tavsiya etiladi):**
```bash
python hvac_calc.py
```

**Buyruqlar satridan (CLI):**
```bash
python hvac_calc.py cli spaces.csv thermal_all.csv natija.xlsx -15 36 "Toshkent"
```

Argumentlar:
- `spaces.csv` — xonalar ro'yxati
- `thermal_all.csv` — tashqi to'siqlar (devorlar, oynalar)
- `natija.xlsx` — chiqish fayli
- `-15` — qishki tashqi harorat, °C
- `36` — yozgi tashqi harorat, °C
- `"Toshkent"` — shahar nomi (iqlim ma'lumotlari avto-yuklanadi)

---

## 2. Umumiy ish jarayoni

Loyiha bo'yicha bir marta hisoblash sikli:

```
Revit → CSV ← (Dynamo)
              ↓
        Dastur (11 ta tab)
              ↓
   ┌──────────┼──────────┐
   ↓          ↓          ↓
 Excel      PDF       Revit
(14 list) (12 bo'lim) (CSV)
```

**Asosiy bosqichlar:**

1. **Revit'dan ma'lumotlar olish.** Dynamo skripti
   `revit_dynamo_hvac_write_csv.py` ishlatiladi → 2 ta CSV fayl chiqadi.
2. **Dasturga yuklash** va tablar bo'yicha bosqichma-bosqich ishlash.
3. **Hisoblash natijalari** Excel, PDF yoki CSV (Revit'ga qaytarish) sifatida eksport qilinadi.

---

## 3. Tablar bo'yicha qadamlar

Asosiy oynada 11 ta tab mavjud. Har bir tab oldingi tab natijalariga
asoslanadi — tartibni buzmang.

### Tab 1. Ma'lumotlar (Данные)

- `spaces.csv` va `thermal_all.csv` fayllarining yo'lini ko'rsating
- **«Загрузить CSV»** tugmasini bosing
- **«🔍 Проверить данные…»** — ogohlantirishlarni ko'ring (maydon = 0,
  hajm = 0, va boshqalar)

### Tab 2. Parametrlar (Параметры)

- **Shahar** ro'yxatidan tanlang → iqlim avtomatik to'ldiriladi (85 ta MDH shahri)
- O'zbekiston shaharlari uchun: Toshkent, Samarqand, Buxoro, Andijon, Namangan va boshqalar
- Quyidagilarni tekshiring/o'zgartiring:
  - `t_out_heating` (qishki tashqi harorat)
  - `t_out_cooling` (yozgi tashqi harorat)
  - `solar_intensity_w_m2` (quyosh intensivligi)
  - `wwr_estimate` — agar Revit'dan oynalar to'liq chiqmagan bo'lsa, devorga
    «virtual oyna» qo'shiladi (0.4 — oddiy bino, 0.6 — vitrajli ofis)
  - `solar_shading_factor` (1.0 — soyabonsiz, 0.7 — ichki jalyuzi, 0.5 — tashqi)
  - **Yangi:** `smoke_norm` — tutun chiqarish me'yori (4-bo'limga qarang)

### Tab 3. Konstruksiyalar (Конструкции)

Dastur barcha devor/oyna/vitraj turlarini avtomatik to'playdi.

Har bir tur uchun:
- **U** (issiqlik o'tkazuvchanligi), Vt/(m²·K)
- **SHGC** (quyosh issiqligi yutilishi), faqat shaffof toʻsiqlar uchun

**Zamonaviy bino uchun me'yorlar (Toshkent):**

| Tur          | U, Vt/(m²·K) | SHGC | Izoh                          |
|--------------|--------------|------|-------------------------------|
| Devor        | 0.4          | —    | Mineral pista 100 mm bilan    |
| Oyna         | 1.6          | 0.40 | Oddiy 2-kamerali              |
| Vitraj Low-E | 1.8          | 0.30 | Tropik iqlim uchun muhim      |
| Yopiq tom    | 0.3          | —    | 200 mm pista                  |
| Yer ustidagi yotgan polt   | 0.4 | —    | Polistirol 100 mm bilan       |

### Tab 4. Xonalar (Помещения)

- Dastur xona turini avtomatik aniqlaydi (Ofis, Avtoturargoh, Sanuzel...)
- **Ikki marta bosish** — bitta xonani tahrirlash
- **Ctrl+bosish** — bir nechta xonani belgilash va ommaviy tahrirlash

**Tekshirish kerak:**
- Yer osti xonalari `has_floor_to_ground=True` belgilangan
  (B1/B2 darajalari uchun avto)
- Eng yuqori qavat `has_roof=True`
- Burchak xonalari ajratib ko'rsatilgan

### Tab 5. Hisoblash (Расчёт)

- **«▶ Рассчитать»** tugmasini bosing
- Natijalar jadvalida bo'limlar:
  - To'siqlardan
  - Quyosh
  - Odamlar
  - Yoritish
  - Jihozlar
  - Ventilyatsiya
  - **Sensible** (sezilarli issiqlik)
  - **Latent** (yashirin issiqlik, namlik)
  - **JAMI**
  - **Solishtirma Vt/m²**

### Tab 6. Ventilyatsiya (Вентиляция)

- **«▶ Рассчитать вентиляцию»** — har bir xona uchun:
  - **Supply** (kirish havosi)
  - **Exhaust** (chiqish havosi)
  - **Hood** (oshxona ko'rgazmasi)
- Qo'lda tahrirlash mumkin — sariq rangda belgilangan xonalar
  qayta hisoblanmaydi

**Me'yorlar:**
- Ofislar: СП 60.13330 → 60 m³/soat/odam
- Mehmonxonalar: СП 44 → 60 m³/soat/odam yoki 3 ach
- Avtoturargohlar: СП 113 → 150 m³/soat/avtomobil

### Tab 7. Zonalar va tizimlar (Зоны)

- **«Авто-присвоение»** — xonalar zona bo'yicha avtomatik guruhlanadi:
  - `by_prefix` — xona raqami prefiksi bo'yicha (B01-001 → «Блок B01»)
  - `by_level` — qavat bo'yicha
  - `by_type_family` — xona turi bo'yicha (Ofis, Mehmonxona, Avtoturargoh...)
- Ommaviy belgilash: xonalarni belgilang → zona nomi kiriting → **«Применить»**
- O'ng panel — har bir zona uchun **AHU/qozon/chiller tavsiyaviy o'lchami**

### Tab 8. Jihozlar (Оборудование)

Har bir tizim uchun individual parametrlar:

- **Havo tayyorlash qurilmalari (AHU):**
  - Rekuperator KPD (yozgi/qishki)
  - Berish harorati
  - Namlik darajasi
- **Qozonlar:**
  - Turi (kondensatsion / oddiy)
  - Berish harorati
  - KPD
- **Chillerlar:**
  - Turi (havoli / suvli)
  - Hladoxlat harorati
  - COP

**«Рассчитать нагрузки от AHU»** — rekuperatsiyani hisobga olgan holda
har bir AHU uchun isitgich va sovitgich quvvati hisoblanadi.

### Tab 9. Issiq suv ta'minoti (ГВС)

СП 30.13330 bo'yicha:
- Sutkalik suv sarfi, V_sut
- Cho'qqi soatlik issiqlik yuki, Q_peak
- Suv qiziturgichning quvvati
- Bak hajmi

3 ta strategiya: yagona tizim, xona turi bo'yicha, zona bo'yicha.

### Tab 10. Grafiklar (Графики)

8 ta grafik turi:
- Qavatlar bo'yicha taqsimlanish
- Xona turlari bo'yicha
- Issiqlik nagruzkasining bo'limlari
- Heat map (qavat reja)
- U-qiymatlar taqsimlanishi
- va hokazo

### Tab 11. Tutun chiqarish va havo bosimi (Дымоудаление)

**Eng muhim qism — keyingi bo'limga qarang.**

---

## 4. Tutun chiqarish — me'yor tanlash

### Mavjud me'yoriy hujjatlar

11-tab yuqorisida **«Действующий норматив»** ro'yxati. To'rt variant:

| Kod        | Hujjat                      | Asosiy uslub          |
|------------|------------------------------|------------------------|
| `SP7_RU`   | СП 7.13130.2013 (RF)         | Soddalashtirilgan: m³/soat·m² |
| `KMK_UZ`   | **КМК 2.04.05-22 (O'zbekiston)** | Plyum formulasi (ilova 20) |
| `NFPA_92`  | NFPA 92 (AQSh, 2018)         | Axisymmetric plume      |
| `CUSTOM`   | Foydalanuvchi profili       | СП 7 nusxasi, qo'lda tahrirlash |

Tanlangan me'yor butun loyihaga ta'sir qiladi:
- Avto-tayinlashda dastlabki qiymatlar ushbu me'yordan olinadi
- Qo'lda tizim yaratishda mavjud `calc_method` ro'yxati cheklanadi
- PDF hisoboti me'yor nomini ko'rsatadi

### Hisoblash usullari

Har bir tizim uchun bittasi tanlanadi:

#### `norm_per_m2` — soddalashtirilgan
```
L = maydon × me'yor (m³/soat·m²)
```
Tezkor baholash uchun. СП 7 amaliyotidan kelib chiqqan.

| Xona turi              | СП 7 RF | КМК UZ | NFPA |
|------------------------|---------|--------|------|
| Yopiq yer osti turargohi | 24      | 24     | 9    |
| Ochiq yer osti turargohi | 18      | 18     | 9    |
| Past xavfli ombor       | 50      | 50     | 27   |
| Yuqori xavfli ombor     | 100     | 100    | 54   |
| Yo'lak                 | 60      | 60     | 18   |
| Savdo zali             | 60      | 60     | 36   |

#### `kmk_zone_perimeter` — КМК ilova 20, formula (3)
```
G = 676.8 × P × y^1.5 × Ks   [kg/soat]
```
- **P** — yong'in maydoni perimetri, m (maksimal 12 m)
- **y** — pol va tutun qatlami orasidagi balandlik, m (minimal 2.5 m)
- **Ks** — sprinklerli (1.2) yoki sprinklersiz (1.0)

Misol: P=12, y=2.5, Ks=1 → G ≈ 32 100 kg/soat ≈ 52 000 m³/soat (300°C da)

#### `kmk_corridor` — КМК ilova 20, formula (1)/(2)
```
G1 = 3420 × n^1.5                    (oddiy)
G1 = 4300 × n^1.5 × Kd               (eshikli)
```
- **n** — me'yoriy koeffitsient: 0.6 / 0.9 / 1.2 / 1.8 / 2.4
- **Kd** — eshik tuzilishi koeffitsienti

#### `nfpa_plume_axi` — NFPA 92 punkt 5.5.1
```
zl = 0.166 × Qc^(2/5)                (cheklovchi balandlik)
z > zl:  m = 0.071 × Qc^(1/3) × z^(5/3) + 0.0018 × Qc   [kg/s]
z ≤ zl:  m = 0.032 × Qc^(3/5) × z                        [kg/s]
```
- **Q** — yong'in quvvati, kVt
- **Qc** = α × Q — konvektiv komponenti (odatda α = 0.7)
- **z** — yong'in markazidan tutun qatlamigacha balandlik, m

#### `manual` — qo'lda kiritish
L_smoke_m3h maydoniga to'g'ridan-to'g'ri raqam kiritiladi.

### Tizim yaratish

#### A. Avto-tayinlash

**«▶ Авто-присвоение систем»** tugmasi:
- Avtoturargohlar → СДУ (m³/soat·m² me'yori bilan)
- Omborlar → СДУ
- Yo'laklar (uzunligi > 15 m) → СДУ
- Zinapoyalar → СПВ (bosim 20 Pa)
- Liftlar → СПВ

Tashlanma qiymatlar tanlangan me'yordan olinadi.

#### B. Qo'lda yaratish

**«+ Создать систему вручную…»** tugmasi:

1. **Nom** (yagona) — masalan, `СДУ-AT1`
2. **Tizim turi:** `smoke_removal` (chiqish) yoki `air_supply` (bosim)
3. **Maqsadi:** avtoturargoh, ombor, yo'lak, atriy, savdo zali,
   zinapoya, lift, tambur-shlyuz, MGN xavfsizlik zonasi
4. **Hisoblash usuli** — ro'yxat tanlangan me'yorga qarab cheklangan
5. Tanlangan usulga mos maydonlar dinamik ko'rsatiladi:
   - `norm_per_m2` → faqat `norma, m³/soat·m²` va `maks. zona maydoni`
   - `kmk_zone_perimeter` → P, y, Ks
   - `nfpa_plume_axi` → Q, z, α
6. **«Создать»** tugmasini bosing

#### C. Xonalarni tizimga bog'lash

**«🚪 Помещения и назначения…»** tugmasi:

- Xonalar jadvali ochiladi
- Belgilang (Ctrl+bosish bilan bir nechtasini)
- Tizimni tanlang → **«Назначить»**

### Hisoblash

Sahifa pastida:
- **«Один пожар в одной зоне»** — standart variant (har bir СДУ uchun
  bitta dudli zonadagi sarf)
- **«Несколько зон одновременно»** — zaxira hisoblash (barcha zonalar yig'indisi)

Jadvalda har bir tizim uchun:
- **L zona** — bitta dudli zonadagi sarf, m³/soat
- **L sist.** — butun tizimning sarfi, m³/soat
- **L kompens.** — kompensatsiya havosi sarfi (70-85%)
- **Olov chidamliligi** — ventilyator klassi (F400-120 va h.k.)

---

## 5. Excel va PDF eksport

### Excel (14 ta sahifa)

**Меню «Файл → Экспорт в Excel»** yoki Ctrl+E

| Sahifa                  | Tarkib                                      |
|--------------------------|----------------------------------------------|
| Parametrlar              | Loyiha sozlamalari                          |
| Konstruksiyalar          | U va SHGC qiymatlari                        |
| Issiqlik yo'qotishi      | Xonalar bo'yicha bo'lim                     |
| Issiqlik kirimi          | Sensible / Latent                           |
| To'siqlar                | Har bir tashqi devor/oyna                   |
| Ventilyatsiya            | Supply / Exhaust / Hood                     |
| **Tutun chiqarish**     | СДУ va СПВ jadvallari                       |
| **Issiq suv (ГВС)**     | Sutkalik / cho'qqi yuki                     |
| **Energopassport**       | Yillik iste'mol va sinf (A++…E)             |
| **Shudring nuqtasi**     | Konstruksiyalar bo'yicha tekshiruv          |
| **Havo o'tkazgichlari** | Diametr / o'lcham, bosim yo'qotishi         |
| **Isitish quvurlari**   | DN, tezlik, bosim                           |
| Qavatlar bo'yicha xulosa | Yig'indi statistika                         |
| Tekshiruv               | Avtomatik diagnostika xabarlar              |

### PDF (12 ta bo'lim)

**Меню «Файл → Экспорт в PDF»**

PDF — tushuntirish yozuvi kabi tugatilgan hujjat:

1. **Muqova** — loyiha nomi, sana, shahar
2. **Kirish ma'lumotlari** — iqlim, qabul qilingan me'yorlar
3. **Konstruksiyalar** — U va SHGC katalogi
4. **Issiqlik yo'qotishi** — to'liq jadval
5. **Issiqlik kirimi** — Sensible / Latent ajratilgan holda
6. **Ventilyatsiya** — sarflar
7. **Issiq suv ta'minoti**
8. **Tutun chiqarish va havo bosimi** — **faol me'yorga havola bilan!**
   - Me'yorning to'liq nomi va bobi
   - Har bir tizim uchun hisoblash usuli va kirish parametrlari
   - Plyum-formulalar uchun (КМК / NFPA) — P, y, Ks yoki Q, z, α
9. **Havo o'tkazgichlari**
10. **Isitish quvurlari**
11. **Energopasport**
12. **Shudring nuqtasi tekshiruvi**

PDF kirill alifbosini DejaVu shrifti bilan to'g'ri qo'llaydi.

### Revit'ga qaytarish

**Меню «Файл → Экспорт для Revit»**

CSV fayli chiqadi. Uni Dynamo orqali `revit_dynamo_apply_results.py`
skripti yordamida Revit'ga yuklab, har bir Space ichiga isitish/sovutish
yuki yozilishi mumkin.

---

## 6. Tipik xatolar va ularning yechimi

### «CSV yuklanmadi»

**Sabab:** Excel CSV fayli BOM yoki noto'g'ri kodlash bilan saqlangan.
**Yechim:** Excel'da → **«Save as»** → **«CSV UTF-8»** ni tanlang.

### Hisoblash bahosi noto'g'ri (Q juda yuqori yoki past)

**Tekshirilsin:**
1. U-qiymatlar konstruksiyalar tabida to'g'ri kiritilganmi?
2. Vitrazh SHGC = 0 emasmi? (agar 0 bo'lsa, quyosh hisobga olinmaydi)
3. `wwr_estimate` bekor qilinmaganmi? (Revit'dan oynalar chiqqan
   bo'lsa, 0 qiling)
4. **«🔍 Проверить данные…»** tugmasi ogohlantirishlarni ko'rsatadi

### Hatto kichik xonada juda katta ventilyatsiya sarfi

**Sabab:** xona turi noto'g'ri aniqlangan (masalan, «Tibbiyot
operatsion bloki» bo'lib ko'rinmoqda).

**Yechim:** Tab 4 → xonani toping → ikki marta bosing → to'g'ri turini
tanlang.

### Tutun chiqarishda sarflar haddan tashqari katta (NFPA bilan)

**Sabab:** NFPA me'yorida `Q = 5000 kVt` (5 MVt) yong'in odatdagidek
gigant savdo markazlari uchundir.

**Yechim:** Tab 11 → tizimni ikki marta bosing → `Q` ni kichraytiring:
- Ofis ≈ 1000-2000 kVt
- Yo'lak ≈ 500 kVt
- Avtoturargoh ≈ 4000 kVt (yonib turgan avtomobil)

### PDF reportlab xatosi

**Yechim:**
```bash
pip install --upgrade reportlab
```

---

## 7. O'zbekiston uchun tavsiya etilgan sozlamalar

### Iqlim parametrlari (Toshkent)

```python
project.params.apply_city("Ташкент")
# Avtomatik qo'yiladi:
#   t_out_heating = -15°C
#   t_out_cooling = 36°C
#   solar_intensity = 750 Vt/m²
#   gsop_18 = 2300 °C·sutka

# Toshkent uchun maxsus qo'shimchalar:
project.params.w_out_summer_g_kg = 7.0         # quruq iqlim
project.params.solar_shading_factor = 0.8       # ichki jalyuzi
project.params.wwr_estimate = 0.6                # vitraj baholanishi
```

### Tutun chiqarish (asosiy element)

```python
# КМК me'yorini tanlash
project.params.smoke_norm = "KMK_UZ"

# Avtoturargohlar uchun СДУ va zinapoyalar uchun СПВ
project.auto_assign_smoke_systems()

# Atriy uchun aniq КМК formulasi
project.create_smoke_system_manual(
    name="СДУ-ATRIY",
    system_type="smoke_removal",
    purpose="atrium",
    calc_method="kmk_zone_perimeter",
    fire_perimeter_m=12.0,    # maksimal qiymat
    layer_height_m=4.0,       # atriy uchun balandroq
    ks_sprinkler=1.2,         # sprinklerlari bor
    t_smoke_C=300.0,
)
```

### Konstruksiyalar (zamonaviy bino)

| Element        | U-qiymat (Vt/m²·K) | SHGC | Izoh                  |
|----------------|-------------------|------|------------------------|
| Tashqi devor   | 0.35-0.45          | —    | Mineral pista 100 mm    |
| Tomi           | 0.25-0.30          | —    | 200 mm pista            |
| Yer ostidagi pol| 0.30-0.40          | —    | Polistirol 100 mm       |
| Oyna           | 1.5-1.8            | 0.40 | 2-kamerali Low-E        |
| Vitraj         | 1.8-2.2            | 0.30 | Selektiv Low-E (muhim!) |
| Tashqi eshik   | 1.8-2.5            | —    | Metall-plastik          |

### Toshkent uchun tipik nagruzkalar

Ofis bino, 5000 m², zamonaviy texnologiyalar:

| Ko'rsatkich         | Qiymat               |
|---------------------|----------------------|
| Q isitish           | 120-150 kVt (24-30 Vt/m²) |
| Q sovutish          | 250-350 kVt (50-70 Vt/m²) |
| Σ Supply ventilyatsiya | 15 000-20 000 m³/soat |
| Σ СДУ avtoturargoh | 30 000-50 000 m³/soat  |
| Σ СПВ zinapoyalar  | 8 000-16 000 m³/soat (har biri 8000) |

---

## 8. Tezkor klaviatura yorliqlari

| Yorliq            | Vazifa                              |
|-------------------|-------------------------------------|
| Ctrl + S          | Loyihani saqlash (JSON)             |
| Ctrl + O          | Loyihani ochish                     |
| Ctrl + E          | Excel'ga eksport                    |
| Ctrl + P          | PDF'ga eksport                      |
| Ctrl + Tab        | Keyingi tab                         |
| Ctrl + Shift + Tab| Oldingi tab                         |
| F5                | Joriy tabni qayta hisoblash         |

Xonalar jadvalida:
| Yorliq            | Vazifa                              |
|-------------------|-------------------------------------|
| Ikki marta bosish | Xonani tahrirlash                   |
| Ctrl + bosish     | Bir nechta xonani belgilash         |
| Shift + bosish    | Diapazonni belgilash                |
| Delete            | Belgilangan xonani o'chirish (qo'l ravishda)|

---

## Qo'shimcha materiallar

- **README.md** — qisqacha umumiy ma'lumot (rus tilida)
- **USER_GUIDE.md** — to'liq qo'llanma (rus tilida)
- **ARCHITECTURE.md** — dastur arxitekturasi (dasturchilar uchun)

### Bog'lanish

Dastur loyiha uchun yaratilgan. Yangi funksiyalar, xatolar haqida —
GitHub Issues yoki to'g'ridan-to'g'ri muallifga.

### Litsenziya

Dastur **«MEN ISHLATAMAN, BAJARILGAN ISH UCHUN MEN JAVOBGAR»** rejimida.
Natijalar har doim **tipik xonada qo'lda** tekshirilishi kerak.

---

## Yangi loyiha uchun nazorat ro'yxati

- [ ] Revit modelida barcha qavatlarda Spaces/Rooms mavjud
- [ ] Curtain Walls'da Room Bounding = True
- [ ] Dynamo skript yangilangan
- [ ] CSV fayllari eksport qilingan (barcha qavatlar bor)
- [ ] Dasturda: yuklash → parametrlar → konstruksiyalar → hisoblash
- [ ] Excel'da «Проверки» varag'i ochilgan — ogohlantirishlar tahlil qilingan
- [ ] Solishtirma nagruzkalar me'yoriy diapazonda
  (isitish 20–60 Vt/m², sovutish 30–150 Vt/m² yer osti uchun va
  80–200 Vt/m² ofislar uchun)
- [ ] Zonalar belgilangan, jihozlar sozlangan
- [ ] Mehmonxona/savdo bo'lsa — AHU nagruzkalari hisoblangan
- [ ] **Tutun chiqarish me'yori tanlangan** (Tab 11 yuqorida)
- [ ] Yer osti qismlarida СДУ va zinapoyalarda СПВ avto-tayinlangan
- [ ] PDF hisobot tayyor

Muvaffaqiyatli ish!

---

**Dastur versiyasi:** 3.7+ (tutun me'yorlari tanlash bilan)
**Hujjat versiyasi:** v1.0
**Til:** O'zbek (lotin yozuvi)
**Sana:** 2026
