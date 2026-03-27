<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.kz.md">Қазақша</a> ·
  <a href="README.ar.md">العربية</a>
</p>

<p align="center"><img src=".github/assets/logo.png" width="200" /></p>

<h1 align="center">vtinker</h1>

<p align="center">
  <strong>Бұлдыр идеяны дайын кодқа айналдыратын виртуалды шебер.</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <a href="#"><img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero Dependencies" /></a>
  <a href="#"><img src="https://img.shields.io/badge/tests-passing-brightgreen" alt="Tests Passing" /></a>
</p>

<br />

[OpenCode](https://github.com/opencode-ai/opencode) және [Beads](https://github.com/beads-project/beads) үстінде жұмыс істейтін автономды код жазу агенттерінің оркестраторы. Мақсатты белгілеңіз, кетіңіз, тесттері өткен дайын бұтаққа қайтып келіңіз.

<br />

## Неге vtinker?

- **Рекурсивті тапсырма декомпозициясы** — жоспарлау, нақтылау, орындау, тексеру, түзету, қайталау
- **Модельге тәуелді емес** — OpenCode қолдайтын кез келген модельмен жұмыс істейді (GLM, Qwen, MiniMax, Kimi, ...)
- **Күй Beads-те сақталады**, жадта емес — әрбір тапсырма, шешім және түзету әрекеті issue ретінде бақыланады
- **Циклге түсуді анықтау** — агент сол сәтсіз түзетуді қайталап жатқанын таниды және токендерді босқа жұмсауды тоқтатады
- **Кез келген нүктеден жалғастыру** — түнгі 2-де үзілді ме? `vtinker resume` дәл сол жерден жалғастырады
- **Нақты уақыттағы ағынды шығару** — әр кезең жұмыс істеген кезде құрал шақыруларын және модель шығысын бақылаңыз
- **Кезеңдер бойынша модель маршруттау** — жоспарлау үшін күшті модельді, орындау үшін жылдамды, тексеру үшін мұқиятты пайдаланыңыз

<br />

## Жылдам бастау

```bash
# 1. Алдын ала қажетті құралдарды орнатыңыз
#    - OpenCode CLI: https://github.com/opencode-ai/opencode
#    - Beads CLI:    https://github.com/beads-project/beads
#    - Python 3.11+

# 2. vtinker орнатыңыз
pip install -e .

# 3. Жобаңызға өтіңіз
cd /path/to/your/project

# 4. Конфигурация жасаңыз (міндетті емес — vtinker көпшілігін автоматты анықтайды)
mkdir -p .vtinker
cat > .vtinker/config.json << 'EOF'
{
  "checks": [
    {"name": "build", "command": "go build ./..."},
    {"name": "test",  "command": "go test ./..."}
  ]
}
EOF

# 5. Іске қосыңыз
vtinker start
```

Немесе интерактивті диалогты толығымен өткізіп жіберіңіз:

```bash
vtinker start --title "Add rate limiting to API" --desc "Implement token bucket rate limiter for all /api/* endpoints"
```

Немесе спецификация файлын беріңіз:

```bash
vtinker start --from epic.md
```

<br />

## Қалай жұмыс істейді

```
 DIALOG ── PREPARE ── PLAN ──┐
                              │
                    ┌─────────┘
                    │
                    ├── REFINE ── EXECUTE ── REVIEW ── FIX ──┐
                    │                                         │
                    └─────────────────────────────────────────┘
                              │
                        FINAL REVIEW
```

| Кезең | Не болады |
|-------|----------|
| **DIALOG** | Модель код базасын зерттейді, қабылдау критерийлері мен тексеру командаларымен эпик құрады |
| **PREPARE** | Оқшауланған жұмыс үшін git бұтағын (немесе worktree) жасайды |
| **PLAN** | Эпикті тәуелділіктерді ескере отырып, ретке қойылған тапсырмаларға бөледі, қабылдау критерийлерімен |
| **REFINE** | Әр тапсырманы бағалайды — атомарлық тапсырмалар тікелей орындалады, күрделілері ішкі тапсырмаларға бөлінеді |
| **EXECUTE** | Модель бір тапсырманы орындайды, сипаттама + қабылдау критерийлері + аяқталған жұмыс контексті бойынша бағытталады |
| **REVIEW** | Модель git diff-ті қабылдау критерийлеріне сәйкестігін тексереді; тексерулер (құрастыру/тест/линтер) автоматты іске қосылады |
| **FIX** | Егер тексеру сәтсіз болса, модель кері байланыс пен diff алады және мәселелерді түзетеді |
| **FINAL REVIEW** | Толық diff бастапқы эпикке сәйкестігі тексеріледі; кез келген олқылықтар жаңа тапсырмалар тудырады және цикл жалғасады |

Әр кезең нақты уақытта прогресті бақылау үшін stderr-ге шығарылады.

<br />

## Конфигурация

Конфигурация файлын `.vtinker/config.json` жолына (немесе жоба түбіріндегі `vtinker.json`) орналастырыңыз:

```jsonc
{
  // Жұмыс директориясы (әдепкі: ағымдағы директория)
  "workdir": ".",

  // Жұмыс бұтағы үшін git бұтақ префиксі
  "branch_prefix": "vtinker/",

  // Бұтақтарды ауыстырудың орнына git worktree пайдалану
  "use_worktree": false,

  // Тапсырма үшін түзету әрекеттерінің максималды саны
  "max_retries": 10,

  // Бір OpenCode шақыруына тайм-аут (секундпен)
  "opencode_timeout": 900,

  // Пайдаланушы промпт үлгілерінің директориясы
  "prompts_dir": null,

  // Әр тапсырмадан кейін өтуі тиіс командалар
  "checks": [
    {"name": "build", "command": "go build ./..."},
    {"name": "test",  "command": "go test ./..."},
    {"name": "lint",  "command": "golangci-lint run"}
  ],

  // Барлық кезеңдер үшін әдепкі модель
  "opencode": {
    "model": "glm-5",
    "agent": null
  },

  // Кезеңдер бойынша модельді қайта анықтау (міндетті емес)
  // Көрсетілмеген кезеңдер opencode.model-ді пайдаланады
  "models": {
    "plan":    "glm-5",        // PLAN + REFINE үшін
    "execute": "glm-4.7",     // EXECUTE + FIX үшін
    "review":  "glm-5"        // REVIEW + FINAL REVIEW үшін
  }
}
```

<br />

## Тестілеу нәтижелері

Модельдер vtinker оркестрациясымен нақты код жазу тапсырмаларында тексерілді:

| Модель | Уақыт | Орындалған тапсырмалар | Жазылған тесттер | Түзету әрекеттері | Сапа |
|:-------|------:|:----------------------:|:----------------:|:-----------------:|:----:|
| GLM-5 | 30м | 8/8 | 51 | 0 | **A+** |
| GLM-4.7 | 25м | 7/7 | 74 | 1 | **A** |
| MiniMax-m2.7 | 41м | 8/8 | 22 | 1 | **B-** |
| MiniMax-m2.5 | 45м | 5/5 | 19 | 3 | **C** |
| Kimi K2.5 | DNF | - | - | - | **F** |
| Qwen3-coder | 9м | 1/1 | 3 | 1 | **D** |

> GLM-5 барлық тапсырмаларды бірінші әрекетте, бірде-бір түзетусіз орындады. Kimi K2.5 аяқтай алмады (циклге түсті).

<br />

## Архитектура

```
vtinker/
  cli.py          CLI кіру нүктесі — start, resume, status командалары
  orchestrator.py Негізгі цикл: кезеңдер, күй машинасы, git интеграциясы
  config.py       Конфигурацияны жүктеу (.vtinker/config.json) + күйді сақтау
  beads.py        Beads (bd) CLI үстіндегі жұқа қабат
  opencode.py     JSONL ағынды шығарумен OpenCode процесін басқару
  prompts.py      Әр кезең үшін промпт үлгілері (қайта анықталатын)
  parse.py        Құрылымдық шығыс парсері — код блоктары, шешімдер, бөлімдер
  checks.py       Конфигурацияланған тексеру командаларын іске қосу, нәтижелерді пішімдеу
  doom.py         Циклге түсуді анықтағыш (хеш негізінде қайталанатын сәтсіздіктерді анықтау)
  gitignore.py    vtinker артефактілері үшін .gitignore-ды автобасқару
```

<br />

## Пайдаланушы промпттары

Промпттар директориясына Markdown файлын орналастыру арқылы кез келген кезеңнің промптын қайта анықтаңыз:

```bash
mkdir -p .vtinker/prompts
```

```
.vtinker/prompts/
  dialog.md        # Тапсырма құрастыру шебері
  plan.md          # Эпикті тапсырмаларға бөлу
  refine.md        # Атомарлық немесе бөлу шешімі
  execute.md       # Іске асыру нұсқаулары
  review.md        # Код тексеру критерийлері
  fix.md           # Кері байланыс негізінде түзету нұсқаулары
  final_review.md  # Толық эпик тексеруі
```

Әр файлда әдепкі үлгілердегідей `{placeholder}` слоттары болуы керек. Әр кезең үшін слоттардың толық тізімін [`vtinker/prompts.py`](vtinker/prompts.py) файлынан қараңыз.

Конфигурацияда директорияны көрсетіңіз:

```json
{
  "prompts_dir": ".vtinker/prompts"
}
```

<br />

## Алдын ала қажетті құралдар

| Құрал | Мақсаты | Орнату |
|-------|---------|--------|
| **Python 3.11+** | Орындау ортасы | [python.org](https://www.python.org/) |
| **OpenCode CLI** | LLM интерфейсі | [github.com/opencode-ai/opencode](https://github.com/opencode-ai/opencode) |
| **Beads CLI** (`bd`) | Тапсырмалар трекері | [github.com/beads-project/beads](https://github.com/beads-project/beads) |

<br />

## CLI анықтамасы

```
vtinker start [--config PATH] [--dir PATH] [--title TEXT] [--desc TEXT] [--from FILE]
vtinker resume [EPIC_ID] [--config PATH] [--dir PATH]
vtinker status [EPIC_ID]
```

| Команда | Сипаттама |
|---------|----------|
| `start` | Жаңа vtinker сеансын бастау (интерактивті немесе басқарусыз) |
| `resume` | Үзілген сеансты сақталған күйден жалғастыру |
| `status` | Эпик прогресін және тапсырмалардың орындалуын көрсету |

<br />

## Лицензия

[MIT](LICENSE)
