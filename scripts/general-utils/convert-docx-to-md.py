"""
docx_to_markdown.py

This script converts Microsoft Word (.docx) files to Markdown (.md) format,
preserving basic structure such as:

- Numbered and unnumbered headings (Heading 1, Heading 2, Heading 3, etc.)
- Bulleted and numbered lists
- Regular paragraph text

Temporary Word files (starting with '~$') are automatically skipped.

Usage:
    python docx_to_markdown.py INPUT_PATH [INPUT_PATH2 ...] --output OUTPUT_FOLDER

Arguments:
    INPUT_PATH         One or more paths to .docx files or folders containing .docx files.
    --output, -o       (Optional) Output folder for the Markdown files (default: ./output).

Examples:
    # Convert a single file
    python docx_to_markdown.py reports/summary.docx --output converted_markdown/

    # Convert all .docx files in a folder
    python docx_to_markdown.py reports/ --output converted_markdown/

    # Convert multiple files and folders
    python docx_to_markdown.py reports/ notes/ file.docx --output output_folder/

Requirements:
    - Python 3.7+
    - python-docx package (install via: pip install python-docx)

Notes:
    - Only .docx files are processed (not .doc, .pdf, etc.).
    - The script handles headings, lists, and paragraphs, but not images or tables.
    - Output folder is created automatically if it does not exist.
    - Subfolders inside input folders are processed recursively.

"""

import os
from docx import Document
import argparse

def convert_docx_with_numbered_headings(docx_path, output_path):
    """
    Convert a .docx file to Markdown format, preserving numbered headings and subtitles.

    :param docx_path: Path to the input .docx file
    :param output_path: Path to save the converted Markdown file
    :return: Path to the converted Markdown file
    """
    # Load the document
    doc = Document(docx_path)
    markdown_content = ""

    # Process paragraphs for styles
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        style = paragraph.style.name

        # Check for numbered headings and add them as Markdown headings
        if text and (text[0].isdigit() and '.' in text[:5]):  # Identify headings with numbers
            if style.startswith("Heading 1"):
                markdown_content += f"# {text}\n\n"
            elif style.startswith("Heading 2"):
                markdown_content += f"## {text}\n\n"
            elif style.startswith("Heading 3"):
                markdown_content += f"### {text}\n\n"
            else:
                markdown_content += f"#### {text}\n\n"
        elif style.startswith("Heading"):
            # Handle non-numbered headings
            if style.startswith("Heading 1"):
                markdown_content += f"# {text}\n\n"
            elif style.startswith("Heading 2"):
                markdown_content += f"## {text}\n\n"
            elif style.startswith("Heading 3"):
                markdown_content += f"### {text}\n\n"
            else:
                markdown_content += f"#### {text}\n\n"
        elif style.startswith("List"):
            markdown_content += f"- {text}\n"
        elif style.startswith("Numbered"):
            markdown_content += f"1. {text}\n"
        else:
            markdown_content += f"{text}\n\n"

    # Save the Markdown to a file
    with open(output_path, "w") as output_file:
        output_file.write(markdown_content)

    return output_path


def process_file(filepath, output_folder):
    """
    Process a single .docx file and convert it to Markdown.

    :param filepath: Path to the input .docx file
    :param output_folder: Folder to save the converted Markdown file
    """
    if not filepath.lower().endswith(".docx"):
        print(f"Skipping non-docx file: {filepath}")
        return

    # Skip temporary files
    if os.path.basename(filepath).startswith("~$"):
        print(f"Skipping temporary file: {filepath}")
        return

    # Generate the output file path
    filename = os.path.splitext(os.path.basename(filepath))[0] + ".md"
    output_path = os.path.join(output_folder, filename)

    try:
        # Convert the file
        print(f"Processing: {filepath}")
        convert_docx_with_numbered_headings(filepath, output_path)
        print(f"Converted to: {output_path}")
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")


def process_folder(folder_path, output_folder):
    """
    Process all .docx files in a folder (including subfolders).

    :param folder_path: Path to the folder containing .docx files
    :param output_folder: Folder to save the converted Markdown files
    """
    for root, _, files in os.walk(folder_path):
        for file in files:
            process_file(os.path.join(root, file), output_folder)


def main(input_paths, output_folder):
    """
    Main function to handle file/folder inputs and convert to Markdown.

    :param input_paths: List of input files or folders
    :param output_folder: Folder to save the converted Markdown files
    """
    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Process each input
    for input_path in input_paths:
        if os.path.isfile(input_path):
            process_file(input_path, output_folder)
        elif os.path.isdir(input_path):
            process_folder(input_path, output_folder)
        else:
            print(f"Invalid input: {input_path}")


if __name__ == "__main__":

    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Convert .docx files to Markdown format.")
    parser.add_argument(
        "inputs",
        metavar="INPUT",
        type=str,
        nargs="+",
        help="Paths to .docx files or folders containing .docx files."
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./output",
        help="Output folder for Markdown files (default: ./output)"
    )

    # Parse arguments and execute
    args = parser.parse_args()
    main(args.inputs, os.path.abspath(args.output))