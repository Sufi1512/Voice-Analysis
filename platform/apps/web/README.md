# NEXORA portal (`platform/apps/web`)

Next.js (App Router, React 19), Tailwind with the Signal Room tokens, next-intl. Talks to NEXORA
Core only through its own origin: `/v1/*` is proxied to `NEXORA_API_URL`, so the session cookie
stays first-party.

```sh
pnpm install
NEXORA_API_URL=http://localhost:8080 pnpm dev   # Core running locally
pnpm check                                      # lint (incl. RTL rules), types, tests
pnpm build
```

## Rules the lint enforces

- **Right-to-left ready (P1 AC-9b):** logical classes only (`ms-4`, `text-end`, `border-s`);
  physical ones (`ml-4`, `text-right`, `left-0`) fail with the replacement named.
  Stylesheets are scanned the same way (`tests/css-logical.test.ts`).
- **Every visible string is translated:** no text in JSX and no literal `aria-label`,
  `placeholder`, `title` or `alt`; strings live in `messages/en.json`. Arabic is a new messages
  file plus a locale in `src/i18n/config.ts`.
- **Contrast:** every text token passes WCAG AA (4.5:1) on every surface in both themes
  (`tests/contrast.test.ts`).

## Design

Signal Room canvas: https://claude.ai/artifact/9w5bzWzzctRNkfz7b7ESzD. Differences from the
canvas, made so contrast passes: dark faint text `#8a96ab` (canvas `#7B879C` is 4.18:1 on raised
panels); light voice `#8c5b00`, good `#0f7a55`, warning `#a84b18`. Fonts are self-hosted
(fontsource), so the portal makes no third-party requests.
