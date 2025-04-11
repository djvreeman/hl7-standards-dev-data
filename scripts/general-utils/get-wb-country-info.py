#!/usr/bin/env python3
import argparse
import sys
import wbgapi as wb
import subprocess
from difflib import get_close_matches

def main():
    parser = argparse.ArgumentParser(
        description='Resolve a common country name to World Bank name, ISO3 code, and region.'
    )
    # Use nargs='+' to accept one or more arguments for country name without quotes
    parser.add_argument('country', nargs='+', help='Common name of the country to look up (no quotes needed)')
    parser.add_argument('--csv', action='store_true', help='Output in CSV format (comma-separated)')
    parser.add_argument('--tsv', action='store_true', help='Output in TSV format (tab-separated)')
    parser.add_argument('-o', '--output', help='Save output to a file')
    parser.add_argument('-c', '--clipboard', action='store_true', help='Copy output to clipboard (Mac only)')
    parser.add_argument('--header', action='store_true', help='Include header row in output')
    parser.add_argument('--debug', action='store_true', help='Print debug information')
    args = parser.parse_args()
    
    # Join the country arguments into a single string
    search_name = ' '.join(args.country).strip()
    
    # Determine delimiter - default to tab unless CSV specified
    delimiter = "\t"  # Default is tab
    if args.csv:
        delimiter = ","
    
    try:
        # Map of World Bank region codes to full names
        # This is a fallback in case we can't get the region name from the API
        region_map = {
            'EAS': 'East Asia & Pacific',
            'ECS': 'Europe & Central Asia',
            'LCN': 'Latin America & Caribbean',
            'MEA': 'Middle East & North Africa',
            'NAC': 'North America',
            'SAS': 'South Asia',
            'SSF': 'Sub-Saharan Africa'
        }
        
        # Try to get official region names from the API
        api_regions_successful = True
        try:
            regions_list = list(wb.region.list())
            for r in regions_list:
                if hasattr(r, 'id') and hasattr(r, 'name'):
                    region_map[r.id] = r.name
                elif isinstance(r, dict) and 'id' in r and 'name' in r:
                    region_map[r['id']] = r['name']
        except Exception as e:
            api_regions_successful = False
            print(f"Warning: Could not get region list from API: {e}", file=sys.stderr)
        
        if args.debug:
            print(f"Region map: {region_map}", file=sys.stderr)
            if api_regions_successful:
                print("Successfully retrieved regions from API", file=sys.stderr)
            else:
                print("Using fallback region mapping", file=sys.stderr)
        
        # Use the economy.coder function to match the country name
        countries_dict = wb.economy.coder([search_name])
        
        if not countries_dict or search_name not in countries_dict:
            print(f"Error: Could not find a match for '{search_name}'.", file=sys.stderr)
            sys.exit(1)
        
        # Get the ISO3 code for the matched country
        iso3_code = countries_dict[search_name]
        
        if args.debug:
            print(f"Found ISO3 code: {iso3_code}", file=sys.stderr)
        
        # Use the DataFrame approach to get country data
        country_df = wb.economy.DataFrame()
        
        if iso3_code not in country_df.index:
            print(f"Error: Could not find country data for '{iso3_code}'.", file=sys.stderr)
            sys.exit(1)
        
        # Get the country data
        country_series = country_df.loc[iso3_code]
        
        # Extract country name
        country_name = country_series.get('name', search_name)
        
        # Extract region code
        region_id = country_series.get('region', None)
        if isinstance(region_id, dict) and 'id' in region_id:
            region_id = region_id['id']
        
        # Look up region name
        region_name = "Unknown Region"
        if region_id in region_map:
            region_name = region_map[region_id]
        elif not api_regions_successful:
            # We couldn't get regions from API and it's not in our fallback map
            print(f"Warning: Could not determine region name for code '{region_id}'.", file=sys.stderr)
        
        # Prepare the output data
        if args.header:
            header_row = f"WBG Name{delimiter}ISO3 Code{delimiter}World Bank Region"
        
        data_row = f"{country_name}{delimiter}{iso3_code}{delimiter}{region_name}"
        
        # Complete output content
        output_content = ""
        if args.header:
            output_content = header_row + "\n"
        output_content += data_row
        
        # Handle file output if specified
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_content + "\n")
            print(f"Results saved to {args.output}", file=sys.stderr)
        
        # Handle clipboard (macOS only)
        if args.clipboard:
            try:
                # Use pbcopy for Mac clipboard
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                process.communicate(output_content.encode())
                print("Results copied to clipboard!", file=sys.stderr)
            except Exception as e:
                print(f"Error copying to clipboard: {e}", file=sys.stderr)
        
        # Print to stdout if not redirecting to file or clipboard only
        if not (args.output and args.clipboard):
            print(output_content)
        
    except Exception as e:
        print(f"Error: An unexpected error occurred: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()