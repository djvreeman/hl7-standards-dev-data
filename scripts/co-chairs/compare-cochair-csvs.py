import csv
import argparse


def load_contact_ids(filepath):
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return {row['Id']: row for row in reader}


def compare_contacts(file1, file2):
    contacts1 = load_contact_ids(file1)
    contacts2 = load_contact_ids(file2)

    only_in_file1 = {cid: contact for cid, contact in contacts1.items() if cid not in contacts2}
    only_in_file2 = {cid: contact for cid, contact in contacts2.items() if cid not in contacts1}

    return only_in_file1, only_in_file2


def print_differences(only_in_file1, only_in_file2, label1, label2):
    print(f"\nContacts only in {label1} ({len(only_in_file1)}):")
    for contact in only_in_file1.values():
        print(f"  {contact['Id']} | {contact['Name']} | {contact['Email']}")

    print(f"\nContacts only in {label2} ({len(only_in_file2)}):")
    for contact in only_in_file2.values():
        print(f"  {contact['Id']} | {contact['Name']} | {contact['Email']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f1', '--file1', required=True, help='Path to first CSV file')
    parser.add_argument('-f2', '--file2', required=True, help='Path to second CSV file')
    parser.add_argument('-l1', '--label1', default='File 1', help='Label for first file')
    parser.add_argument('-l2', '--label2', default='File 2', help='Label for second file')
    args = parser.parse_args()

    only_in_file1, only_in_file2 = compare_contacts(args.file1, args.file2)
    print_differences(only_in_file1, only_in_file2, args.label1, args.label2)

if __name__ == '__main__':
    main()