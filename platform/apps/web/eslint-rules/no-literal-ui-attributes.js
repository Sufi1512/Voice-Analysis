// ESLint rule: user-facing attribute text must be translated (no string literals).
// alt="" stays allowed: it marks an image as decorative.

const ATTRS = new Set(["aria-label", "aria-description", "aria-placeholder", "aria-roledescription", "placeholder", "title", "alt"]);

/** @type {import("eslint").Rule.RuleModule} */
const rule = {
  meta: {
    type: "problem",
    docs: { description: "Translate user-facing attribute text (messages/en.json)" },
    messages: { literal: "'{{attr}}' text must come from translations (t(...)), not a string literal." },
    schema: [],
  },
  create(context) {
    return {
      JSXAttribute(attr) {
        const name = attr.name.type === "JSXIdentifier" ? attr.name.name : null;
        if (!name || !ATTRS.has(name) || !attr.value) return;
        let value = attr.value;
        if (value.type === "JSXExpressionContainer") value = value.expression;
        const text =
          value.type === "Literal" && typeof value.value === "string"
            ? value.value
            : value.type === "TemplateLiteral" && value.expressions.length === 0
              ? value.quasis[0].value.cooked
              : null;
        if (text !== null && text.trim() !== "") context.report({ node: attr, messageId: "literal", data: { attr: name } });
      },
    };
  },
};

export default rule;
