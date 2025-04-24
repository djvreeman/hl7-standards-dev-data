import argparse
import requests
import sys
import os

def get_json(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def ig_to_ris(ig_json, tags=None):
    tags = tags or []
    title = ig_json.get("title", "Untitled")
    authors = [c.get("name") for c in ig_json.get("contact", []) if "name" in c]
    publisher = ig_json.get("publisher", "Unknown Publisher")
    year = ig_json.get("date", "")[:4]
    version = ig_json.get("version", "")
    url = ig_json.get("url", "")
    package_id = ig_json.get("packageId", "")
    country = ig_json.get("jurisdiction", [{}])[0].get("coding", [{}])[0].get("display", "Unknown")

    ris_lines = [
        "TY  - STD",
        f"TI  - {title}",
        f"T2  - {package_id}",
        f"PY  - {year}",
        f"PB  - {publisher}",
        f"UR  - {url}",
        f"VL  - {version}",
        f"CY  - {country}",
    ]
    for author in authors:
        ris_lines.append(f"AU  - {author}")
    for tag in tags:
        ris_lines.append(f"KW  - {tag}")
    ris_lines.append("ER  -")
    return "\n".join(ris_lines)

def ig_to_bibtex(ig_json, tags=None):
    tags = tags or []
    title = ig_json.get("title", "Untitled")
    authors = [c.get("name") for c in ig_json.get("contact", []) if "name" in c]
    publisher = ig_json.get("publisher", "Unknown Publisher")
    year = ig_json.get("date", "")[:4]
    version = ig_json.get("version", "")
    url = ig_json.get("url", "")
    package_id = ig_json.get("packageId", "unknown")

    bibtex = [
        f"@misc{{{package_id},",
        f"  title={{ {title} }},",
        f"  author={{ {' and '.join(authors)} }},",
        f"  year={{ {year} }},",
        f"  version={{ {version} }},",
        f"  howpublished={{\\url{{{url}}} }},",
        f"  publisher={{ {publisher} }},"
    ]
    if tags:
        bibtex.append(f"  keywords={{ {', '.join(tags)} }},")
    # Remove trailing comma from last entry
    if bibtex[-1].endswith(","):
        bibtex[-1] = bibtex[-1][:-1]
    bibtex.append("}")
    return "\n".join(bibtex)

def main():
    parser = argparse.ArgumentParser(description="Export FHIR IG metadata as RIS or BibTeX.")
    parser.add_argument("-url", required=True, help="Base URL of the FHIR Implementation Guide")
    parser.add_argument("-o-type", choices=["ris", "bibtex"], default="ris", help="Output type (ris or bibtex)")
    parser.add_argument("-o", help="Output file path or directory (optional)")
    parser.add_argument("-tags", help="Comma-separated list of tags (e.g. FHIR,regulatory,EU)", default="")

    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    output_type = args.o_type
    output_path = args.o
    tags = [tag.strip() for tag in args.tags.split(",")] if args.tags else []

    try:
        package_list = get_json(f"{base_url}/package-list.json")
        canonical = package_list.get("canonical", base_url)
        package_id = package_list.get("package-id")
        if not package_id:
            raise ValueError("package-id not found in package-list.json")

        ig_url = f"{canonical}/ImplementationGuide-{package_id}.json"
        ig_json = get_json(ig_url)

        if output_type == "ris":
            result = ig_to_ris(ig_json, tags)
        else:
            result = ig_to_bibtex(ig_json, tags)

        if output_path:
            # If it's a directory or a path with no extension, treat as folder
            if os.path.isdir(output_path) or not os.path.splitext(output_path)[1]:
                os.makedirs(output_path, exist_ok=True)
                output_path = os.path.join(output_path, f"{package_id}.{output_type}")
            else:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"✅ Output written to {output_path}")
        else:
            print(result)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()