// oxlint rules of broom's own, for the smells oxlint has no rule for. They load as an oxlint JS plugin (alpha, with
// an ESLint v9 compatible API) from a pass of their own, so an old oxlint or a missing Node costs these two smells
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

const classLines = {
  meta: { type: "suggestion", schema: [{ type: "object", properties: { max: { type: "integer" } } }] },
  create(context) {
    const max = context.options[0]?.max ?? 250;
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

function looksLikeCode(text) {
  const body = text.trim();
  if (body.length < 3 || !CODE_MARKS.test(body) || LABEL.test(body)) return false;
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

export default {
  meta: { name: "broom" },
  rules: { "bool-params": boolParams, "class-lines": classLines, "module-state": moduleState,
           "commented-code": commentedCode },
};
