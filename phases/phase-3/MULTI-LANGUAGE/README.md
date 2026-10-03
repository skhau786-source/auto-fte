# Multi-language — 🔴 NOT IMPLEMENTED

## Evidence

Searched the entire repo (backend and frontend) for any of: `i18n`,
`locale`, `translat*`, `multi-language`/`multilanguage`.

```
grep -rliE "i18n|multi.?language|locale|translat" backend-fte/app --include=*.py
→ no matches

grep -rliE "i18n|locale|translat|multi.?lang" frontend-fte/{app,components,lib,src}
→ matched only files containing CSS `translate-x`/`translate-y` utility
  classes (Tailwind transforms) and `toLocaleString`-style calls — false
  positives, not i18n infrastructure
```

No translation files, no locale switcher, no `next-intl`/`react-i18next`/
similar dependency in `frontend-fte/package.json`, no `Accept-Language`
handling in the backend, no per-user or per-store locale field on any
model.

## Conclusion

There is no multi-language support anywhere in this codebase. This is 🔴,
not 🟡 — there is no partial scaffolding to point to.

## Full detail

See `source-location.md`.
