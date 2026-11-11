# Character Card Studio — v2.5 Update

This update connects the app to SillyTavern and gives you more ways to check and reuse a story. Lore now follows the
point where your roleplay starts. Cards keep their pictures. Cards, lorebooks and Quick Replies can go straight into a
running SillyTavern. Your existing data is migrated automatically and nothing is lost.

> **After updating:** restart the app (`start.bat` / `start.sh`). The backend has new routes, and an old backend
> still running will return "not found" errors.

---

## Highlights

- **Lore as of the starting point.** Entries and cards only know what the story has said by the time your roleplay
  starts.
- **UPDATE IN LORE shows every change first**, and you can untick any of them.
- **Send to SillyTavern:** cards, lorebooks and Quick Reply sets, with basic-auth support.
- **Portraits are saved** with cards and TEXT characters. **CHARX** export.
- **Prose scan** in the Critic: stock phrases, overused words, filler and more, with no model call.
- **Interview** a character, then check its answers against its notes.
- **Relationship map**, **story bible** (Markdown or printable), **Data Bank pack**, **Quick Reply sets**.
- **Secrets:** facts only some characters know, which SillyTavern shows only to those characters.

---

## Text Studio

### Lore as of the starting point
When **Roleplay starts after** is set, everything sent to LORE and every card made from TEXT uses only what the
chapters up to that point say: age, relationships, speech samples and facts. Characters who first appear later are
left out. To see it per entry, open the **BY CHAPTER** tab. It lists what each chapter said, with a red
**ROLEPLAY STARTS HERE** line. Hand-edited entries are always used exactly as you wrote them. Untick "Lore and cards
only use facts up to this point" to send everything.

### Mentions
The **MENTIONS** tab lists every line of your text that names the entry, chapter by chapter, so you can check a fact
without searching the whole story. One-word names keep their capital letter, so a character called "Will" doesn't
match "will". Tick *ignore case* if you want those too.

### Preview before updating LORE
**UPDATE IN LORE** no longer writes straight away. A preview groups every entry:

- **Refreshed:** the text changed, shown as a word-by-word diff.
- **New:** not in the LORE project yet.
- **Going to the LORE trash:** no longer kept. You can restore these in LORE.
- **Kept as you edited them in LORE:** your LORE edits win.

Untick anything to leave it exactly as it is.

### Often here
Place entries can end with an **Often here:** line naming the characters usually found there. It is counted from
events at that place and from chapters where both appear, so it costs no model call. It is on by default; untick it
under Roleplay starts after.

### Interview
Characters have an **INTERVIEW** tab. Pick a starter question or type your own, and the character answers in its
own voice from its notes. When you have a few answers, **✓ CHECK AGAINST NOTES** lists any answer that contradicts
the notes or sounds out of character. Nothing is saved. Cards in the CHARACTER studio have the same thing under
**Interview**.

### Relationship map
**◇ RELATIONSHIP MAP** draws who is linked to whom. Squares are characters and diamonds are factions; filled means
a main character, and bigger means more links. You can:

- drag nodes to rearrange them;
- hover a node to highlight its links;
- click a node to see both sides of each relationship;
- jump from a node to its entry in review;
- download the map as an SVG.

### Secrets: who knows this
Optional, under any entry's **SECRETS** section. Write a fact and pick who knows it. Each secret becomes its own LORE
entry with SillyTavern's **character filter**, so it only reaches the prompt when one of those characters is
speaking, in a solo or a group chat. If nobody is picked, only the character itself knows. A character's interview
knows its secrets. Secrets appear in the story bible for you, but never in the Data Bank pack, because the Data Bank
has no character filter.

### Pictures
Characters can have a picture (EDIT tab). **MAKE CARD** carries it over to the CHARACTER studio as the card's portrait.

---

## Story bible, Data Bank and Quick Replies (TEXT and LORE)

- **Story bible:** everything the project knows, in reading order: story so far, timeline, relationships,
  characters (main first), factions, places, the rest, and secrets. Download it as **Markdown**, or open the
  **printable page** with portraits and use its *Print / Save as PDF* button.
- **Data Bank pack:** a .zip with one Markdown note per entry and instructions. In SillyTavern, open the wand menu,
  choose **Open Data Bank**, add the files, and turn on Vector Storage for files. Notes are found by meaning instead
  of keywords, which suits long background notes.
- **Quick Reply set:** buttons under the SillyTavern chat box. **→ place** moves the scene, **+ character** brings
  someone in, and **Recap**, **Time skip** and **Who's here?** help keep a long roleplay on track. Download the
  .json or send it straight to SillyTavern.

---

## Critic: prose scan

**✓ PROSE SCAN** runs instantly on the chosen scope, with no model call. It shows:

- stock "AI-sounding" phrases, with examples from your text;
- overused words;
- filler words and -ly adverbs;
- how many dialogue tags are something other than *said* or *asked*;
- runs of sentences that start with the same word;
- a by-chapter table, in story order or worst first.

The phrase list is `backend/config/ai_cliches.txt`; add or remove lines to taste.

---

## Lore Studio

- Entries over about 150 tokens show a size hint, and very long ones get a **LONG** badge. Stock phrases are
  pointed out as you type.
- **✂ TRIM** asks the model for a shorter version and shows it next to the original. Nothing changes until you
  press **USE TRIMMED**.
- **Send to SillyTavern** saves the project as a World Info lorebook in SillyTavern. Sending it again under the same
  name replaces it.

---

## Character Studio

- **With strangers / With people close to them:** two profile fields for how the character changes with closeness.
- **AUDIT** also flags heavy trauma wording, many absolutes ("always", "never"), oversized group cards, missing or
  identical personality layers, and stock phrases. A long description gets **✂ TRIM DESCRIPTION**.
- **Portraits are saved** with the card. Reopening a card from the Library brings its picture back, and the Library
  shows thumbnails.
- **SEND TO SILLYTAVERN** (under the PNG export) imports the card, with its portrait and attached lorebook, into a
  running SillyTavern. Sending it again replaces that card instead of adding a copy.
- **CHARX** export: a Character Card V3 zip with the portrait inside. SillyTavern and other V3 apps import it.
- The toolbar is two rows: making and checking cards on top, exports below.

---

## Config: SillyTavern

Fill in SillyTavern's address (default `http://127.0.0.1:8000`). Add a user name and password only if SillyTavern
has basic auth turned on (`basicAuthMode` in its `config.yaml`). Then press **TEST CONNECTION**. The password is
saved masked, like the API keys. If SillyTavern runs on another computer, its whitelist has to allow this one.

---

## Bundles

Project bundles now include the pictures of the cards and characters in them. They also hold a ready-to-use card
PNG for every card that has a PNG portrait.
