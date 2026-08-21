#!/usr/bin/env python3
"""
Test the mermaid_to_drawio repository approach
"""

import sys
import os
sys.path.append('/tmp/mermaid_to_drawio')

from mermaid_drawio import mermaid_to_drawio

def test_repo_converter():
    """Test the mermaid_to_drawio repository converter"""
    
    # Read the Mermaid file
    mermaid_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow.mermaid"
    
    with open(mermaid_file, 'r') as f:
        mermaid_content = f.read()
    
    print("Testing mermaid_to_drawio repository converter...")
    
    try:
        # Convert using the repository's method
        drawio_xml_base64 = mermaid_to_drawio(mermaid_content)
        
        # Decode and save the XML
        import base64
        import zlib
        
        # Decode the base64
        compressed_xml = base64.b64decode(drawio_xml_base64)
        
        # Decompress the XML
        xml_content = zlib.decompress(compressed_xml, -15).decode('utf-8')
        
        # Save the XML file
        output_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow_repo.xml"
        
        with open(output_file, 'w') as f:
            f.write(xml_content)
        
        print(f"Repository conversion saved: {output_file}")
        
        # Generate draw.io URL
        drawio_url = f"https://app.diagrams.net/?splash=0&clibs=U&lang=en#R{drawio_xml_base64}"
        print(f"Draw.io URL: {drawio_url}")
        
        return True
        
    except Exception as e:
        print(f"Error with repository converter: {e}")
        return False

if __name__ == "__main__":
    test_repo_converter()

