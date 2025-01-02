import PyPDF2
import re
import argparse

def count_words_in_pdf(pdf_path):
    word_count = 0
    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page_num in range(len(pdf_reader.pages)):
            page_text = pdf_reader.pages[page_num].extract_text()
            if page_text:
                words = re.findall(r'\b\w+\b', page_text)
                word_count += len(words)
    return word_count

def main():
    parser = argparse.ArgumentParser(description="Count words in a PDF file.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    args = parser.parse_args()
    
    word_count = count_words_in_pdf(args.pdf_path)
    print(f"Word count: {word_count}")

if __name__ == "__main__":
    main()