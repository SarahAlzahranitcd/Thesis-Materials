import os
import time
from datetime import datetime
from flask import (
    Flask,
    Response,
    render_template,
    request,
    send_file,
    session,
    flash,
    jsonify,
    redirect,
)
from rdflib import Graph, Literal, Namespace, URIRef, RDF, BNode, Dataset
import requests
from rdflib.util import guess_format
import logging
import random
import string
import csv
import urllib.parse
from rdflib.namespace import XSD
from google.cloud import storage
import traceback

app = Flask(__name__)
GRAPHDB_URL = "http://172.31.128.12:7200/repositories/Metagraphs"


from openai import OpenAI

client = OpenAI(
)

app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
app.config["UPLOAD_FOLDER"] = "upload"

if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])

if not os.path.exists("reuse_results"):
    os.makedirs("reuse_results")


def generate_sparql_with_chatgpt(user_query):
    try:
        print("🚀 Sending query to OpenAI:", user_query)

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that converts natural language queries "
                        "into SPARQL 1.1 queries that work on RDF-star data. "
                        "You must use the RDF-star triple syntax like this: << ?mapping a rr:TriplesMap >> . "
                        "Assume the data includes metadata properties like `metag:mappingType`, `metag:purpose`, "
                        "`dc:source`, etc., where `metag` is the prefix for http://example.com/metag/ "
                        "and `rr` is for http://www.w3.org/ns/r2rml#.\n\n"
                        "Only return the SPARQL query. Do not include explanations, markdown, or extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Generate a SPARQL query for: {user_query}",
                },
            ],
        )

        generated_query = response.choices[0].message.content.strip()
        if generated_query.startswith("```"):
            generated_query = generated_query.split("```")[1].strip()

        print("✅ OpenAI Extracted Query:", generated_query)
        return generated_query

    except Exception:
        print("⚠️ OpenAI API Error:")
        traceback.print_exc()
        return "Error generating query."


def query_graphdb(sparql_query):
    headers = {"Content-Type": "application/sparql-query"}
    try:
        response = requests.post(GRAPHDB_URL, data=sparql_query, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print("❌ GraphDB Query Error:", e)
        return f"GraphDB query failed: {e}"


def upload_to_gcs(bucket_name, source_file_path, destination_blob_name):
    """Uploads a file to Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_path)
    print(f"✅ Uploaded to GCS: {destination_blob_name}")


# ----------------------------
# Main pages
# ----------------------------


@app.route("/")
def main():
    return render_template("home.html")


@app.route("/health")
def health():
    return "ok", 200


@app.route("/reuse_mapping")
def reuse_mapping():
    return render_template("reuse_mapping.html")


@app.route("/task_explanation")
def task_explanation():
    return render_template("task_explanation.html")


@app.route("/llmexperiment")
def llm_experiment():
    return render_template("llmexperiment.html")


# ----------------------------
# Search
# ----------------------------


@app.route("/search", methods=["POST"])
def search():
    try:
        data = request.json
        print("📩 Received Search Request:", data)

        search_type = data.get("searchType")
        if search_type == "nlp":
            user_query = data.get("nlQuery", "").strip()

            if len(user_query) < 10:
                return jsonify(
                    {"error": "Query must be at least 10 characters long."}
                ), 400

            sparql_query = generate_sparql_with_chatgpt(user_query)
            print("🔍 Generated SPARQL Query:", sparql_query)

            headers = {
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            }
            response = requests.post(GRAPHDB_URL, data=sparql_query, headers=headers)
            response.raise_for_status()
            result_json = response.json()

            bindings = result_json.get("results", {}).get("bindings", [])
            parsed_results = []
            for item in bindings:
                parsed_row = {k: v.get("value", "") for k, v in item.items()}
                parsed_results.append(parsed_row)

            print("📊 Parsed GraphDB Results:", parsed_results)

            return jsonify({"sparql_query": sparql_query, "results": parsed_results})

        return jsonify({"error": "Invalid search type"}), 400

    except Exception:
        print("❌ Error in search function:")
        traceback.print_exc()
        return jsonify(
            {"error": "An error occurred while processing your request."}
        ), 500


# Reuse evaluation helpers
# ----------------------------


def _ensure_participant():
    if "participant_id" not in session:
        session["participant_id"] = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=8)
        )


def _ensure_reuse_store():
    session.setdefault("reuse_eval", {})
    session.modified = True


def _clean_text(v):
    return (v or "").strip()


def _save_final_reuse_eval_to_csv(payload):
    """
    Save one CSV per participant and upload it to GCS.
    """
    participant_id = payload.get("participant_id", "UNKNOWN")
    timestamp_for_filename = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reuse_eval_{participant_id}_{timestamp_for_filename}.csv"
    out_file = os.path.join("reuse_results", filename)

    fieldnames = [
        "timestamp",
        "participant_id",
        "s1_scenario_id",
        "s1_reuse_a",
        "s1_reuse_b",
        "s1_reservation_detail",
        "s1_better_option",
        "s1_easier_option",
        "s1_confidence_option",
        "s1_complementary",
        "s1_useful_detail",
        "s1_missing_detail",
        "s1_comments",
        "s2_scenario_id",
        "s2_reuse_a",
        "s2_reuse_b",
        "s2_reservation_detail",
        "s2_better_option",
        "s2_easier_option",
        "s2_confidence_option",
        "s2_complementary",
        "s2_useful_detail",
        "s2_missing_detail",
        "s2_comments",
        "s3_scenario_id",
        "s3_reuse_a",
        "s3_reuse_b",
        "s3_reservation_detail",
        "s3_better_option",
        "s3_easier_option",
        "s3_confidence_option",
        "s3_complementary",
        "s3_useful_detail",
        "s3_missing_detail",
        "s3_comments",
        "overall_preference",
        "overall_preference_reason",
        "final_suggestions",
    ]

    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "participant_id": participant_id,
        "s1_scenario_id": payload.get("s1", {}).get("scenario_id", ""),
        "s1_reuse_a": payload.get("s1", {}).get("reuse_a", ""),
        "s1_reuse_b": payload.get("s1", {}).get("reuse_b", ""),
        "s1_reservation_detail": payload.get("s1", {}).get("reservation_detail", ""),
        "s1_better_option": payload.get("s1", {}).get("better_option", ""),
        "s1_easier_option": payload.get("s1", {}).get("easier_option", ""),
        "s1_confidence_option": payload.get("s1", {}).get("confidence_option", ""),
        "s1_complementary": payload.get("s1", {}).get("complementary", ""),
        "s1_useful_detail": payload.get("s1", {}).get("useful_detail", ""),
        "s1_missing_detail": payload.get("s1", {}).get("missing_detail", ""),
        "s1_comments": payload.get("s1", {}).get("comments", ""),
        "s2_scenario_id": payload.get("s2", {}).get("scenario_id", ""),
        "s2_reuse_a": payload.get("s2", {}).get("reuse_a", ""),
        "s2_reuse_b": payload.get("s2", {}).get("reuse_b", ""),
        "s2_reservation_detail": payload.get("s2", {}).get("reservation_detail", ""),
        "s2_better_option": payload.get("s2", {}).get("better_option", ""),
        "s2_easier_option": payload.get("s2", {}).get("easier_option", ""),
        "s2_confidence_option": payload.get("s2", {}).get("confidence_option", ""),
        "s2_complementary": payload.get("s2", {}).get("complementary", ""),
        "s2_useful_detail": payload.get("s2", {}).get("useful_detail", ""),
        "s2_missing_detail": payload.get("s2", {}).get("missing_detail", ""),
        "s2_comments": payload.get("s2", {}).get("comments", ""),
        "s3_scenario_id": payload.get("s3", {}).get("scenario_id", ""),
        "s3_reuse_a": payload.get("s3", {}).get("reuse_a", ""),
        "s3_reuse_b": payload.get("s3", {}).get("reuse_b", ""),
        "s3_reservation_detail": payload.get("s3", {}).get("reservation_detail", ""),
        "s3_better_option": payload.get("s3", {}).get("better_option", ""),
        "s3_easier_option": payload.get("s3", {}).get("easier_option", ""),
        "s3_confidence_option": payload.get("s3", {}).get("confidence_option", ""),
        "s3_complementary": payload.get("s3", {}).get("complementary", ""),
        "s3_useful_detail": payload.get("s3", {}).get("useful_detail", ""),
        "s3_missing_detail": payload.get("s3", {}).get("missing_detail", ""),
        "s3_comments": payload.get("s3", {}).get("comments", ""),
        "overall_preference": payload.get("final", {}).get("overall_preference", ""),
        "overall_preference_reason": payload.get("final", {}).get(
            "overall_preference_reason", ""
        ),
        "final_suggestions": payload.get("final", {}).get("final_suggestions", ""),
    }

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    print(f"✅ Local CSV saved: {out_file}")

    bucket_name = "s123r123"
    destination_blob_name = f"reuse_results/{filename}"
    upload_to_gcs(bucket_name, out_file, destination_blob_name)


# ----------------------------
# Reuse evaluation routes
# ----------------------------


@app.route("/reuse")
def reuse_intro():
    _ensure_participant()
    return render_template("reuse_intro.html", participant_id=session["participant_id"])


# Scenario 1 = Interlinking
@app.route("/reuse-eval-s1")
def reuse_eval_s1():
    _ensure_participant()
    return render_template(
        "reuse_s3_interlink.html", participant_id=session["participant_id"]
    )


# Scenario 2 = Uplift
@app.route("/reuse-eval-s2")
def reuse_eval_s2():
    _ensure_participant()
    return render_template(
        "reuse_s2_uplift.html", participant_id=session["participant_id"]
    )


# Scenario 3 = Alignment
@app.route("/reuse-eval-s3")
def reuse_eval_s3():
    _ensure_participant()
    return render_template(
        "reuse_s1_alignment.html", participant_id=session["participant_id"]
    )


@app.route("/reuse-final")
def reuse_final():
    _ensure_participant()
    return render_template(
        "reuse_final_questions.html", participant_id=session["participant_id"]
    )


@app.route("/submit-reuse-eval-s1", methods=["POST"])
def submit_reuse_eval_s1():
    try:
        _ensure_participant()
        _ensure_reuse_store()

        participant_id = request.form.get("participant_id", session["participant_id"])

        session["reuse_eval"]["participant_id"] = participant_id
        session["reuse_eval"]["s1"] = {
            "scenario_id": request.form.get("scenario_id", "S1_SILK_INTERLINKING"),
            "reuse_a": request.form.get("reuse_a", ""),
            "reuse_b": request.form.get("reuse_b", ""),
            "reservation_detail": _clean_text(
                request.form.get("reservation_detail", "")
            ),
            "better_option": request.form.get("better_option", ""),
            "easier_option": request.form.get("easier_option", ""),
            "confidence_option": request.form.get("confidence_option", ""),
            "complementary": request.form.get("complementary", ""),
            "useful_detail": _clean_text(request.form.get("useful_detail", "")),
            "missing_detail": _clean_text(request.form.get("missing_detail", "")),
            "comments": _clean_text(request.form.get("comments", "")),
        }
        session.modified = True

        return redirect("/reuse-eval-s2")

    except Exception:
        traceback.print_exc()
        return "Error storing Scenario 1 responses.", 500


@app.route("/submit-reuse-eval-s2", methods=["POST"])
def submit_reuse_eval_s2():
    try:
        _ensure_participant()
        _ensure_reuse_store()

        participant_id = request.form.get("participant_id", session["participant_id"])

        session["reuse_eval"]["participant_id"] = participant_id
        session["reuse_eval"]["s2"] = {
            "scenario_id": request.form.get("scenario_id", "S2_RML_ERA_MAPPING"),
            "reuse_a": request.form.get("reuse_a", ""),
            "reuse_b": request.form.get("reuse_b", ""),
            "reservation_detail": _clean_text(
                request.form.get("reservation_detail", "")
            ),
            "better_option": request.form.get("better_option", ""),
            "easier_option": request.form.get("easier_option", ""),
            "confidence_option": request.form.get("confidence_option", ""),
            "complementary": request.form.get("complementary", ""),
            "useful_detail": _clean_text(request.form.get("useful_detail", "")),
            "missing_detail": _clean_text(request.form.get("missing_detail", "")),
            "comments": _clean_text(request.form.get("comments", "")),
        }
        session.modified = True

        return redirect("/reuse-eval-s3")

    except Exception:
        traceback.print_exc()
        return "Error storing Scenario 2 responses.", 500


@app.route("/submit-reuse-eval-s3", methods=["POST"])
def submit_reuse_eval_s3():
    try:
        _ensure_participant()
        _ensure_reuse_store()

        participant_id = request.form.get("participant_id", session["participant_id"])

        session["reuse_eval"]["participant_id"] = participant_id
        session["reuse_eval"]["s3"] = {
            "scenario_id": request.form.get("scenario_id", "S3_OAEI_ANATOMY_ALIGNMENT"),
            "reuse_a": request.form.get("reuse_a", ""),
            "reuse_b": request.form.get("reuse_b", ""),
            "reservation_detail": _clean_text(
                request.form.get("reservation_detail", "")
            ),
            "better_option": request.form.get("better_option", ""),
            "easier_option": request.form.get("easier_option", ""),
            "confidence_option": request.form.get("confidence_option", ""),
            "complementary": request.form.get("complementary", ""),
            "useful_detail": _clean_text(request.form.get("useful_detail", "")),
            "missing_detail": _clean_text(request.form.get("missing_detail", "")),
            "comments": _clean_text(request.form.get("comments", "")),
        }
        session.modified = True

        payload = session.get("reuse_eval", {})

        if "s1" not in payload or "s2" not in payload:
            return redirect("/reuse")

        return redirect("/reuse-final")

    except Exception:
        traceback.print_exc()
        return "Error saving final responses.", 500


@app.route("/submit-reuse-final", methods=["POST"])
def submit_reuse_final():
    try:
        _ensure_participant()
        _ensure_reuse_store()

        participant_id = request.form.get("participant_id", session["participant_id"])

        session["reuse_eval"]["participant_id"] = participant_id
        session["reuse_eval"]["final"] = {
            "overall_preference": request.form.get("overall_preference", ""),
            "overall_preference_reason": _clean_text(
                request.form.get("overall_preference_reason", "")
            ),
            "final_suggestions": _clean_text(request.form.get("final_suggestions", "")),
        }
        session.modified = True

        payload = session.get("reuse_eval", {})

        if "s1" not in payload or "s2" not in payload or "s3" not in payload:
            return redirect("/reuse")

        _save_final_reuse_eval_to_csv(payload)

        session.pop("reuse_eval", None)
        session.modified = True

        return render_template("reuse_thank_you.html")

    except Exception:
        traceback.print_exc()
        return "Error saving final responses.", 500


# ----------------------------
# LLM experiment
# ----------------------------


@app.route("/generate_mapping", methods=["POST"])
def generate_mapping():
    task_prompt = request.form.get("task_prompt", "").strip()
    metadata_prompt = request.form.get("metadata_prompt", "").strip()
    condition = request.form.get("condition", "without_metadata")
    scenario_id = request.form.get("scenario_id", "").strip()
    mapping_type = request.form.get("mapping_type", "RML").strip()
    run_number = request.form.get("run_number", "1").strip()

    if not task_prompt or len(task_prompt) < 10:
        return render_template(
            "llmexperiment.html",
            generated_code="Please enter a more descriptive task prompt.",
            full_prompt="",
        )

    if mapping_type == "RML":
        system_prompt = (
            "You are a helpful assistant that generates valid RML mappings "
            "from structured task descriptions. "
            "Return only valid RML mapping in Turtle syntax. "
            "Do not include explanations, comments, markdown, or extra text."
        )
    elif mapping_type == "OntologyAlignment":
        system_prompt = (
            "You are a helpful assistant that generates ontology alignment mappings "
            "from structured task descriptions. "
            "Return only the alignment output. "
            "Do not include explanations, comments, markdown, or extra text."
        )
    elif mapping_type == "Interlinking":
        system_prompt = (
            "You are a helpful assistant that generates interlinking rules "
            "from structured task descriptions. "
            "Return only the interlinking rule output. "
            "Do not include explanations, comments, markdown, or extra text."
        )
    else:
        system_prompt = (
            "You are a helpful assistant that generates mapping artefacts "
            "from structured task descriptions. "
            "Return only the mapping output. "
            "Do not include explanations, comments, markdown, or extra text."
        )

    if condition == "with_metadata" and metadata_prompt:
        full_prompt = f"""
Generate a {mapping_type} mapping artefact for the following task.

Task description:
{task_prompt}

Lifecycle metadata:
{metadata_prompt}

Return only the {mapping_type} output with no extra explanation.
""".strip()
    else:
        full_prompt = f"""
Generate a {mapping_type} mapping artefact for the following task.

Task description:
{task_prompt}

Return only the {mapping_type} output with no extra explanation.
""".strip()

    try:
        model_name = "gpt-4o-mini"

        response = client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
        )

        output = response.choices[0].message.content.strip()

        if output.startswith("```"):
            output = (
                output.replace("```turtle", "")
                .replace("```xml", "")
                .replace("```sparql", "")
                .replace("```", "")
                .strip()
            )
        validation_result = "Not tested"
        parse_error = ""

        if mapping_type == "RML":
            try:
                g_val = Graph()
                g_val.parse(data=output, format="turtle")
                validation_result = f"Valid - {len(g_val)} triples"
            except Exception as e:
                validation_result = "Invalid - parse error"
                parse_error = str(e)[:300]

        elif mapping_type == "OntologyAlignment":
            try:
                g_val = Graph()
                g_val.parse(data=output, format="xml")
                validation_result = f"Valid - {len(g_val)} triples"
            except Exception as e:
                validation_result = "Invalid - parse error"
                parse_error = str(e)[:300]

        elif mapping_type == "Interlinking":
            has_query = any(k in output.upper() for k in ["SELECT", "CONSTRUCT"])
            has_where = "WHERE" in output.upper()
            has_sameAs = "sameas" in output.lower()
            if has_query and has_where:
                validation_result = "Valid SPARQL"
                if has_sameAs:
                    validation_result += " + sameAs present"
            else:
                validation_result = "Invalid SPARQL"

        filepath = os.path.join(os.getcwd(), "llm_experiment_results.csv")
        file_exists = os.path.isfile(filepath)

        fieldnames = [
            "timestamp",
            "scenario_id",
            "mapping_type",
            "run_number",
            "condition",
            "task_prompt",
            "metadata_prompt",
            "full_prompt",
            "model",
            "output",
            "validation_result",
            "parse_error",
        ]

        with open(filepath, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "scenario_id": scenario_id,
                    "mapping_type": mapping_type,
                    "run_number": run_number,
                    "condition": condition,
                    "task_prompt": task_prompt,
                    "metadata_prompt": metadata_prompt,
                    "full_prompt": full_prompt,
                    "model": model_name,
                    "output": output,
                    "validation_result": validation_result,
                    "parse_error": parse_error,
                }
            )

        print("✅ Saved experiment log to:", filepath)

        os.makedirs("experiment_results", exist_ok=True)
        safe_condition = condition.replace(" ", "_")
        safe_mapping_type = mapping_type.replace(" ", "_")
        safe_scenario = scenario_id.replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_filename = (
            f"experiment_results/"
            f"{safe_scenario}_{safe_mapping_type}_{safe_condition}_run{run_number}_{timestamp}.txt"
        )

        with open(out_filename, "w", encoding="utf-8") as f:
            f.write(output)

        print("✅ Saved output to:", os.path.abspath(out_filename))

        return render_template(
            "llmexperiment.html",
            generated_code=output,
            full_prompt=full_prompt,
        )

    except Exception as e:
        print("❌ Error generating mapping:", e)
        traceback.print_exc()
        return render_template(
            "llmexperiment.html",
            generated_code="Error generating mapping. Please try again.",
            full_prompt=full_prompt,
        )


# ----------------------------
# Upload + metadata annotation
# ----------------------------


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        participant_id = request.form.get("participant_id")

        if not file or file.filename == "":
            flash("No file uploaded. Please upload a valid file.")
            return render_template("upload.html", participant_id=participant_id)

        file_content = file.read().decode("utf-8")
        filename = file.filename

        saved_file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        with open(saved_file_path, "w", encoding="utf-8") as f:
            f.write(file_content)

        if "rr:TriplesMap" in file_content or "rml:logicalSource" in file_content:
            expected_mapping_type = "Uplift Mapping"
        elif "align:Alignment" in file_content or "align:map" in file_content:
            expected_mapping_type = "Ontologies Alignment"
        elif "INSERT" in file_content and "WHERE" in file_content:
            expected_mapping_type = "Interlinking"
        else:
            flash("The uploaded file does not match any known mapping type.")
            return render_template("upload.html", participant_id=participant_id)

        session["start_time"] = time.time()
        session["participant_id"] = participant_id
        session["file_content"] = file_content
        session["uploaded_file_name"] = filename
        session["expected_mapping_type"] = expected_mapping_type

        return render_template(
            "Ack.html",
            file_content=file_content,
            uploaded_file_name=filename,
            expected_mapping_type=expected_mapping_type,
            participant_id=participant_id,
        )

    return render_template("upload.html")


@app.route("/add_metadata", methods=["GET", "POST"])
def add_metadata():
    return render_template("add_metadata.html")


@app.route("/submit_metadata", methods=["POST"])
def submit_metadata():
    if request.method == "POST":
        form_data = request.form
        user_mapping_type = form_data.get("mappingType")
        expected_mapping_type = session.get("expected_mapping_type")

        if user_mapping_type != expected_mapping_type:
            flash(
                "Mapping type mismatch detected!, Please double-check your selection and ensure that the uploaded file corresponds to the correct mapping type.",
                "error",
            )
            return render_template("add_metadata.html", form_data=form_data)

        generated_codes = set()

        def generate_random_code():
            while True:
                digits = "".join(random.choices(string.digits, k=3))
                letter = random.choice(string.ascii_uppercase)
                code = digits + letter
                if code not in generated_codes:
                    generated_codes.add(code)
                    return code

        unique_code = generate_random_code()
        session["unique_code"] = unique_code

        participant_id = session.get("participant_id")
        uploaded_file_name = session.get("uploaded_file_name")

        end_time = time.time()
        start_time = session.get("start_time")
        duration = end_time - start_time if start_time else None
        logging.debug(
            f"Participant {participant_id} took {duration} seconds to complete."
        )

        g_named_graph = Graph()
        g_rdf_star = Graph()

        populate_named_graph(form_data, g_named_graph)
        rdf_data_named_graph = g_named_graph.serialize(format="turtle")

        timestamp = time.strftime("%Y%m%d%H%M%S")
        duration_suffix = f"_{int(duration)}s" if duration else ""

        rdf_filename_named_graph = (
            f"metadata_named_graph_{timestamp}{duration_suffix}_{unique_code}.ttl"
        )
        rdf_filename_rdf_star = (
            f"metadata_rdf_star_{timestamp}{duration_suffix}_{unique_code}.ttl"
        )

        rdf_named_graph_path = os.path.join(
            app.config["UPLOAD_FOLDER"], rdf_filename_named_graph
        )
        rdf_star_file_path = os.path.join(
            app.config["UPLOAD_FOLDER"], rdf_filename_rdf_star
        )

        with open(rdf_named_graph_path, "w") as file_named_graph:
            file_named_graph.write(rdf_data_named_graph)

        bucket_name = "s123r123"
        upload_to_gcs(
            bucket_name,
            rdf_named_graph_path,
            f"named_graphs/{rdf_filename_named_graph}",
        )

        rdf_star_output = populate_rdf_star(form_data, g_rdf_star, uploaded_file_name)

        with open(rdf_star_file_path, "w") as file_rdf_star:
            file_rdf_star.write(rdf_star_output)

        upload_to_gcs(
            bucket_name, rdf_star_file_path, f"rdf_star/{rdf_filename_rdf_star}"
        )

        return render_template(
            "success.html",
            rdf_data_path_named_graph=rdf_named_graph_path,
            rdf_data_path_rdf_star=rdf_star_file_path,
            unique_code=unique_code,
        )


# ----------------------------
# RDF metadata generation
# ----------------------------


def populate_named_graph(form_data, g_named_graph):
    dcmi = Namespace("http://purl.org/dc/terms/")
    subject_uri = URIRef("http://example.com/metag/subject")
    foaf = Namespace("http://xmlns.com/foaf/0.1/")
    custom_ns = Namespace("http://example.com/metag/")
    g_named_graph.bind("metag", custom_ns)
    g_named_graph.bind("foaf", foaf)
    g_named_graph.bind("dcmi", dcmi)

    g_named_graph.add(
        (subject_uri, foaf.givenName, Literal(form_data.get("fname", "")))
    )
    g_named_graph.add(
        (subject_uri, foaf.familyName, Literal(form_data.get("lname", "")))
    )
    g_named_graph.add(
        (subject_uri, foaf.background, Literal(form_data.get("background", "")))
    )
    g_named_graph.add((subject_uri, foaf.role, Literal(form_data.get("role", ""))))
    g_named_graph.add(
        (subject_uri, foaf.organization, Literal(form_data.get("organization", "")))
    )

    g_named_graph.add(
        (subject_uri, custom_ns.purpose, Literal(form_data.get("requirement", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.mappingType, Literal(form_data.get("mappingType", "")))
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.mappingDomain,
            Literal(form_data.get("mappingDomain", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.mappingAssumptions,
            Literal(form_data.get("mappingAssumptions", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.technicalRequirement,
            Literal(form_data.get("technicalRequirement", "")),
        )
    )
    g_named_graph.add(
        (subject_uri, custom_ns.risksIssues, Literal(form_data.get("risksIssues", "")))
    )

    g_named_graph.add(
        (subject_uri, dcmi.source, Literal(form_data.get("InputURI", "")))
    )
    g_named_graph.add(
        (subject_uri, dcmi.creator, Literal(form_data.get("InputSource", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.fileName, Literal(form_data.get("fileName", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.fileSource, Literal(form_data.get("fileSource", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.fileType, Literal(form_data.get("fileType", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.fileFormat, Literal(form_data.get("fileFormat", "")))
    )

    g_named_graph.add(
        (
            subject_uri,
            custom_ns.finalDesignDecisions,
            Literal(form_data.get("finalDesignDecisions", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.designDecisionJustification,
            Literal(form_data.get("designDecisionJustification", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.qualityMetrics,
            Literal(form_data.get("qualityMetrics", "")),
        )
    )

    g_named_graph.add(
        (
            subject_uri,
            custom_ns.startDate,
            Literal(form_data.get("StartDate", ""), datatype=XSD.date),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.endDate,
            Literal(form_data.get("EndDate", ""), datatype=XSD.date),
        )
    )
    g_named_graph.add((subject_uri, custom_ns.tool, Literal(form_data.get("Tool", ""))))
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.mappingMethod,
            Literal(form_data.get("MappingMethod", "")),
        )
    )
    g_named_graph.add(
        (subject_uri, custom_ns.mappingURI, Literal(form_data.get("mappingURI", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.mappingName, Literal(form_data.get("mappingName", "")))
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.mappingAlgorithm,
            Literal(form_data.get("mappingAlgorithm", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.mappingFormat,
            Literal(form_data.get("mappingFormat", "")),
        )
    )

    g_named_graph.add(
        (subject_uri, custom_ns.testingURI, Literal(form_data.get("testingURI", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.testingName, Literal(form_data.get("testingName", "")))
    )
    g_named_graph.add(
        (subject_uri, custom_ns.testingType, Literal(form_data.get("testingType", "")))
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.testingDate,
            Literal(form_data.get("testingDate", ""), datatype=XSD.date),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.testingResult,
            Literal(form_data.get("testingResult", "")),
        )
    )

    g_named_graph.add(
        (
            subject_uri,
            custom_ns.publisherName,
            Literal(form_data.get("publisherName", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.publisherSource,
            Literal(form_data.get("publisherSource", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.versionNumber,
            Literal(form_data.get("versionNumber", "")),
        )
    )
    g_named_graph.add(
        (
            subject_uri,
            custom_ns.versionDateTime,
            Literal(form_data.get("versionDateTime", ""), datatype=XSD.date),
        )
    )

    return g_named_graph


def populate_rdf_star(form_data, g_rdf_star, uploaded_file_name):
    mapping_type = form_data["mappingType"]

    if mapping_type == "Ontologies Alignment":
        return populate_rdf_star_Ontology(form_data, g_rdf_star, uploaded_file_name)
    elif mapping_type == "Uplift Mapping":
        return populate_rdf_star_Uplift(form_data, g_rdf_star, uploaded_file_name)
    elif mapping_type == "Interlinking":
        return populate_rdf_star_Interlink(form_data, g_rdf_star, uploaded_file_name)


def populate_rdf_star_Interlink(form_data, g_rdf_star, uploaded_file_name):
    safe_file_name = urllib.parse.quote(uploaded_file_name)
    interlink_iri = URIRef(f"http://example.com/interlink/{safe_file_name}")

    custom_ns = Namespace("http://example.com/ontology#")
    dcmi = Namespace("http://purl.org/dc/terms/")
    ex = Namespace("http://example.com/")
    xsd = Namespace("http://www.w3.org/2001/XMLSchema#")
    foaf = Namespace("http://xmlns.com/foaf/0.1/")

    g_rdf_star.bind("custom", custom_ns)
    g_rdf_star.bind("dcmi", dcmi)
    g_rdf_star.bind("ex", ex)
    g_rdf_star.bind("xsd", xsd)

    uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], uploaded_file_name)

    if uploaded_file_name.endswith(".rq"):
        with open(uploaded_file_path, "r", encoding="utf-8") as f:
            sparql_query_content = f.read()

        rdf_star_output = f"{interlink_iri.n3()} a {custom_ns.SPARQLQuery.n3()} ;\n"
        rdf_star_output += (
            f"    {ex.queryContent.n3()} {Literal(sparql_query_content).n3()} .\n\n"
        )

        fname = form_data.get("fname", "")
        lname = form_data.get("lname", "")
        background = form_data.get("background", "")
        role = form_data.get("role", "")
        organization = form_data.get("organization", "")
        requirement = form_data.get("requirement", "")
        mappingAssumptions = form_data.get("mappingAssumptions", "")
        technicalRequirement = form_data.get("technicalRequirement", "")
        risksIssues = form_data.get("risksIssues", "")
        startDate = form_data.get("StartDate", "")
        endDate = form_data.get("EndDate", "")
        tool = form_data.get("Tool", "")
        mappingMethod = form_data.get("MappingMethod", "")
        mappingDomain = form_data.get("mappingDomain", "")
        mappingURI = form_data.get("mappingURI", "")
        mappingName = form_data.get("mappingName", "")
        mappingAlgorithm = form_data.get("mappingAlgorithm", "")
        mappingFormat = form_data.get("mappingFormat", "")
        testingURI = form_data.get("testingURI", "")
        testingName = form_data.get("testingName", "")
        testingType = form_data.get("testingType", "")
        testingDate = form_data.get("testingDate", "")
        testingResult = form_data.get("testingResult", "")
        publisherName = form_data.get("publisherName", "")
        publisherSource = form_data.get("publisherSource", "")
        versionNumber = form_data.get("versionNumber", "")
        versionDateTime = form_data.get("versionDateTime", "")
        finalDesignDecisions = form_data.get("finalDesignDecisions", "")
        designDecisionJustification = form_data.get("designDecisionJustification", "")
        qualityMetrics = form_data.get("qualityMetrics", "")
        stakeholderURI = form_data.get("stakeholderURI", "")

        rdf_star_output += (
            f"# Metadata annotations for the SPARQL query interlinking operation\n"
        )
        rdf_star_output += f"<< {interlink_iri.n3()} {RDF.type.n3()} {custom_ns.InterlinkingOperation.n3()} >>\n"
        rdf_star_output += (
            f"    {dcmi.creator.n3()} {Literal(f'{fname} {lname}').n3()} ;\n"
        )
        rdf_star_output += f"    {foaf.background.n3()} {Literal(background).n3()} ;\n"
        rdf_star_output += f"    {foaf.role.n3()} {Literal(role).n3()} ;\n"
        rdf_star_output += (
            f"    {foaf.organization.n3()} {Literal(organization).n3()} ;\n"
        )
        rdf_star_output += f"    {dcmi.purpose.n3()} {Literal(requirement).n3()} ;\n"
        rdf_star_output += (
            f"    {ex.mappingAssumptions.n3()} {Literal(mappingAssumptions).n3()} ;\n"
        )
        rdf_star_output += f"    {ex.technicalRequirement.n3()} {Literal(technicalRequirement).n3()} ;\n"
        rdf_star_output += f"    {ex.risksIssues.n3()} {Literal(risksIssues).n3()} ;\n"
        rdf_star_output += f"    {ex.toolUsed.n3()} {Literal(tool).n3()} ;\n"
        rdf_star_output += (
            f"    {dcmi.created.n3()} {Literal(startDate).n3()}^^xsd:date ;\n"
        )
        rdf_star_output += (
            f"    {ex.endDate.n3()} {Literal(endDate).n3()}^^xsd:date ;\n"
        )
        rdf_star_output += (
            f"    {ex.mappingMethod.n3()} {Literal(mappingMethod).n3()} ;\n"
        )
        rdf_star_output += (
            f"    {ex.mappingDomain.n3()} {Literal(mappingDomain).n3()} ;\n"
        )
        rdf_star_output += f"    {ex.mappingURI.n3()} {Literal(mappingURI).n3()} ;\n"
        rdf_star_output += f"    {ex.mappingName.n3()} {Literal(mappingName).n3()} ;\n"
        rdf_star_output += (
            f"    {ex.mappingAlgorithm.n3()} {Literal(mappingAlgorithm).n3()} ;\n"
        )
        rdf_star_output += (
            f"    {ex.mappingFormat.n3()} {Literal(mappingFormat).n3()} ;\n"
        )
        rdf_star_output += f"    {ex.testingURI.n3()} {Literal(testingURI).n3()} ;\n"
        rdf_star_output += f"    {ex.testingName.n3()} {Literal(testingName).n3()} ;\n"
        rdf_star_output += f"    {ex.testingType.n3()} {Literal(testingType).n3()} ;\n"
        rdf_star_output += (
            f"    {ex.testingDate.n3()} {Literal(testingDate).n3()}^^xsd:date ;\n"
        )
        rdf_star_output += (
            f"    {ex.testingResult.n3()} {Literal(testingResult).n3()} ;\n"
        )
        rdf_star_output += (
            f"    {ex.publisherName.n3()} {Literal(publisherName).n3()} ;\n"
        )
        rdf_star_output += (
            f"    {ex.publisherSource.n3()} {Literal(publisherSource).n3()} ;\n"
        )
        rdf_star_output += (
            f"    {ex.versionNumber.n3()} {Literal(versionNumber).n3()} ;\n"
        )
        rdf_star_output += f"    {ex.versionDateTime.n3()} {Literal(versionDateTime).n3()}^^xsd:dateTime ;\n"
        rdf_star_output += f"    {ex.finalDesignDecisions.n3()} {Literal(finalDesignDecisions).n3()} ;\n"
        rdf_star_output += f"    {ex.designDecisionJustification.n3()} {Literal(designDecisionJustification).n3()} ;\n"
        rdf_star_output += (
            f"    {ex.qualityMetrics.n3()} {Literal(qualityMetrics).n3()} ;\n"
        )
        rdf_star_output += (
            f"    {ex.stakeholderURI.n3()} {Literal(stakeholderURI).n3()} .\n\n"
        )

        rdf_filename_rdf_star = f"{uploaded_file_name}_rdf_star.ttl"
        rdf_star_file_path = os.path.join(
            app.config["UPLOAD_FOLDER"], rdf_filename_rdf_star
        )

        with open(rdf_star_file_path, "w", encoding="utf-8") as file_rdf_star:
            file_rdf_star.write(rdf_star_output)

        logging.debug(f"RDF-star file saved at: {rdf_star_file_path}")
        return rdf_star_output

    try:
        g_rdf_star.parse(uploaded_file_path, format="turtle", publicID=None)
    except Exception as e:
        logging.error(f"Failed to parse RDF file {uploaded_file_path}: {e}")
        raise e


def populate_rdf_star_Ontology(form_data, g_rdf_star, uploaded_file_name):
    uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], uploaded_file_name)
    try:
        g_rdf_star.parse(uploaded_file_path, format="turtle", publicID=None)
    except Exception as e:
        logging.error(f"Error parsing ontology alignment file: {e}")
        raise e

    alignment_content = g_rdf_star.serialize(format="turtle")

    foaf = Namespace("http://xmlns.com/foaf/0.1/")
    custom_ns = Namespace("http://example.com/metag/")
    align = Namespace("http://knowledgeweb.semanticweb.org/heterogeneity/alignment#")
    dcmi = Namespace("http://purl.org/dc/terms/")

    fname = form_data.get("fname", "")
    lname = form_data.get("lname", "")
    background = form_data.get("background", "")
    role = form_data.get("role", "")
    organization = form_data.get("organization", "")
    requirement = form_data.get("requirement", "")
    mappingType = form_data.get("mappingType", "Ontology Alignment")
    mappingDomain = form_data.get("mappingDomain", "")
    mappingAssumptions = form_data.get("mappingAssumptions", "")
    technicalRequirement = form_data.get("technicalRequirement", "")
    risksIssues = form_data.get("risksIssues", "")
    inputURI = form_data.get("InputURI", "")
    inputSource = form_data.get("InputSource", "")
    startDate = form_data.get("StartDate", "")
    endDate = form_data.get("EndDate", "")
    tool = form_data.get("Tool", "")
    mappingMethod = form_data.get("MappingMethod", "")
    mappingURI = form_data.get("mappingURI", "")
    mappingName = form_data.get("mappingName", "")
    mappingAlgorithm = form_data.get("mappingAlgorithm", "")
    mappingFormat = form_data.get("mappingFormat", "")
    testingURI = form_data.get("testingURI", "")
    testingName = form_data.get("testingName", "")
    testingType = form_data.get("testingType", "")
    testingDate = form_data.get("testingDate", "")
    testingResult = form_data.get("testingResult", "")
    publisherName = form_data.get("publisherName", "")
    publisherSource = form_data.get("publisherSource", "")
    versionNumber = form_data.get("versionNumber", "")
    versionDateTime = form_data.get("versionDateTime", "")

    metadata_output = ""

    for alignment in g_rdf_star.subjects(RDF.type, align.Alignment):
        metadata_output += (
            f"# Metadata annotations for the ontology alignment operation\n"
        )
        metadata_output += (
            f"<< {alignment.n3()} {RDF.type.n3()} {align.Alignment.n3()} >>\n"
        )
        metadata_output += f"    {foaf.givenName.n3()} {Literal(fname).n3()} ;\n"
        metadata_output += f"    {foaf.familyName.n3()} {Literal(lname).n3()} ;\n"
        metadata_output += f"    {foaf.background.n3()} {Literal(background).n3()} ;\n"
        metadata_output += f"    {foaf.role.n3()} {Literal(role).n3()} ;\n"
        metadata_output += (
            f"    {foaf.organization.n3()} {Literal(organization).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.purpose.n3()} {Literal(requirement).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingType.n3()} {Literal(mappingType).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingDomain.n3()} {Literal(mappingDomain).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.mappingAssumptions.n3()} {Literal(mappingAssumptions).n3()} ;\n"
        metadata_output += f"    {custom_ns.technicalRequirement.n3()} {Literal(technicalRequirement).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.risksIssues.n3()} {Literal(risksIssues).n3()} ;\n"
        )
        metadata_output += f"    {dcmi.source.n3()} {Literal(inputURI).n3()} ;\n"
        metadata_output += f"    {dcmi.creator.n3()} {Literal(inputSource).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.startDate.n3()} {Literal(startDate).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.endDate.n3()} {Literal(endDate).n3()} ;\n"
        metadata_output += f"    {custom_ns.tool.n3()} {Literal(tool).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.mappingMethod.n3()} {Literal(mappingMethod).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingURI.n3()} {Literal(mappingURI).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingName.n3()} {Literal(mappingName).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.mappingAlgorithm.n3()} {Literal(mappingAlgorithm).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.mappingFormat.n3()} {Literal(mappingFormat).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingURI.n3()} {Literal(testingURI).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingName.n3()} {Literal(testingName).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingType.n3()} {Literal(testingType).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingDate.n3()} {Literal(testingDate).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingResult.n3()} {Literal(testingResult).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.publisherName.n3()} {Literal(publisherName).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.publisherSource.n3()} {Literal(publisherSource).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.versionNumber.n3()} {Literal(versionNumber).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.versionDateTime.n3()} {Literal(versionDateTime).n3()} .\n\n"

    return f"{alignment_content}\n\n{metadata_output}"


def populate_rdf_star_Uplift(form_data, g_rdf_star, uploaded_file_name):
    uploaded_file_path = os.path.join(app.config["UPLOAD_FOLDER"], uploaded_file_name)

    try:
        g_rdf_star.parse(uploaded_file_path, format="turtle", publicID=None)
    except Exception as e:
        logging.error(f"Error parsing mapping file: {e}")
        raise e

    mapping_content = g_rdf_star.serialize(format="turtle")

    foaf = Namespace("http://xmlns.com/foaf/0.1/")
    custom_ns = Namespace("http://example.com/metag/")
    dcmi = Namespace("http://purl.org/dc/terms/")
    rr = Namespace("http://www.w3.org/ns/r2rml#")

    fname = form_data.get("fname", "")
    lname = form_data.get("lname", "")
    background = form_data.get("background", "")
    role = form_data.get("role", "")
    organization = form_data.get("organization", "")
    requirement = form_data.get("requirement", "")
    mappingType = form_data.get("mappingType", "Uplift Mapping")
    mappingDomain = form_data.get("mappingDomain", "")
    mappingAssumptions = form_data.get("mappingAssumptions", "")
    technicalRequirement = form_data.get("technicalRequirement", "")
    risksIssues = form_data.get("risksIssues", "")
    inputURI = form_data.get("InputURI", "")
    inputSource = form_data.get("InputSource", "")
    startDate = form_data.get("StartDate", "")
    endDate = form_data.get("EndDate", "")
    tool = form_data.get("Tool", "")
    mappingMethod = form_data.get("MappingMethod", "")
    mappingURI = form_data.get("mappingURI", "")
    mappingName = form_data.get("mappingName", "")
    mappingAlgorithm = form_data.get("mappingAlgorithm", "")
    mappingFormat = form_data.get("mappingFormat", "")
    testingURI = form_data.get("testingURI", "")
    testingName = form_data.get("testingName", "")
    testingType = form_data.get("testingType", "")
    testingDate = form_data.get("testingDate", "")
    testingResult = form_data.get("testingResult", "")
    publisherName = form_data.get("publisherName", "")
    publisherSource = form_data.get("publisherSource", "")
    versionNumber = form_data.get("versionNumber", "")
    versionDateTime = form_data.get("versionDateTime", "")

    metadata_output = ""

    for tm in g_rdf_star.subjects(RDF.type, rr.TriplesMap):
        metadata_output += f"# Metadata annotations for the uplift mapping operation\n"
        metadata_output += f"<< {tm.n3()} {RDF.type.n3()} {rr.TriplesMap.n3()} >>\n"
        metadata_output += f"    {foaf.givenName.n3()} {Literal(fname).n3()} ;\n"
        metadata_output += f"    {foaf.familyName.n3()} {Literal(lname).n3()} ;\n"
        metadata_output += f"    {foaf.background.n3()} {Literal(background).n3()} ;\n"
        metadata_output += f"    {foaf.role.n3()} {Literal(role).n3()} ;\n"
        metadata_output += (
            f"    {foaf.organization.n3()} {Literal(organization).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.purpose.n3()} {Literal(requirement).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingType.n3()} {Literal(mappingType).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingDomain.n3()} {Literal(mappingDomain).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.mappingAssumptions.n3()} {Literal(mappingAssumptions).n3()} ;\n"
        metadata_output += f"    {custom_ns.technicalRequirement.n3()} {Literal(technicalRequirement).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.risksIssues.n3()} {Literal(risksIssues).n3()} ;\n"
        )
        metadata_output += f"    {dcmi.source.n3()} {Literal(inputURI).n3()} ;\n"
        metadata_output += f"    {dcmi.creator.n3()} {Literal(inputSource).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.startDate.n3()} {Literal(startDate).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.endDate.n3()} {Literal(endDate).n3()} ;\n"
        metadata_output += f"    {custom_ns.tool.n3()} {Literal(tool).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.mappingMethod.n3()} {Literal(mappingMethod).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingURI.n3()} {Literal(mappingURI).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.mappingName.n3()} {Literal(mappingName).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.mappingAlgorithm.n3()} {Literal(mappingAlgorithm).n3()} ;\n"
        metadata_output += (
            f"    {custom_ns.mappingFormat.n3()} {Literal(mappingFormat).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingURI.n3()} {Literal(testingURI).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingName.n3()} {Literal(testingName).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingType.n3()} {Literal(testingType).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingDate.n3()} {Literal(testingDate).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.testingResult.n3()} {Literal(testingResult).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.publisherName.n3()} {Literal(publisherName).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.publisherSource.n3()} {Literal(publisherSource).n3()} ;\n"
        )
        metadata_output += (
            f"    {custom_ns.versionNumber.n3()} {Literal(versionNumber).n3()} ;\n"
        )
        metadata_output += f"    {custom_ns.versionDateTime.n3()} {Literal(versionDateTime).n3()} .\n\n"

    return f"{mapping_content}\n\n{metadata_output}"


# ----------------------------
# View / download metadata
# ----------------------------


@app.route("/view_metadata")
def view_metadata():
    rdf_data_path = request.args.get("rdf_data_path")
    rdf_star_data_path = request.args.get("rdf_star_data_path")

    if rdf_data_path:
        with open(rdf_data_path, "r") as rdf_file:
            rdf_content = rdf_file.read()
        return Response(rdf_content, mimetype="text/turtle")

    elif rdf_star_data_path:
        with open(rdf_star_data_path, "r") as rdf_star_file:
            rdf_star_content = rdf_star_file.read()
        return Response(rdf_star_content, mimetype="text/turtle")

    return "RDF data is not available for viewing."


@app.route("/download_metadata")
def download_metadata():
    rdf_data_path = request.args.get("rdf_data_path")
    rdf_star_data_path = request.args.get("rdf_star_data_path")

    if rdf_data_path:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        download_name = f"metadata_named_graph_{timestamp}.ttl"
        return send_file(
            rdf_data_path,
            as_attachment=True,
            mimetype="text/turtle",
            download_name=download_name,
        )

    elif rdf_star_data_path:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        download_name = f"metadata_rdf_star_{timestamp}.ttl"
        return send_file(
            rdf_star_data_path,
            as_attachment=True,
            mimetype="text/turtle",
            download_name=download_name,
        )

    return "RDF data is not available for download."


# ----------------------------
# Save anonymous code
# ----------------------------


def save_code_to_csv(code, user_id, filename="codes.csv"):
    file_exists = os.path.isfile(filename)
    with open(filename, "a", newline="") as csvfile:
        fieldnames = ["timestamp", "user_id", "code"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": user_id,
                "code": code,
            }
        )


# ----------------------------
# SPARQL page
# ----------------------------


@app.route("/sparql", methods=["GET", "POST"])
def sparql():
    if request.method == "POST":
        query = request.form["query"]
        headers = {"Content-Type": "application/sparql-query"}
        response = requests.post(GRAPHDB_URL, data=query, headers=headers)
        return response.text
    return render_template("sparql.html")


def _slug(text):
    """Convert free text to a URI-safe slug for IRI minting."""
    import re

    if not text:
        return "unspecified"
    out = re.sub(r"[^A-Za-z0-9_\-]+", "_", text.strip())
    return out[:60] or "unspecified"


def _build_v02_triples(form_data, g, ex_namespace):
    """
    Add MMV v0.2 triples to the graph object g (which can be either a plain
    Graph or a named graph from a Dataset). ex_namespace is the EX Namespace
    used to mint instance IRIs.
    """
    MMV = Namespace("http://w3id.org/mmv/0.2#")
    MQV = Namespace("https://alex-randles.github.io/MQV/#")
    PROV = Namespace("http://www.w3.org/ns/prov#")
    DQV = Namespace("http://www.w3.org/ns/dqv#")
    DCTERMS = Namespace("http://purl.org/dc/terms/")
    FOAF = Namespace("http://xmlns.com/foaf/0.1/")
    EX = ex_namespace

    pid = _slug(form_data.get("projectId", ""))

    project_uri = EX[pid]
    analysis_uri = EX[f"{pid}_analysis"]
    design_uri = EX[f"{pid}_design"]
    development_uri = EX[f"{pid}_development"]
    testing_uri = EX[f"{pid}_testing"]
    maintenance_uri = EX[f"{pid}_maintenance"]
    input_uri = EX[f"{pid}_input"]
    metric_uri = EX[f"{pid}_plannedMetric"]
    report_uri = EX[f"{pid}_validationReport"]

    artifact_iri_str = (form_data.get("mappingURI") or "").strip()
    artifact_uri = (
        URIRef(artifact_iri_str) if artifact_iri_str else EX[f"{pid}_artifact"]
    )
    stakeholder_uri = EX[f"{pid}_stakeholder"]

    def add_lit(s, p, key, datatype=None):
        v = (form_data.get(key) or "").strip()
        if v:
            if datatype is not None:
                g.add((s, p, Literal(v, datatype=datatype)))
            else:
                g.add((s, p, Literal(v)))

    def add_uri(s, p, key):
        v = (form_data.get(key) or "").strip()
        if v:
            g.add((s, p, URIRef(v)))

    # ---- MappingProject ----
    g.add((project_uri, RDF.type, MMV.MappingProject))
    add_lit(project_uri, DCTERMS.title, "projectTitle")
    g.add((project_uri, MMV.hasAnalysis, analysis_uri))
    g.add((project_uri, MMV.hasDesign, design_uri))
    g.add((project_uri, MMV.hasDevelopment, development_uri))
    g.add((project_uri, MMV.hasTesting, testing_uri))
    g.add((project_uri, MMV.hasMaintenance, maintenance_uri))
    g.add((project_uri, MMV.hasMappingArtifact, artifact_uri))
    g.add((project_uri, MMV.hasStakeholder, stakeholder_uri))

    # ---- MappingArtifact ----
    g.add((artifact_uri, RDF.type, MMV.MappingArtifact))
    add_lit(artifact_uri, DCTERMS.title, "mappingName")
    add_lit(artifact_uri, MMV.hasDescription, "mappingDescription")
    add_lit(artifact_uri, MMV.hasIdentifier, "mappingURI", datatype=XSD.anyURI)
    add_lit(artifact_uri, MMV.version, "versionNumber")
    vdt = (form_data.get("versionDateTime") or "").strip()
    if vdt:
        dtype = XSD.dateTime if "T" in vdt else XSD.date
        g.add((artifact_uri, MMV.hasVersionDateTime, Literal(vdt, datatype=dtype)))
    add_uri(artifact_uri, PROV.wasRevisionOf, "previousVersionURI")
    add_lit(artifact_uri, MQV.hasMappingType, "mappingType")
    add_lit(artifact_uri, MQV.hasMappingFormat, "mappingFormat")

    # ---- Stakeholder ----
    g.add((stakeholder_uri, RDF.type, FOAF.Person))
    fname = (form_data.get("fname") or "").strip()
    lname = (form_data.get("lname") or "").strip()
    if fname:
        g.add((stakeholder_uri, FOAF.givenName, Literal(fname)))
    if lname:
        g.add((stakeholder_uri, FOAF.familyName, Literal(lname)))
    if fname or lname:
        g.add((stakeholder_uri, FOAF.name, Literal((fname + " " + lname).strip())))
    add_lit(stakeholder_uri, MMV.hasBackground, "background")
    add_lit(stakeholder_uri, MMV.hasRole, "role")
    add_lit(stakeholder_uri, FOAF.organization, "organization")
    add_uri(stakeholder_uri, FOAF.homepage, "homepage")

    # ---- AnalysisActivity ----
    g.add((analysis_uri, RDF.type, MMV.AnalysisActivity))
    add_lit(analysis_uri, MMV.hasPurpose, "purpose")
    add_lit(analysis_uri, MMV.hasMappingDomain, "mappingDomain")
    add_lit(analysis_uri, MMV.hasRequirement, "requirementDetails")
    add_lit(analysis_uri, MMV.hasAssumption, "mappingAssumptions")
    add_lit(analysis_uri, MMV.hasDomainAssumption, "domainAssumption")
    add_lit(analysis_uri, MMV.hasTechnicalRequirement, "technicalRequirement")
    add_lit(analysis_uri, MMV.hasRiskOrIssue, "risksIssues")

    input_keys = [
        "inputName",
        "inputDescription",
        "inputSource",
        "inputCreator",
        "inputType",
        "inputFormat",
    ]
    if any((form_data.get(k) or "").strip() for k in input_keys):
        g.add((analysis_uri, MMV.hasInput, input_uri))
        g.add((input_uri, RDF.type, MMV.DataSet))
        add_lit(analysis_uri, MMV.hasInputName, "inputName")
        add_lit(analysis_uri, MMV.hasInputDescription, "inputDescription")
        add_lit(analysis_uri, MMV.hasInputSource, "inputSource")
        add_lit(analysis_uri, MMV.hasInputCreator, "inputCreator")
        add_lit(analysis_uri, MMV.hasInputType, "inputType")
        add_lit(analysis_uri, MMV.hasInputFormat, "inputFormat")

    # ---- DesignActivity ----
    g.add((design_uri, RDF.type, MMV.DesignActivity))
    add_lit(design_uri, MMV.hasDesignDecision, "finalDesignDecisions")
    add_lit(design_uri, MMV.hasJustification, "designDecisionJustification")
    qm = (form_data.get("qualityMetrics") or "").strip()
    if qm:
        g.add((metric_uri, RDF.type, DQV.Metric))
        g.add((metric_uri, DCTERMS.title, Literal(qm)))
        g.add((design_uri, MMV.hasPlannedQualityMetric, metric_uri))

    # ---- DevelopmentActivity ----
    g.add((development_uri, RDF.type, MMV.DevelopmentActivity))
    add_lit(development_uri, PROV.startedAtTime, "StartDate", datatype=XSD.date)
    add_lit(development_uri, PROV.endedAtTime, "EndDate", datatype=XSD.date)
    add_lit(development_uri, MMV.hasTool, "Tool")
    add_lit(development_uri, MQV.hasMappingMethod, "MappingMethod")
    add_lit(development_uri, MQV.hasMappingType, "mappingType")
    add_lit(development_uri, MQV.hasMappingFormat, "mappingFormat")
    add_lit(development_uri, MMV.hasMappingAlgorithm, "mappingAlgorithm")

    # ---- TestingActivity ----
    g.add((testing_uri, RDF.type, MMV.TestingActivity))
    add_lit(testing_uri, MMV.hasTestingType, "testingType")
    add_lit(testing_uri, PROV.generatedAtTime, "testingDate", datatype=XSD.date)
    add_lit(testing_uri, MMV.hasTestingResult, "testingResult")
    vr_url = (form_data.get("validationReportURL") or "").strip()
    if vr_url:
        g.add((report_uri, RDF.type, MMV.ValidationReport))
        g.add((report_uri, DCTERMS.identifier, URIRef(vr_url)))
        add_lit(report_uri, DCTERMS.description, "validationReportDescription")
        g.add((testing_uri, MMV.hasValidationReport, report_uri))

    # ---- MaintenanceActivity ----
    g.add((maintenance_uri, RDF.type, MMV.MaintenanceActivity))
    add_lit(maintenance_uri, MMV.hasPublisherName, "publisherName")
    add_lit(
        maintenance_uri, MMV.hasPublisherSource, "publisherSource", datatype=XSD.anyURI
    )


def _bind_v02_prefixes(graph_or_dataset):
    """Bind MMV v0.2 prefixes for nicer serialisation."""
    graph_or_dataset.bind("mmv", Namespace("http://w3id.org/mmv/0.2#"))
    graph_or_dataset.bind("mqv", Namespace("https://alex-randles.github.io/MQV/#"))
    graph_or_dataset.bind("prov", Namespace("http://www.w3.org/ns/prov#"))
    graph_or_dataset.bind("dqv", Namespace("http://www.w3.org/ns/dqv#"))
    graph_or_dataset.bind("dcterms", Namespace("http://purl.org/dc/terms/"))
    graph_or_dataset.bind("foaf", Namespace("http://xmlns.com/foaf/0.1/"))
    graph_or_dataset.bind("ex", Namespace("http://example.org/mmv-instance/"))


@app.route("/v2_annotate", methods=["GET"])
def v2_annotate():
    return render_template("refined_metadata.html")


@app.route("/submit_v2_metadata", methods=["POST"])
def submit_v2_metadata():
    try:
        form_data = request.form

        required = [
            "projectId",
            "projectTitle",
            "mappingType",
            "purpose",
            "mappingDomain",
            "finalDesignDecisions",
            "MappingMethod",
            "testingType",
            "publisherName",
            "versionNumber",
        ]
        missing = [k for k in required if not (form_data.get(k) or "").strip()]
        if missing:
            flash("Missing required field(s): " + ", ".join(missing))
            return render_template("refined_metadata.html")

        # Read user's chosen output format (default to trig)
        output_format = (form_data.get("outputFormat") or "trig").strip().lower()
        if output_format not in ("trig", "turtle"):
            output_format = "trig"

        unique_code = "".join(random.choices(string.digits, k=3)) + random.choice(
            string.ascii_uppercase
        )
        timestamp = time.strftime("%Y%m%d%H%M%S")
        pid_slug = _slug(form_data.get("projectId", "project"))

        EX = Namespace("http://example.org/mmv-instance/")
        graph_iri_str = None

        if output_format == "trig":
            # Named Graph: use Dataset, place triples in a named graph
            ds = Dataset()
            _bind_v02_prefixes(ds)
            graph_iri = URIRef(str(EX[pid_slug]) + "/graph")
            graph_iri_str = str(graph_iri)
            named_graph = ds.graph(graph_iri)
            _build_v02_triples(form_data, named_graph, EX)

            rdf_data = ds.serialize(format="trig")
            ext = "trig"
            display_format = "Named Graph (TriG, MMV v0.2)"
            gcs_subdir = "v2_named_graphs"
        else:
            # Single-graph Turtle
            g = Graph()
            _bind_v02_prefixes(g)
            _build_v02_triples(form_data, g, EX)

            rdf_data = g.serialize(format="turtle")
            ext = "ttl"
            display_format = "Single-graph Turtle (MMV v0.2)"
            gcs_subdir = "v2_turtle"

        filename = f"mmv_v02_{pid_slug}_{timestamp}_{unique_code}.{ext}"
        out_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rdf_data)

        try:
            bucket_name = "s123r123"
            upload_to_gcs(bucket_name, out_path, f"{gcs_subdir}/{filename}")
        except Exception as gcs_err:
            print("⚠️ GCS upload skipped:", gcs_err)

        return render_template(
            "refined_success.html",
            rdf_data_path_named_graph=out_path,
            unique_code=unique_code,
            graph_iri=graph_iri_str,
            display_format=display_format,
            file_extension=ext,
        )

    except Exception:
        traceback.print_exc()
        flash("An error occurred while generating the metadata. Please try again.")
        return render_template("refined_metadata.html")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False,
        use_reloader=False,
    )
