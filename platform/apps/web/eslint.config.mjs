import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import { defineConfig, globalIgnores } from "eslint/config";
import noLiteralUiAttributes from "./eslint-rules/no-literal-ui-attributes.js";
import noPhysicalDirection from "./eslint-rules/no-physical-direction.js";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    plugins: { nexora: { rules: { "no-physical-direction": noPhysicalDirection, "no-literal-ui-attributes": noLiteralUiAttributes } } },
    rules: {
      // Right-to-left ready (P1 AC-9b): logical classes only, and every visible string translated.
      "nexora/no-physical-direction": "error",
      "nexora/no-literal-ui-attributes": "error",
      "react/jsx-no-literals": ["error", { noStrings: true, ignoreProps: true, allowedStrings: [] }],
    },
  },
  {
    files: ["tests/**", "eslint-rules/**", "**/*.test.{ts,tsx}"],
    rules: { "react/jsx-no-literals": "off", "nexora/no-literal-ui-attributes": "off" },
  },
  globalIgnores([".next/**", "node_modules/**", "next-env.d.ts"]),
]);
