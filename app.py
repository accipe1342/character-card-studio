import io
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from database import (
    DB_PATH,
    create_or_update_card,
    delete_card,
    get_card,
    get_source,
    init_db,
    list_cards,
    save_field_version,
    save_source,
)
from generator import generate_full_card, regenerate_single_field
from preview import build_export_card_json, format_structured_profile_text
from scraper import parse_fandom_url, scrape_fandom_page


def load_config():
    if not CONFIG_PATH.exists():
        return {"use_templates": False}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config" / "settings.json"

load_dotenv(ENV_PATH, override=True)

app = Flask(__name__)
init_db()


# ---------- DB helpers ----------
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_table_names() -> list[str]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    rows = [r["name"] for r in cur.fetchall()]
    conn.close()
    return rows


def get_table_rows(
    table_name: str, limit: int = 100
) -> tuple[list[str], list[sqlite3.Row]]:
    allowed = {"sources", "cards", "field_versions"}
    if table_name not in allowed:
        abort(404)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    conn.close()
    return columns, rows


def get_table_count(table_name: str) -> int:
    allowed = {"sources", "cards", "field_versions"}
    if table_name not in allowed:
        return 0

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
    count = cur.fetchone()["count"]
    conn.close()
    return count


# ---------- Main pages ----------
@app.get("/")
def index():
    cards = list_cards()
    error = request.args.get("error", "")
    return render_template("index.html", cards=cards, error=error)


@app.get("/library")
def library():
    cards = list_cards()
    return render_template("library.html", cards=cards)


from prompt_templates import get_prompt_templates

@app.get("/config")
def config_page():
    config = load_config()
    prompts = get_prompt_templates()
    return render_template("config.html", config=config, prompts=prompts)


from prompt_templates import save_prompt_templates

@app.post("/config")
def save_config_route():
    use_templates = request.form.get("use_templates") == "true"

    character_generation_template = request.form.get("character_generation_template", "").strip()
    field_regeneration_template = request.form.get("field_regeneration_template", "").strip()

    # save toggle
    config = {
        "use_templates": use_templates
    }
    save_config(config)

    # save templates
    save_prompt_templates(
        character_generation_template,
        field_regeneration_template
    )

    return redirect(url_for("config_page"))


# ---------- Scrape / cards ----------
@app.post("/scrape")
def scrape():
    fandom_url = request.form.get("fandom_url", "").strip()

    try:
        wiki_base, page_name = parse_fandom_url(fandom_url)
    except ValueError as e:
        return redirect(url_for("index", error=str(e)))

    provider = (
        request.form.get("provider", "").strip().lower()
        or os.getenv("DEFAULT_PROVIDER", "local").strip().lower()
        or "local"
    )

    if provider in {"lmstudio", "openai_local"}:
        provider = "local"

    model_default = os.getenv("NANOGPT_MODEL", "zai-org/glm-4.7:thinking")
    if provider == "openrouter":
        model_default = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.7")
    elif provider == "local":
        model_default = os.getenv(
            "LOCAL_MODEL", "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K"
        )

    model = request.form.get("model", "").strip() or model_default

    try:
        source = scrape_fandom_page(wiki_base, page_name)
    except Exception as e:
        return redirect(url_for("index", error=f"Scrape failed: {e}"))

    source_id = save_source(source)
    card_id = create_or_update_card(
        source_id,
        {
            "name": source["title"],
            "provider": provider,
            "model": model,
        },
    )
    return redirect(url_for("editor", card_id=card_id))


@app.get("/card/<int:card_id>")
def editor(card_id: int):
    card = get_card(card_id)
    source = get_source(card["source_id"])
    preview_text = format_structured_profile_text(
        card["name"], card["structured_profile"]
    )
    export_json = build_export_card_json(card)
    error = request.args.get("error", "")
    return render_template(
        "editor.html",
        card=card,
        source=source,
        preview_text=preview_text,
        export_json=json.dumps(export_json, ensure_ascii=False, indent=2),
        error=error,
    )


@app.post("/generate/full/<int:card_id>")
def generate_full(card_id: int):
    card = get_card(card_id)
    source = get_source(card["source_id"])
    try:
        generated = generate_full_card(source, card["provider"], card["model"])
    except Exception as e:
        return redirect(url_for("editor", card_id=card_id, error=str(e)))
    generated["provider"] = card["provider"]
    generated["model"] = card["model"]
    create_or_update_card(card["source_id"], generated, card_id=card_id)
    return redirect(url_for("editor", card_id=card_id))


@app.post("/generate/field/<int:card_id>")
def regenerate_field(card_id: int):
    field_name = request.form["field_name"]
    custom_prompt = request.form.get("custom_prompt", "").strip()
    include_current_card = (
        request.form.get("include_current_card", "true").lower() == "true"
    )
    include_source = request.form.get("include_source", "true").lower() == "true"

    card = get_card(card_id)
    source = get_source(card["source_id"])

    result = regenerate_single_field(
        source=source,
        card=card,
        field_name=field_name,
        provider=card["provider"],
        model=card["model"],
        custom_prompt=custom_prompt,
        include_current_card=include_current_card,
        include_source=include_source,
    )

    natural_preview_fields = {
        "name",
        "description",
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "tags",
    }

    structured_subfields = {
        "sp_backstory": "backstory",
        "sp_appearance": "appearance",
        "sp_non_human_appearance": "non_human_appearance",
        "sp_personal_parts": "personal_parts",
        "sp_clothing": "clothing",
        "sp_accessories": "accessories",
        "sp_speech": "speech",
        "sp_personality_traits": "personality_traits",
        "sp_kinks": "kinks",
        "sp_likes": "likes",
        "sp_dislikes": "dislikes",
        "sp_loves": "loves",
        "sp_hates": "hates",
    }

    if field_name in natural_preview_fields or field_name == "structured_profile":
        return jsonify(
            {
                "preview_only": True,
                "field_name": field_name,
                "result": result,
                "current_value": (
                    card.get(field_name)
                    if field_name != "structured_profile"
                    else card.get("structured_profile")
                ),
                "new_value": (
                    result.get(field_name)
                    if field_name != "structured_profile"
                    else result.get("structured_profile")
                ),
            }
        )

    updated = dict(card)

    if field_name in structured_subfields:
        profile_key = structured_subfields[field_name]
        old_value = json.dumps(
            card["structured_profile"].get(profile_key), ensure_ascii=False
        )
        new_piece = result["structured_profile"][profile_key]
        new_value = json.dumps(new_piece, ensure_ascii=False)

        updated_profile = dict(card["structured_profile"])
        updated_profile[profile_key] = new_piece
        updated["structured_profile"] = updated_profile

        save_field_version(card_id, field_name, old_value, new_value)
        create_or_update_card(card["source_id"], updated, card_id=card_id)

        return jsonify(
            {"preview_only": False, "field_name": field_name, "result": result}
        )

    old_value = card.get(field_name)
    new_value = result[field_name]
    updated.update(result)

    save_field_version(card_id, field_name, old_value, new_value)
    create_or_update_card(card["source_id"], updated, card_id=card_id)

    return jsonify({"preview_only": False, "field_name": field_name, "result": result})


@app.post("/apply-preview/<int:card_id>")
def apply_preview(card_id: int):
    payload = request.get_json(force=True)
    field_name = payload["field_name"]
    result = payload["result"]

    card = get_card(card_id)
    updated = dict(card)

    if field_name == "structured_profile":
        old_value = json.dumps(card.get("structured_profile"), ensure_ascii=False)
        new_value = json.dumps(result["structured_profile"], ensure_ascii=False)
        updated["structured_profile"] = result["structured_profile"]
    else:
        old_value = card.get(field_name)
        new_value = result[field_name]
        updated.update(result)

    save_field_version(card_id, field_name, old_value, new_value)
    create_or_update_card(card["source_id"], updated, card_id=card_id)

    return jsonify({"status": "ok"})


@app.post("/card/<int:card_id>/delete")
def delete_card_route(card_id: int):
    delete_card(card_id)
    return redirect(url_for("library"))


@app.post("/save/<int:card_id>")
def save_card(card_id: int):
    payload = request.get_json(force=True)
    card = get_card(card_id)
    # Accept provider/model from payload if caller supplies them, otherwise keep stored values
    payload["provider"] = payload.get("provider") or card["provider"]
    payload["model"] = payload.get("model") or card["model"]
    create_or_update_card(card["source_id"], payload, card_id=card_id)
    return jsonify({"status": "ok"})


@app.get("/export/<int:card_id>")
def export(card_id: int):
    card = get_card(card_id)
    export_json = build_export_card_json(card)
    bio = io.BytesIO(
        json.dumps(export_json, ensure_ascii=False, indent=2).encode("utf-8")
    )
    filename = f"{card['name']}.card.json".replace("/", "-")
    return send_file(
        bio, mimetype="application/json", as_attachment=True, download_name=filename
    )


# ---------- DB viewer ----------
@app.get("/db")
def db_home():
    tables = [
        {"name": name, "count": get_table_count(name)} for name in get_table_names()
    ]
    return render_template("db/home.html", tables=tables)


@app.get("/db/<table_name>")
def db_table(table_name: str):
    columns, rows = get_table_rows(table_name)
    return render_template(
        "db/table.html", table_name=table_name, columns=columns, rows=rows
    )


@app.get("/db/card/<int:card_id>")
def db_card_detail(card_id: int):
    card = get_card(card_id)
    return render_template("db/card_detail.html", card=card)


@app.get("/db/source/<int:source_id>")
def db_source_detail(source_id: int):
    source = get_source(source_id)
    return render_template("db/source_detail.html", source=source)


# ---------- .env editor ----------
@app.get("/env")
def env_editor():
    env_data = ""
    if ENV_PATH.exists():
        env_data = ENV_PATH.read_text(encoding="utf-8")
    return render_template("env_editor.html", env_data=env_data)


@app.post("/env")
def save_env():
    content = request.form.get("env_content", "")
    ENV_PATH.write_text(content.strip() + "\n", encoding="utf-8")
    load_dotenv(ENV_PATH, override=True)
    return redirect(url_for("env_editor"))


if __name__ == "__main__":
    app.run(debug=True)
