/** Strip leaked tool-call markup from assistant message text.

    Some providers emit <｜tool_calls><｜invoke name="shell_exec">… in content. */

/** Matches complete <｜tool_calls>…</｜tool_calls> blocks (including all nested content). */
function block(): RegExp {
  return new RegExp(`<\\s*[｜|]+tool_calls\\s*>[\\s\\S]*?<\\s*/\\s*[｜|]+tool_calls\\s*>`, "gi");
}

/** Matches standalone <｜invoke>…</｜invoke> blocks (without outer tool_calls wrapper). */
function invoke(): RegExp {
  return new RegExp(`<\\s*[｜|]+invoke[^>]*>[\\s\\S]*?<\\s*/\\s*[｜|]+invoke\\s*>`, "gi");
}

/** Matches any individual open/close/self-closing tool-call markup tag. */
function anyTag(): RegExp {
  return new RegExp(`<\\s*\\/?\\s*[｜|]+\\s*(?:tool_calls|invoke|parameter)\\b[^>]*>`, "gi");
}

/**
 * Final safety-net: if any `<｜` survived all previous passes,
 * strip from there to end of string.
 */
function ultimateTail(): RegExp {
  return new RegExp(`<\\s*[｜|][\\s\\S]*$`, "i");
}

export function stripToolMarkup(text: string, options?: { trim?: boolean }): string {
  if (!text) return "";

  // Step 1: complete <｜tool_calls>…</｜tool_calls> blocks
  text = text.replace(block(), "");

  // Step 2: standalone <｜invoke>…</｜invoke> blocks
  text = text.replace(invoke(), "");

  // Step 3: any surviving individual tool-call tags
  text = text.replace(anyTag(), "");

  // Step 4: ultimate safety-net
  text = text.replace(ultimateTail(), "");

  return options?.trim === false ? text : text.trim();
}

export function hasToolMarkup(text: string): boolean {
  if (!text) return false;
  return /<[｜|]/.test(text);
}
