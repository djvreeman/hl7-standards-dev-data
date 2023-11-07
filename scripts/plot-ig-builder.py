# This script reads the output log of the IG Publisher release build process (either from the filesystem or the URL)
# It parses the time info, converts the millisecond values to seconds (for visualization purposes),
# and then plots the results for each tested IG.
#
# USAGE
# Run it from the command line, providing the path or URL as an argument. 
# For example:
#   python script.py path/to/yourfile.json
# or
#  python script.py https://raw.githubusercontent.com/HL7/fhir-ig-publisher/master/test-statistics.json
# 
# The matplotlib runs in interactive mode, where the use can save the image to a png if they wish.

import argparse
import json
import matplotlib.pyplot as plt
import requests
import sys

def load_json_data(source):
    if source.startswith('http://') or source.startswith('https://'):
        # Fetch the JSON data from a URL
        response = requests.get(source)
        response.raise_for_status()  # Raise an exception if the request failed
        data = response.json()
    else:
        # Load the JSON data from a local file
        with open(source, 'r') as file:
            data = json.load(file)
    return data

def main(source):
    data = load_json_data(source)

    # Prepare data for visualization
    build_times = {}  # Structure to hold the build times

    # Process the JSON data
    for version, guides in data.items():
        if version == 'format-version':
            continue  # Skip the 'format-version' entry

        for guide, stats in guides.items():
            if guide in ['sync-date', 'date']:
                continue  # Skip non-guide entries

            guide_name = guide
            time = stats.get('time', 0) / 1000.0  # Convert milliseconds to seconds

            if guide_name not in build_times:
                build_times[guide_name] = {}
            build_times[guide_name][version] = time

    # Create the visualization
    # Create a figure with a specific size (16x9 inches here) and an axes object
    # Create a figure with the 'constrained_layout' feature enabled.
    fig, ax = plt.subplots(figsize=(16, 9), constrained_layout=True)

    for guide, times in build_times.items():
        sorted_items = sorted(times.items())
        versions = [item[0] for item in sorted_items]
        timings = [item[1] for item in sorted_items]

        ax.plot(versions, timings, marker='o', label=guide)

    # Set labels, legend, etc.
    ax.set_ylabel('Build Time (seconds)')
    ax.set_xlabel('Version')
    ax.set_title('Build Time for each Implementation Guide by Version')

    plt.xticks(rotation=45)  # this still works on the current figure
    plt.tight_layout()  # this affects the current figure, so it's okay

    # If you are saving the figure, use the following command:
    # fig.savefig('output.png', bbox_inches='tight')  # using `fig` instead of `plt`
    plt.show()

if __name__ == "__main__":
    # Set up the command-line argument parser
    parser = argparse.ArgumentParser(description='Visualize FHIR IG Publisher build times.')
    parser.add_argument('source', help='Path to the JSON file or URL to the JSON data')

    # Parse the arguments
    args = parser.parse_args()

    try:
        main(args.source)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)