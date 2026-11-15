// oxlint rules of broom's own, for the smells oxlint has no rule for. They load as an oxlint JS plugin (alpha, with
// an ESLint v9 compatible API) from a pass of their own, so an old oxlint or a missing Node costs these two smells
// and no others. Messages quote only what broom reads back as a name: no quotes around a parameter.

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

export default { meta: { name: "broom" }, rules: { "bool-params": boolParams, "class-lines": classLines } };
