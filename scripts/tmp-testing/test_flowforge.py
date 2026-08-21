#!/usr/bin/env python3
"""
Test FlowForge library for Mermaid to draw.io conversion
"""

def test_flowforge():
    """Test if FlowForge is available and can convert our Mermaid diagram"""
    try:
        from flowforge import FlowForgeConverter
        import logging
        
        print("FlowForge is available!")
        
        # Read the Mermaid file
        mermaid_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow.mermaid"
        
        with open(mermaid_file, 'r') as f:
            mermaid_content = f.read()
        
        # Initialize converter
        converter = FlowForgeConverter(log_level=logging.INFO, strict_mode=False)
        
        # Convert Mermaid to draw.io
        try:
            drawio_xml = converter.convert_mermaid_to_drawio(mermaid_content)
            
            # Save the result
            output_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow_flowforge.drawio"
            
            with open(output_file, 'w') as f:
                f.write(drawio_xml)
            
            print(f"Successfully converted using FlowForge: {output_file}")
            return True
            
        except Exception as e:
            print(f"Error during conversion: {e}")
            return False
            
    except ImportError:
        print("FlowForge is not installed. Install with: pip install flowforge")
        return False
    except Exception as e:
        print(f"Error importing FlowForge: {e}")
        return False

if __name__ == "__main__":
    test_flowforge()

