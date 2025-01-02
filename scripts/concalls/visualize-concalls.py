import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import argparse
import os

# Set up command-line argument parsing
parser = argparse.ArgumentParser(description="Generate an animation of weekly conference calls over time.")
parser.add_argument("-i", "--input", required=True, help="Path to the input CSV file.")
parser.add_argument("-o", "--output", required=True, help="Path to save the output animation file.")
args = parser.parse_args()

# Validate the input file
if not os.path.exists(args.input):
    raise FileNotFoundError(f"Input file '{args.input}' not found.")

# Validate the output file path
output_dir = os.path.dirname(args.output)
if output_dir and not os.path.exists(output_dir):
    raise FileNotFoundError(f"Output directory '{output_dir}' does not exist.")

# Load data from the input CSV file
data = pd.read_csv(args.input)

# Extract and process the relevant column for date
if 'wg_concall_basestartdate' not in data.columns:
    raise ValueError("Input file must contain 'wg_concall_basestartdate' column.")

# Handle invalid date/time formats gracefully
try:
    data['Date'] = pd.to_datetime(data['wg_concall_basestartdate'], errors='coerce').dt.date
except Exception as e:
    raise ValueError(f"Error parsing dates: {e}")

# Drop rows with invalid dates
data = data.dropna(subset=['Date'])

# Aggregate the data by week
data['Week'] = pd.to_datetime(data['Date']).dt.to_period('W').apply(lambda r: r.start_time)
weekly_calls = data.groupby('Week').size().reset_index(name='Calls')

# Ensure the Week column is datetime and sort by week
weekly_calls['Week'] = pd.to_datetime(weekly_calls['Week'])
weekly_calls = weekly_calls.sort_values('Week')
weekly_calls = weekly_calls.set_index('Week')

# Initialize Matplotlib animation
fig, ax = plt.subplots(figsize=(10, 6))
weeks, counts = [], []

def update(frame):
    """Update function for animation."""
    weeks.append(weekly_calls.index[frame])
    counts.append(weekly_calls['Calls'].iloc[frame])
    ax.clear()
    ax.bar(weeks, counts, color='blue')
    ax.set_xlim(weekly_calls.index[0], weekly_calls.index[-1])
    ax.set_ylim(0, weekly_calls['Calls'].max() + 5)
    ax.set_title(f"Weekly Conference Calls - Week of {weeks[-1].strftime('%Y-%m-%d')}", fontsize=14)
    ax.set_xlabel("Week", fontsize=12)
    ax.set_ylabel("Number of Calls", fontsize=12)
    plt.xticks(rotation=45)

# Create the animation
ani = animation.FuncAnimation(fig, update, frames=len(weekly_calls), repeat=False, interval=200)

# Save animation to the specified output file
ani.save(args.output, writer="ffmpeg", fps=30)

print(f"Animation saved to {args.output}")