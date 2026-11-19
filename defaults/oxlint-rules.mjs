// oxlint rules of broom's own, for the smells oxlint has no rule for. They load as an oxlint JS plugin (alpha, with
// an ESLint v9 compatible API) from a pass of their own, so an old oxlint or a missing Node costs these smells
// and no others. Messages quote only what broom reads back as a name: no quotes around a parameter.

import vm from "node:vm";

const FUNCTIONS = ["FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"];

// `flag: boolean`, `flag?: boolean`, and `flag = true` or `flag = false`.
function isBooleanFlag(param) {
  const target = param.type === "AssignmentPattern" ? param.left : param;
  const typed = target.typeAnnotation?.typeAnnotation?.type === "TSBooleanKeyword";
  const defaulted =
    param.type === "AssignmentPattern" && param.right.type === "Literal" && typeof param.right.value === "boolean";
  return typed || defaulted;
}

// A function handed to a call, such as `items.map((x, ok: boolean) => ...)`: the callee picks its parameters.
function isCallback(node) {
  return node.type !== "FunctionDeclaration" && node.parent?.type === "CallExpression";
}

const boolParams = {
  meta: { type: "suggestion", schema: [] },
  create(context) {
    const check = (node) => {
      if (isCallback(node)) return;
      for (const param of node.params) {
        if (!isBooleanFlag(param)) continue;
        const target = param.type === "AssignmentPattern" ? param.left : param;
        context.report({ node: param, message: `Boolean flag parameter ${target.name ?? ""}.` });
      }
    };
    return Object.fromEntries(FUNCTIONS.map((type) => [type, check]));
  },
};

const DEFAULT_MAX_CLASS_LINES = 250;

const classLines = {
  meta: { type: "suggestion", schema: [{ type: "object", properties: { max: { type: "integer" } } }] },
  create(context) {
    const max = context.options[0]?.max ?? DEFAULT_MAX_CLASS_LINES;
    const check = (node) => {
      const lines = node.loc.end.line - node.loc.start.line + 1;
      if (lines <= max) return;
      context.report({ node, message: `Class '${node.id?.name ?? "class"}' is too long (${lines}). Maximum allowed is ${max}.` });
    };
    return { ClassDeclaration: check, ClassExpression: check };
  },
};

// Module-level `let` or `var` that a function assigns: state shared by whoever calls it.
const moduleState = {
  meta: { type: "suggestion", schema: [] },
  create(context) {
    const inFunction = (scope) => {
      for (let s = scope; s; s = s.upper) if (s.type === "function") return true;
      return false;
    };
    return {
      Program(node) {
        const global = context.sourceCode.getScope(node);
        const top = global.childScopes.find((s) => s.type === "module") ?? global;
        for (const variable of top.variables) {
          const def = variable.defs[0];
          if (!def || !["let", "var"].includes(def.parent?.kind)) continue;
          if (variable.references.some((ref) => ref.isWrite() && !ref.init && inFunction(ref.from))) {
            context.report({ node: def.name, message: `Module-level variable ${variable.name} is assigned in a function.` });
          }
        }
      },
    };
  },
};

// Comments that compile as code: `// total += x;`, or a run of line comments that is a whole block. Prose that
// merely mentions a call doesn't compile, and a `Note: foo()` that does is skipped as a label.
const CODE_MARKS = /[;{}=()]/;
const LABEL = /^\s*[A-Za-z_$][\w$]*\s*:\s/;
const MIN_CODE_LENGTH = 3; // a shorter body is too little to be code

function looksLikeCode(text) {
  const body = text.trim();
  if (body.length < MIN_CODE_LENGTH || !CODE_MARKS.test(body) || LABEL.test(body)) return false;
  try {
    new vm.Script(`(function () {\n${body}\n})`); // compiled, never run
    return true;
  } catch {
    return false;
  }
}

// Runs of adjacent line comments, and each block comment alone; a JSDoc comment is never code.
function commentRuns(comments) {
  const runs = [];
  for (const c of comments) {
    const last = runs[runs.length - 1];
    if (c.type === "Line" && last && last[0].type === "Line" && c.loc.start.line === last[last.length - 1].loc.end.line + 1) {
      last.push(c);
    } else if (c.type === "Line" || !c.value.startsWith("*")) {
      runs.push([c]);
    }
  }
  return runs;
}

// A run that compiles as a whole is one block of code: `// if (x) {`, `//   foo();`, `// }`. One that doesn't may
// still hold a line of code beside the prose around it.
function codeIn(run) {
  const whole = { text: run.map((c) => c.value).join("\n"), loc: run[0].loc };
  if (!whole.text.startsWith("/") && looksLikeCode(whole.text)) return [whole];
  return run.filter((c) => !c.value.startsWith("/") && looksLikeCode(c.value)).map((c) => ({ loc: c.loc }));
}

const commentedCode = {
  meta: { type: "suggestion", schema: [] },
  create(context) {
    return {
      Program() {
        for (const run of commentRuns(context.sourceCode.getAllComments())) {
          for (const code of codeIn(run)) context.report({ loc: code.loc, message: "Commented-out code." });
        }
      },
    };
  },
};

// Exported functions and classes with no comment on what they are for: `export function f`, `export class C`,
// `export const f = () => ...` and a default export. A comment that ends on the line above counts, JSDoc or not;
// a lint directive is no comment on the code.
const DIRECTIVE = /^\s*\*?\s*(eslint-|oxlint-|@ts-|prettier-|biome-|istanbul |c8 |v8 )/;

// What an export statement declares, when that is a function or a class: its kind and its name.
function exported(node) {
  const d = node.declaration;
  if (!d) return null;
  if (d.type === "ClassDeclaration" || d.type === "ClassExpression") return { kind: "class", name: d.id?.name ?? "default" };
  if (FUNCTIONS.includes(d.type)) return { kind: "function", name: d.id?.name ?? "default" };
  const only = d.type === "VariableDeclaration" && d.declarations.length === 1 ? d.declarations[0] : null;
  return only && FUNCTIONS.includes(only.init?.type) ? { kind: "function", name: only.id.name } : null;
}

const missingDocs = {
  meta: { type: "suggestion", schema: [] },
  create(context) {
    const overloaded = new Set(); // a function with overload signatures: its comment sits above the first of them
    const check = (node) => {
      if (node.declaration?.type === "TSDeclareFunction") overloaded.add(node.declaration.id?.name);
      const thing = exported(node);
      if (!thing || overloaded.has(thing.name)) return;
      const above = context.sourceCode.getCommentsBefore(node).filter((c) => !DIRECTIVE.test(c.value));
      const last = above[above.length - 1];
      if (last && last.loc.end.line >= node.loc.start.line - 1) return;
      context.report({ node, message: `Exported ${thing.kind} ${thing.name} has no doc comment.` });
    };
    return { ExportNamedDeclaration: check, ExportDefaultDeclaration: check };
  },
};

// A handler that never looks at the error it caught and throws nothing: a `catch` clause with a body, or a function
// literal handed as the first argument to `.catch(...)`. An empty `catch` body is no-empty's. A handler that uses its
// parameter (more mentions of its name than the parameter itself), destructures it or throws is quiet. The open
// handlers sit on a stack: each Identifier counts for those whose parameter it names, each throw marks them all.
function isPromiseHandler(node) {
  const call = node.parent;
  return (
    call?.type === "CallExpression" &&
    call.arguments[0] === node &&
    call.callee.type === "MemberExpression" &&
    call.callee.property.name === "catch"
  );
}

// The name of the one parameter a handler can look at, or null with `looked` set when there is nothing to count.
function openHandler(param) {
  const named = param?.type === "Identifier";
  return { name: named ? param.name : null, mentions: 0, thrown: false, looked: Boolean(param) && !named };
}

const broadCatch = {
  meta: { type: "suggestion", schema: [] },
  create(context) {
    const open = [];
    const enter = (param) => open.push(openHandler(param));
    const leave = (node, body) => {
      const h = open.pop();
      const empty = node.type === "CatchClause" && body.body.length === 0;
      if (empty || h.thrown || h.looked || h.mentions > 1) return;
      context.report({ node, message: "Handler never looks at the error it caught." });
    };
    const onFunction = {};
    for (const type of FUNCTIONS) {
      onFunction[type] = (node) => isPromiseHandler(node) && enter(node.params[0]);
      onFunction[`${type}:exit`] = (node) => isPromiseHandler(node) && leave(node, node.body);
    }
    return {
      ...onFunction,
      CatchClause: (node) => enter(node.param),
      "CatchClause:exit": (node) => leave(node, node.body),
      Identifier: (node) => open.forEach((h) => { if (h.name === node.name) h.mentions += 1; }),
      ThrowStatement: () => open.forEach((h) => { h.thrown = true; }),
    };
  },
};

export default {
  meta: { name: "broom" },
  rules: { "bool-params": boolParams, "class-lines": classLines, "module-state": moduleState,
           "commented-code": commentedCode, "missing-docs": missingDocs, "broad-catch": broadCatch },
};
