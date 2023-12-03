# HL7 Data Gathering Scripts


fetch-parse-fhir-ig-list-and-all-editions-onecsv.py

fhir-ecosystem-json-parser.py

github-release-csv-cleanup.py

github-release-json-to-csv.py

parse-builds-web.py

 [parse-jira-filter-export-csv-md.py](scripts/parse-jira-filter-export-csv-md.py) 

parse-jiracommenters-unique-csv.py

parse-jiraresolvedissues-csv-for-totals.py

parse-package-list-json-to-csv.py

plot-ig-builder-auto-dynamic.py

standups.hl7.org-json-to-csv.py

# Dependencies
Python3
pip

## Installing Python on Mac (DV method)
- Install [Homebrew](https://brew.sh/)
- Use Homebew to install `python3` since the system version of python on mac is 2.N. This should also install `pip3`
```
export PATH="/usr/local/opt/python/libexec/bin:$PATH"
brew install python
```

## Python Packages Needed

The following modules are used in these scripts, but are part of the Python Standard Library and should be available by default:

- argparse
- csv
- datetime
- getopt
- getpass
- json
- re
- sys
- urllib (and its submodules: request)
- collections
- pprint

If you run a script and encounter an `ImportError`, it will indicate if any additional packages need to be installed. 

You can install packages with pip3 like this:

```
python3 -m pip install -U {package-name}
```

