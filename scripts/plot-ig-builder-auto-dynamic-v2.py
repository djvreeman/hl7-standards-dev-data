import argparse
import json
import matplotlib.pyplot as plt
import requests
import sys
import os
import numpy as np

def parse_version(version):
    try:
        major, minor, patch = map(int, version.split('.'))
        return major, minor, patch
    except ValueError:
        return (0, 0, 0)

def load_json_data(source):
    if source.startswith('http://') or source.startswith('https://'):
        response = requests.get(source)
        response.raise_for_status()
        data = response.json()
    else:
        with open(source, 'r') as file:
            data = json.load(file)
    return data

def extract_build_times(data):
    build_times = {}
    for version, details in data.items():
        if isinstance(details, dict):
            for key, value in details.items():
                if isinstance(value, dict) and 'time' in value:
                    build_times[f"{version}-{key}"] = value['time']
    return build_times

def plot_data(build_times, output):
    sorted_keys = sorted(build_times.keys(), key=lambda x: build_times[x])
    times = [build_times[key] for key in sorted_keys]
    labels = sorted_keys

    # Calculate dynamic width for the plot
    dynamic_width = max(10, min(30, 0.2 * len(times)))
    plt.figure(figsize=(dynamic_width, 5))
    plt.bar(labels, times, color='blue')
    plt.xlabel('Entries')
    plt.ylabel('Time (ms)')
    plt.title('Build Times for All Entries')
    plt.xticks(rotation=90)
    plt.tight_layout()

    output_dir = os.path.dirname(output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    plt.savefig(output)
    plt.close()

def main(source, output):
    data = load_json_data(source)
    build_times = extract_build_times(data)
    plot_data(build_times, output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Visualize FHIR IG Publisher build times.')
    parser.add_argument('--source', type=str, help='The path or URL to the JSON data source', required=True)
    parser.add_argument('-o', '--output', type=str, help='Output filename with path', required=True)
    args = parser.parse_args()

    try:
        main(args.source, args.output)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
