# Multi-language — Canonical Source Location

**Nothing exists.** There is no file to point to. When this feature is
built, it will most likely touch:

```
frontend-fte/package.json          (add an i18n library)
frontend-fte/app/                  (locale routing / provider)
backend-fte/app/config.py          (if server-rendered strings or
                                     locale-aware formatting are needed)
```

No snapshot exists.
