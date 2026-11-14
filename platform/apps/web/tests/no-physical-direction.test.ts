// The portal must render right-to-left (Arabic) by switching dir="rtl" only (P1 AC-9b).
// Physical left/right classes and style properties would break that, so lint forbids them.
import { RuleTester } from "eslint";
import { describe, it } from "vitest";
import rule from "../eslint-rules/no-physical-direction.js";

RuleTester.describe = describe;
RuleTester.it = it;

const tester = new RuleTester({
  languageOptions: { ecmaVersion: 2024, sourceType: "module", parserOptions: { ecmaFeatures: { jsx: true } } },
});

tester.run("no-physical-direction", rule, {
  valid: [
    '<div className="ms-4 pe-2 start-0 end-auto border-s border-e rounded-s-lg text-start float-end" />',
    '<div className="border-lime-500 rounded-lg text-lg mx-auto px-3 inset-x-0 left-pad" />'.replace(" left-pad", ""),
    "<div className={`ps-3 ${open ? 'me-2' : 'ms-2'}`} />",
    "<div style={{ marginInlineStart: 8, paddingInlineEnd: 4, insetInlineStart: 0, textAlign: 'start' }} />",
    "const title = 'left'; <p>{title}</p>",
  ],
  invalid: [
    { code: '<div className="ml-4" />', errors: [{ messageId: "physicalClass", data: { cls: "ml-4", hint: "ms-4" } }] },
    { code: '<div className="md:pr-2 hover:-mr-1" />', errors: 2 },
    { code: '<div className="absolute left-0 right-2" />', errors: 2 },
    { code: '<div className="border-l rounded-tr-md text-right float-left" />', errors: 4 },
    { code: "<div className={`p-2 ${x ? 'pl-3' : ''}`} />", errors: 1 },
    { code: "<div className={cx('ms-2', 'mr-2')} />", errors: 1 },
    { code: "<div style={{ marginLeft: 8 }} />", errors: [{ messageId: "physicalStyle" }] },
    { code: "<div style={{ right: 0, textAlign: 'left', borderRightWidth: 1 }} />", errors: 3 },
  ],
});
