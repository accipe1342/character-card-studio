/** Shared facts about a lore entry: which ones SillyTavern always loads, and how big one is. */

export const ALWAYS_ON_TITLES = ["Story So Far", "Cast Roster", "Relationships"];
export const isAlwaysOn = (e) => (e.constant === null || e.constant === undefined ? ALWAYS_ON_TITLES.includes(e.title) : !!e.constant);
export const entryTokens = (e) => Math.max(1, Math.ceil((e.content_chars ?? (e.content || "").length) / 4));
