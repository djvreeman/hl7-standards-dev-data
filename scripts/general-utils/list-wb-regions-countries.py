#!/usr/bin/env python3
import argparse
import sys
import wbgapi as wb
import subprocess
import re

def main():
    parser = argparse.ArgumentParser(
        description='List all World Bank regions and countries.'
    )
    parser.add_argument('--csv', action='store_true', help='Output in CSV format (comma-separated)')
    parser.add_argument('--tsv', action='store_true', help='Output in TSV format (tab-separated)')
    parser.add_argument('-o', '--output', help='Save output to a file')
    parser.add_argument('-c', '--clipboard', action='store_true', help='Copy output to clipboard (Mac only)')
    parser.add_argument('--by-region', action='store_true', help='Group countries by region')
    parser.add_argument('--regions-only', action='store_true', help='List only regions, not countries')
    parser.add_argument('--debug', action='store_true', help='Print debug information')
    args = parser.parse_args()
    
    # Determine delimiter - default to tab unless CSV specified
    delimiter = "\t"  # Default is tab
    if args.csv:
        delimiter = ","
    
    try:
        # Define standard World Bank regions and their codes
        # This is a fallback in case API calls don't work properly
        standard_regions = {
            'EAS': 'East Asia & Pacific',
            'ECS': 'Europe & Central Asia',
            'LCN': 'Latin America & Caribbean',
            'MEA': 'Middle East & North Africa',
            'NAC': 'North America',
            'SAS': 'South Asia',
            'SSF': 'Sub-Saharan Africa',
            # Add numeric codes as well for compatibility
            '1': 'East Asia & Pacific',
            '2': 'Europe & Central Asia',
            '3': 'Latin America & Caribbean',
            '4': 'Middle East & North Africa',
            '6': 'North America',
            '8': 'South Asia',
            '9': 'Sub-Saharan Africa'
        }
        
        # Attempt to get regions from API
        api_regions = {}
        try:
            regions_list = list(wb.region.list())
            if args.debug:
                print(f"Found {len(regions_list)} regions from API", file=sys.stderr)
            
            for r in regions_list:
                # Handle different ways the API might return region data
                region_id = None
                region_name = None
                
                if hasattr(r, 'id') and hasattr(r, 'name'):
                    region_id = r.id
                    region_name = r.name
                elif isinstance(r, dict) and 'id' in r and 'name' in r:
                    region_id = r['id']
                    region_name = r['name']
                
                if region_id and region_name:
                    api_regions[region_id] = region_name
            
            if args.debug:
                print(f"Mapped {len(api_regions)} regions from API", file=sys.stderr)
        except Exception as e:
            if args.debug:
                print(f"Error getting regions from API: {e}", file=sys.stderr)
            api_regions = {}
        
        # Combine API regions with standard regions, with API taking precedence
        regions = {**standard_regions, **api_regions}
        
        if args.debug:
            print(f"Final regions map: {regions}", file=sys.stderr)
        
        # If we only want to list regions
        if args.regions_only:
            output_lines = []
            
            # Add header
            output_lines.append(f"Region ID{delimiter}Region Name")
            
            # Add each region
            for region_id, region_name in sorted(regions.items()):
                output_lines.append(f"{region_id}{delimiter}{region_name}")
            
            # Join all lines
            output_content = "\n".join(output_lines)
        
        # Otherwise, list all countries (optionally grouped by region)
        else:
            # Get all countries
            countries_df = wb.economy.DataFrame()
            
            if args.debug:
                print(f"Found {len(countries_df)} entries", file=sys.stderr)
            
            # Filter for actual countries (not aggregates, regions, or income groups)
            # ISO3 country codes are 3 uppercase letters
            country_pattern = re.compile(r'^[A-Z]{3}$')
            
            # Special cases to exclude - aggregates, income groups, etc.
            exclude_codes = {
                'WLD',  # World
                'LIC', 'LMC', 'UMC', 'HIC',  # Income groups
                'IBD', 'IBT', 'IDB', 'IDX',  # IDA/IBRD groupings
                'LDC', 'MIC',  # Other common aggregates
                'EMU', 'SST', 'XKX',  # Economic/special regions
                'AFE', 'AFW', 'ARB', 'CEB', 'CSS', 'EAR', 'EAP', 'ECA', 'EUU', 'FCS',
                'HPC', 'IDA', 'LAC', 'LMY', 'LTE', 'MNA', 'OED', 'OSS', 'PSS', 'PST',
                'PRE', 'SSA', 'TEA', 'TEC', 'TLA', 'TMN', 'TSA', 'TSS'
            }
            
            # Create a list of valid countries with region mapping
            valid_countries = []
            for iso3, country_data in countries_df.iterrows():
                # Skip if not a standard ISO3 code or in exclusion list
                if not country_pattern.match(iso3) or iso3 in exclude_codes:
                    if args.debug:
                        print(f"Skipping: {iso3}", file=sys.stderr)
                    continue
                
                country_name = country_data.get('name', "Unknown")
                
                # Extract region code based on different possible formats
                region_id = None
                if hasattr(country_data, 'region'):
                    if isinstance(country_data.region, str):
                        region_id = country_data.region
                    elif isinstance(country_data.region, dict) and 'id' in country_data.region:
                        region_id = country_data.region['id']
                    elif hasattr(country_data.region, 'id'):
                        region_id = country_data.region.id
                
                # If we can't determine the region, try using the first digit of the ISO3 code
                # as a fallback (this is a heuristic)
                if not region_id or region_id not in regions:
                    # Try to get the region from a property called 'regionID' if it exists
                    if hasattr(country_data, 'regionID'):
                        region_id = str(country_data.regionID)
                    # Check if there's a region property
                    elif hasattr(country_data, 'Region'):
                        region_id = str(country_data.Region)
                    
                # Get region name
                region_name = regions.get(region_id, "Unknown Region")
                
                # Add to valid countries list
                valid_countries.append((iso3, country_name, region_id, region_name))
            
            if args.debug:
                print(f"Valid countries: {len(valid_countries)}", file=sys.stderr)
            
            # If grouping by region
            if args.by_region:
                output_lines = []
                # Dictionary to group countries by region
                region_countries = {}
                
                # Group countries by region
                for iso3, country_name, region_id, region_name in valid_countries:
                    if region_name not in region_countries:
                        region_countries[region_name] = []
                    region_countries[region_name].append((iso3, country_name))
                
                # Generate output with region headers
                for region_name, country_list in sorted(region_countries.items()):
                    region_id = "N/A"
                    for rid, rname in regions.items():
                        if rname == region_name:
                            region_id = rid
                            break
                    
                    output_lines.append(f"Region: {region_name} ({region_id})")
                    
                    # Add countries in this region (sorted alphabetically by name)
                    for iso3, country_name in sorted(country_list, key=lambda x: x[1]):
                        output_lines.append(f"{country_name}{delimiter}{iso3}")
                    
                    # Add blank line between regions
                    output_lines.append("")
                
                # Join all lines
                output_content = "\n".join(output_lines).strip()
                
            # List all countries without grouping
            else:
                output_lines = []
                # Add header row
                output_lines.append(f"WBG Name{delimiter}ISO3 Code{delimiter}World Bank Region")
                
                # Add each country (sorted alphabetically by name)
                for iso3, country_name, region_id, region_name in sorted(valid_countries, key=lambda x: x[1]):
                    output_lines.append(f"{country_name}{delimiter}{iso3}{delimiter}{region_name}")
                
                # Join all lines
                output_content = "\n".join(output_lines)
        
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