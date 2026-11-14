// User-facing attribute text (aria-label, placeholder, title, alt) must come from messages/en.json,
// like JSX text (react/jsx-no-literals), so the Arabic translation is a file, not a code change.
import { RuleTester } from "eslint";
import { describe, it } from "vitest";
import rule from "../eslint-rules/no-literal-ui-attributes.js";

RuleTester.describe = describe;
RuleTester.it = it;

new RuleTester({
  languageOptions: { ecmaVersion: 2024, sourceType: "module", parserOptions: { ecmaFeatures: { jsx: true } } },
}).run("no-literal-ui-attributes", rule, {
  valid: [
    "<button aria-label={t('close')} />",
    '<input type="email" name="email" autoComplete="email" className="h-10" />',
    '<img alt="" src="/x.svg" />',
    "<div aria-labelledby=\"h1\" />",
  ],
  invalid: [
    { code: '<button aria-label="Close" />', errors: [{ messageId: "literal", data: { attr: "aria-label" } }] },
    { code: '<input placeholder="you@company.sa" />', errors: 1 },
    { code: '<abbr title="Organization" />', errors: 1 },
    { code: '<img alt="NEXORA logo" />', errors: 1 },
    { code: "<input placeholder={'Search'} />", errors: 1 },
  ],
});
