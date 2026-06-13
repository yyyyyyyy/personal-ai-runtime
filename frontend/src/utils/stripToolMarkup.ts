/** Strip leaked tool-call markup from assistant message text.

    Some providers emit <｜tool_calls><｜invoke name="shell_exec">… in content. */

const PIPE = /[｜|]/;

function open(): RegExp {
  return new RegExp(`<\\s*[｜|]+tool_calls\\s*>`, "gi");
}
function close(): RegExp {
  return new RegExp(`<\\s*/\\s*[｜|]+tool_calls\\s*>`, "gi");
}
function invoke(): RegExp {
  return new RegExp(
    `<\\s*[｜|]+invoke[^>]*>[\\s\\S]*?<\\s*/\\s*[｜|]+invoke\\s*>`,
    "gi"
  );
}
function block(): RegExp {
  return new RegExp(
    `<\\s*[｜|]+tool_calls\\s*>[\\s\\S]*?<\\s*/\\s*[｜|]+tool_calls\\s*>`,
    "gi"
  );
}
function tail(): RegExp {
  return new RegExp(`<\\s*[｜|]+tool_calls\\s*>[\\s\\S]*`, "gi");
}

export function stripToolMarkup(text: string): string {
  if (!text) return "";
  return text.replace(block(), "").replace(tail(), "").trim();
}

export function hasToolMarkup(text: string): boolean {
  return open().test(text) || invoke().test(text);
}
