<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.kz.md">Қазақша</a> ·
  <a href="README.ar.md">العربية</a>
</p>

<p align="center"><img src=".github/assets/logo.png" width="200" /></p>

<h1 align="center">vtinker</h1>

<p align="center">
  <strong>المُصلح الافتراضي الذي يحوّل فكرة غامضة إلى كود جاهز للنشر.</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <a href="#"><img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero Dependencies" /></a>
  <a href="#"><img src="https://img.shields.io/badge/tests-passing-brightgreen" alt="Tests Passing" /></a>
</p>

<br />

منسّق وكلاء البرمجة المستقل الذي يعمل فوق [OpenCode](https://github.com/opencode-ai/opencode) و [Beads](https://github.com/steveyegge/beads). حدد الهدف، اذهب لشؤونك، وعُد لتجد فرعاً جاهزاً بالاختبارات الناجحة.

<br />

## لماذا vtinker؟

- **تفكيك المهام تكرارياً** — تخطيط، تحسين، تنفيذ، مراجعة، إصلاح، تكرار
- **مستقل عن النموذج** — يعمل مع أي نموذج يدعمه OpenCode (مثل GLM، Qwen، MiniMax، Kimi، ...)
- **الحالة محفوظة في Beads** وليس في الذاكرة — كل مهمة وحكم ومحاولة إصلاح تُتبع كقضية (issue)
- **كشف حلقات الفشل** — يتعرف على تكرار الوكيل لنفس الإصلاح الفاشل ويتوقف عن إهدار التوكنات
- **الاستئناف من أي نقطة** — انقطعت في الثانية صباحاً؟ `vtinker resume` يُكمل من حيث توقفت بالضبط
- **بث مباشر** — شاهد استدعاءات الأدوات ومخرجات النموذج أثناء تنفيذ كل مرحلة
- **توجيه النماذج حسب المرحلة** — استخدم نموذجاً قوياً للتخطيط، وسريعاً للتنفيذ، ودقيقاً للمراجعة

<br />

## البدء السريع

```bash
# 1. ثبّت المتطلبات الأساسية
#    - OpenCode CLI: https://github.com/opencode-ai/opencode
#    - Beads CLI:    https://github.com/steveyegge/beads
#    - Python 3.11+

# 2. ثبّت vtinker
pip install -e .

# 3. انتقل إلى مشروعك
cd /path/to/your/project

# 4. أنشئ ملف إعدادات (اختياري — vtinker يكتشف معظم الأشياء تلقائياً)
mkdir -p .vtinker
cat > .vtinker/config.json << 'EOF'
{
  "checks": [
    {"name": "build", "command": "go build ./..."},
    {"name": "test",  "command": "go test ./..."}
  ]
}
EOF

# 5. شغّل
vtinker start
```

أو تجاوز الحوار التفاعلي بالكامل:

```bash
vtinker start --title "Add rate limiting to API" --desc "Implement token bucket rate limiter for all /api/* endpoints"
```

أو مرّر ملف مواصفات:

```bash
vtinker start --from epic.md
```

<br />

## كيف يعمل

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

| المرحلة | ما يحدث |
|---------|---------|
| **DIALOG** | يستكشف النموذج قاعدة الكود، ويصوغ ملحمة (epic) بمعايير القبول وأوامر التحقق |
| **PREPARE** | ينشئ فرع git (أو worktree) للعمل المعزول |
| **PLAN** | يقسّم الملحمة إلى مهام مرتبة مع مراعاة التبعيات ومعايير القبول |
| **REFINE** | يقيّم كل مهمة — المهام الذرية تُنفَّذ مباشرة، والمعقدة تُقسَّم إلى مهام فرعية |
| **EXECUTE** | ينفّذ النموذج مهمة واحدة، مسترشداً بالوصف ومعايير القبول وسياق العمل المنجز |
| **REVIEW** | يراجع النموذج فرق git وفقاً لمعايير القبول؛ تُجرى الفحوصات (بناء/اختبار/تنسيق) تلقائياً |
| **FIX** | إذا فشلت المراجعة، يتلقى النموذج الملاحظات والفرق ويُصلح المشاكل |
| **FINAL REVIEW** | يُراجَع الفرق الكامل مقابل الملحمة الأصلية؛ أي ثغرات تولّد مهام جديدة ويستمر الدوران |

كل مرحلة تبث مخرجاتها إلى stderr لتتمكن من متابعة التقدم في الوقت الفعلي.

<br />

## الإعدادات

ضع ملف الإعدادات في `.vtinker/config.json` (أو `vtinker.json` في جذر المشروع):

```jsonc
{
  // مجلد العمل (الافتراضي: المجلد الحالي)
  "workdir": ".",

  // بادئة فرع git لفرع العمل
  "branch_prefix": "vtinker/",

  // استخدام git worktree بدلاً من تبديل الفروع
  "use_worktree": false,

  // الحد الأقصى لمحاولات الإصلاح لكل مهمة
  "max_retries": 10,

  // مهلة كل استدعاء OpenCode بالثواني
  "opencode_timeout": 900,

  // مجلد قوالب التعليمات المخصصة
  "prompts_dir": null,

  // أوامر يجب أن تنجح بعد كل مهمة
  "checks": [
    {"name": "build", "command": "go build ./..."},
    {"name": "test",  "command": "go test ./..."},
    {"name": "lint",  "command": "golangci-lint run"}
  ],

  // النموذج الافتراضي لجميع المراحل
  "opencode": {
    "model": "glm-5",
    "agent": null
  },

  // تجاوز النموذج حسب المرحلة (اختياري)
  // المراحل غير المحددة ترجع إلى opencode.model
  "models": {
    "plan":    "glm-5",        // يُستخدم لـ PLAN + REFINE
    "execute": "glm-4.7",     // يُستخدم لـ EXECUTE + FIX
    "review":  "glm-5"        // يُستخدم لـ REVIEW + FINAL REVIEW
  }
}
```

<br />

## نتائج الاختبارات

النماذج اختُبرت على مهام برمجة حقيقية بتنسيق vtinker:

| النموذج | الوقت | المهام المنجزة | الاختبارات المكتوبة | محاولات الإصلاح | الجودة |
|:--------|------:|:--------------:|:-------------------:|:---------------:|:------:|
| GLM-5 | 30د | 8/8 | 51 | 0 | **A+** |
| GLM-4.7 | 25د | 7/7 | 74 | 1 | **A** |
| MiniMax-m2.7 | 41د | 8/8 | 22 | 1 | **B-** |
| MiniMax-m2.5 | 45د | 5/5 | 19 | 3 | **C** |
| Kimi K2.5 | DNF | - | - | - | **F** |
| Qwen3-coder | 9د | 1/1 | 3 | 1 | **D** |

> أنجز GLM-5 جميع المهام من المحاولة الأولى دون أي إصلاحات. لم يُنهِ Kimi K2.5 العمل (دخل في حلقة فشل).

<br />

## البنية المعمارية

```
vtinker/
  cli.py          نقطة دخول CLI — أوامر start، resume، status
  orchestrator.py الحلقة الرئيسية: المراحل، آلة الحالة، التكامل مع git
  config.py       تحميل الإعدادات (.vtinker/config.json) + حفظ الحالة
  beads.py        غلاف رقيق حول CLI الخاص بـ Beads (bd)
  opencode.py     إدارة عملية OpenCode مع بث JSONL
  prompts.py      قوالب التعليمات لكل مرحلة (قابلة للتجاوز)
  parse.py        محلل المخرجات المهيكلة — كتل الكود، الأحكام، الأقسام
  checks.py       تشغيل أوامر الفحص المُعدَّة، تنسيق النتائج
  doom.py         كاشف حلقات الفشل (كشف الإخفاقات المتكررة بالتجزئة)
  gitignore.py    إدارة تلقائية لـ .gitignore لمخرجات vtinker
```

<br />

## التعليمات المخصصة

تجاوز تعليمات أي مرحلة بوضع ملف Markdown في مجلد التعليمات:

```bash
mkdir -p .vtinker/prompts
```

```
.vtinker/prompts/
  dialog.md        # معالج صياغة المهمة
  plan.md          # تفكيك الملحمة إلى مهام
  refine.md        # قرار: ذرية أم تقسيم
  execute.md       # تعليمات التنفيذ
  review.md        # معايير مراجعة الكود
  fix.md           # تعليمات الإصلاح من ملاحظات المراجعة
  final_review.md  # مراجعة الملحمة الكاملة
```

يجب أن يحتوي كل ملف على نفس فتحات `{placeholder}` الموجودة في القوالب الافتراضية. راجع [`vtinker/prompts.py`](vtinker/prompts.py) للقائمة الكاملة للفتحات في كل مرحلة.

حدد المجلد في الإعدادات:

```json
{
  "prompts_dir": ".vtinker/prompts"
}
```

<br />

## المتطلبات الأساسية

| الأداة | الغرض | التثبيت |
|--------|-------|---------|
| **Python 3.11+** | بيئة التشغيل | [python.org](https://www.python.org/) |
| **OpenCode CLI** | واجهة النماذج اللغوية | [github.com/opencode-ai/opencode](https://github.com/opencode-ai/opencode) |
| **Beads CLI** (`bd`) | متتبع المهام | [github.com/beads-project/beads](https://github.com/steveyegge/beads) |

<br />

## مرجع CLI

```
vtinker start [--config PATH] [--dir PATH] [--title TEXT] [--desc TEXT] [--from FILE]
vtinker resume [EPIC_ID] [--config PATH] [--dir PATH]
vtinker status [EPIC_ID]
```

| الأمر | الوصف |
|-------|-------|
| `start` | بدء جلسة vtinker جديدة (تفاعلية أو بدون تدخل) |
| `resume` | استئناف جلسة متوقفة من الحالة المحفوظة |
| `status` | عرض تقدم الملحمة وإنجاز المهام |

<br />

## الرخصة

[MIT](LICENSE)
