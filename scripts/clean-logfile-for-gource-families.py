
#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
import argparse

def clean_and_reformat_data(input_file, output_file):
    with open(input_file, 'r') as file:
        lines = file.readlines()[1:]  # Skip the header

    with open(output_file, 'w') as output:
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) > 1:  # Check if there's a specification field
                spec = parts[-1]
                prefix = spec.split('-')[0]
                parts[-1] = 'HL7/' + prefix + '/' + spec  # Reformat the specification field
                
                # Determine the new field value based on specification prefix
                if prefix.startswith("FHIR"):
                    new_field = "ad1f2f"
                elif prefix.startswith("CDA"):
                    new_field = "2E8B57"
                elif prefix.startswith("V2"):
                    new_field = "005a8c"
                elif prefix.startswith("OTHER"):
                    new_field = "D36621"
                else:
                    new_field = ""
                
                parts.append(new_field)  # Add the new field
                
            output.write('|'.join(parts) + '\n')

def main():
    parser = argparse.ArgumentParser(description="Cleans and reformats a '|' delimited data file.")
    parser.add_argument("-i", "--input_file", required=True, help="Path to the input file")
    parser.add_argument("-o", "--output_file", required=True, help="Path to the output file")
    args = parser.parse_args()
    
    clean_and_reformat_data(args.input_file, args.output_file)

if __name__ == "__main__":
    main()