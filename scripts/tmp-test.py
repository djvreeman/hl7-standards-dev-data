import re

html_snippet = """
<h3>REALM</h3>
<ul style="display: inline-block; margin: 0 0 0 -20px;">
  <li class="box-list">US Realm</li>
</ul>
"""

pattern = r'<h3>\s*REALM\s*</h3>.*?<li[^>]*>(.*?)</li>'
match = re.search(pattern, html_snippet, re.IGNORECASE | re.DOTALL)
if match:
    realm_text = match.group(1).strip()
    print("Extracted:", realm_text)
else:
    print("No match")