import os
import re
from PyPDF2 import PdfReader
from markdownify import markdownify as md

def extract_toc(pdf_text):
    """
    Extract the Table of Contents (TOC) from the document text.
    Matches lines with section numbers, titles, and page numbers.
    """
    toc = []
    toc_pattern = re.compile(r"^(?P<section>\d+(\.\d+)*)(?P<title>.*?)\.+(?P<page>\d+)$")
    for line in pdf_text.splitlines():
        match = toc_pattern.match(line)
        if match:
            section = match.group("section").strip()
            title = match.group("title").strip()
            page = int(match.group("page"))
            toc.append((section, title, page))
    return toc

def clean_text(text):
    """
    Normalize the extracted text for better processing.
    """
    # Join hyphenated words across line breaks
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
    # Remove multiple consecutive line breaks
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()

def insert_headings(content, toc):
    """
    Insert Markdown headings into the content based on the TOC.
    """
    lines = content.splitlines()
    output = []
    toc_index = 0
    toc_length = len(toc)

    for line in lines:
        # Check if the current line matches the next TOC entry
        if toc_index < toc_length:
            section, title, _ = toc[toc_index]
            if line.strip() == f"{section} {title}":  # Exact match
                heading_level = section.count('.') + 1
                output.append(f"{'#' * heading_level} {section} {title}")
                toc_index += 1
                continue  # Skip appending the original line
        output.append(line)

    return "\n".join(output)

def convert_pdf_to_markdown(pdf_path, output_path):
    """
    Convert a PDF to Markdown with TOC-based headings.
    """
    try:
        reader = PdfReader(pdf_path)
        pdf_text = "\n".join([page.extract_text() for page in reader.pages])

        # Extract text before TOC, TOC itself, and the body content
        toc_start_index = pdf_text.lower().find("table of contents")
        toc_end_index = pdf_text.find("Introduction")  # Assuming "Introduction" marks the end of TOC
        before_toc_text = clean_text(pdf_text[:toc_start_index])
        toc_text = pdf_text[toc_start_index:toc_end_index]
        body_text = clean_text(pdf_text[toc_end_index:])

        # Parse TOC
        toc = extract_toc(toc_text)

        # Insert headings into the body content
        content_with_headings = insert_headings(body_text, toc)
        markdown_content = f"{before_toc_text}\n\n{md(content_with_headings)}"

        # Write to output file
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(markdown_content)

        print(f"Converted '{pdf_path}' to '{output_path}' with improved heading insertion.")
    except Exception as e:
        print(f"Error during conversion: {e}")

def process_folder(input_folder, output_folder):
    """
    Process all PDF files in a folder and convert them to Markdown.
    """
    os.makedirs(output_folder, exist_ok=True)
    for file_name in os.listdir(input_folder):
        if file_name.lower().endswith(".pdf"):
            pdf_path = os.path.join(input_folder, file_name)
            output_file_name = f"{os.path.splitext(file_name)[0]}.md"
            output_path = os.path.join(output_folder, output_file_name)
            convert_pdf_to_markdown(pdf_path, output_path)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert PDF files to Markdown format.")
    parser.add_argument("inputs", nargs="+", help="Path to a folder or list of PDF files.")
    parser.add_argument("-o", "--output", default="output", help="Output folder for Markdown files.")

    args = parser.parse_args()

    input_paths = args.inputs
    output_folder = args.output

    os.makedirs(output_folder, exist_ok=True)

    for input_path in input_paths:
        if os.path.isdir(input_path):
            process_folder(input_path, output_folder)
        elif os.path.isfile(input_path) and input_path.lower().endswith(".pdf"):
            output_file_name = f"{os.path.splitext(os.path.basename(input_path))[0]}.md"
            output_path = os.path.join(output_folder, output_file_name)
            convert_pdf_to_markdown(input_path, output_path)
        else:
            print(f"Invalid input: {input_path}")

if __name__ == "__main__":
    main()