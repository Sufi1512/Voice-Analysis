// ESLint rule: no physical left/right in Tailwind classes or style props (RTL readiness, P1 AC-9b).
// Each finding names the logical replacement, e.g. ml-4 -> ms-4, text-right -> text-end.

const LOGICAL = {
  ml: "ms", mr: "me", pl: "ps", pr: "pe",
  "scroll-ml": "scroll-ms", "scroll-mr": "scroll-me", "scroll-pl": "scroll-ps", "scroll-pr": "scroll-pe",
  left: "start", right: "end",
  "border-l": "border-s", "border-r": "border-e",
  "rounded-l": "rounded-s", "rounded-r": "rounded-e",
  "rounded-tl": "rounded-ss", "rounded-tr": "rounded-se", "rounded-bl": "rounded-es", "rounded-br": "rounded-ee",
  "text-left": "text-start", "text-right": "text-end",
  "float-left": "float-start", "float-right": "float-end",
  "clear-left": "clear-start", "clear-right": "clear-end",
};
// Longest first so "scroll-ml" wins over "ml" and "rounded-tl" over "rounded-l".
const KEYS = Object.keys(LOGICAL).sort((a, b) => b.length - a.length);
const UTILITY = new RegExp(`^(${KEYS.map((k) => k.replace(/[-]/g, "\\-")).join("|")})(?=-|$)`);

const STYLE_PROPS = /^(margin|padding)(Left|Right)$|^(left|right)$|^border(Left|Right)|^border(Top|Bottom)(Left|Right)Radius$|^scroll(Margin|Padding)(Left|Right)$/;
const DIRECTIONAL_VALUES = new Set(["textAlign", "float", "clear"]);

/** Return { cls, hint } for each physical utility in a class string. */
export function physicalClasses(value) {
  const found = [];
  for (const token of value.split(/\s+/)) {
    if (!token) continue;
    const cut = token.lastIndexOf(":") + 1; // after variants such as md: or hover:
    const prefix = token.slice(0, cut);
    let utility = token.slice(cut);
    let sign = "";
    if (utility.startsWith("!")) { sign = "!"; utility = utility.slice(1); }
    if (utility.startsWith("-")) { sign += "-"; utility = utility.slice(1); }
    const match = UTILITY.exec(utility.replace(/!$/, ""));
    if (match) {
      const hint = prefix + sign + LOGICAL[match[1]] + utility.slice(match[1].length);
      found.push({ cls: token, hint });
    }
  }
  return found;
}

function stringNodes(node, out = []) {
  if (!node || typeof node !== "object") return out;
  if (node.type === "Literal" && typeof node.value === "string") out.push({ node, text: node.value });
  else if (node.type === "TemplateElement") out.push({ node, text: node.value.cooked ?? "" });
  for (const [key, child] of Object.entries(node)) {
    if (key === "parent" || key === "loc" || key === "range") continue;
    if (Array.isArray(child)) child.forEach((c) => stringNodes(c, out));
    else if (child && typeof child.type === "string") stringNodes(child, out);
  }
  return out;
}

function propName(prop) {
  if (prop.type !== "Property") return null;
  if (prop.key.type === "Identifier") return prop.key.name;
  if (prop.key.type === "Literal") return String(prop.key.value);
  return null;
}

/** @type {import("eslint").Rule.RuleModule} */
const rule = {
  meta: {
    type: "problem",
    docs: { description: "Use logical (start/end) classes and style properties so the portal works right-to-left" },
    messages: {
      physicalClass: "'{{cls}}' is physical left/right; use '{{hint}}' so right-to-left layouts mirror.",
      physicalStyle: "'{{prop}}' is physical left/right; use the logical property (inline-start / inline-end).",
    },
    schema: [],
  },
  create(context) {
    return {
      JSXAttribute(attr) {
        const name = attr.name.name;
        if ((name === "className" || name === "class") && attr.value) {
          for (const { node, text } of stringNodes(attr.value)) {
            for (const data of physicalClasses(text)) context.report({ node, messageId: "physicalClass", data });
          }
        }
        if (name === "style" && attr.value?.type === "JSXExpressionContainer") {
          const obj = attr.value.expression;
          if (obj.type !== "ObjectExpression") return;
          for (const prop of obj.properties) {
            const key = propName(prop);
            if (!key) continue;
            const directional =
              DIRECTIONAL_VALUES.has(key) &&
              prop.value.type === "Literal" &&
              (prop.value.value === "left" || prop.value.value === "right");
            if (STYLE_PROPS.test(key) || directional) {
              context.report({ node: prop, messageId: "physicalStyle", data: { prop: key } });
            }
          }
        }
      },
    };
  },
};

export default rule;
