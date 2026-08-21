import base64
import json
import re
import requests
import uuid
import tempfile
import os
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from langflow.custom import Component
from langflow.io import BoolInput, DropdownInput, IntInput, Output, SecretStrInput, StrInput, DataInput
from langflow.schema import Data


class DrawIOProcessorComponent(Component):
    display_name = "DrawIO Processor"
    description = "Process Confluence content and convert draw.io macros to PNG images for RAG applications"
    documentation = "Extracts draw.io diagrams from Confluence pages and downloads them directly"
    trace_type = "tool"
    icon = "Image"
    name = "DrawIOProcessor"
    
    inputs = [
        DataInput(
            name="confluence_data",
            display_name="Confluence Data",
            required=True,
            info="Input data from Confluence component",
            is_list=True,
        ),
        StrInput(
            name="confluence_username",
            display_name="Confluence Username",
            required=False,
            info="Username for accessing Confluence attachments (if different from main flow)",
        ),
        SecretStrInput(
            name="confluence_token",
            display_name="Confluence API Token",
            required=False,
            info="API token for accessing Confluence attachments (if different from main flow)",
        ),
        StrInput(
            name="output_directory",
            display_name="Output Directory",
            required=False,
            info="Directory to save PNG files (uses temp directory if empty)",
        ),
        DropdownInput(
            name="processing_mode",
            display_name="Processing Mode",
            options=["extract_and_convert", "extract_only", "text_description"],
            value="extract_and_convert",
            required=True,
            info="How to handle draw.io content",
        ),
        IntInput(
            name="image_width",
            display_name="Image Width",
            value=1500,
            required=False,
            info="Width of exported PNG images in pixels",
        ),
        BoolInput(
            name="include_diagram_text",
            display_name="Include Diagram Text",
            value=True,
            required=False,
            info="Extract text content from diagrams for better RAG performance",
        ),
        BoolInput(
            name="embed_images_base64",
            display_name="Embed Images as Base64",
            value=True,
            required=False,
            info="Embed PNG images as base64 data URIs for direct display",
        ),
        IntInput(
            name="max_image_size_kb",
            display_name="Max Image Size (KB)",
            value=500,
            required=False,
            info="Maximum image size in KB for base64 embedding (0 = no limit)",
        ),
        StrInput(
            name="diagram_context_template",
            display_name="Diagram Context Template",
            value="This is a process diagram titled '{title}' containing: {content}",
            required=False,
            info="Template for wrapping diagram text with context",
        ),
        BoolInput(
            name="create_diagram_chunks",
            display_name="Create Diagram Chunks",
            value=False,
            required=False,
            info="Create separate data chunks for each diagram",
        ),
    ]
    
    outputs = [
        Output(name="processed_data", display_name="Processed Data", method="process_confluence_data"),
    ]
    
    # Debug methods removed for security
    # def debug_credentials(self, data_obj: Data = None):
    #     """Debug credential handling - removed for security"""
    #     pass
    
    def get_document_content(self, data_obj: Data) -> str:
        """Extract document content from Data object, trying multiple sources"""
        content = None
        
        # Method 1: Try data_obj.text (Langflow standard)
        if hasattr(data_obj, 'text') and data_obj.text:
            content = data_obj.text
            print(f"✅ Got content from data_obj.text ({len(content)} chars)")
            return content
        
        # Method 2: Try data_obj.page_content (Langchain standard)
        if hasattr(data_obj, 'page_content') and data_obj.page_content:
            content = data_obj.page_content
            print(f"✅ Got content from data_obj.page_content ({len(content)} chars)")
            return content
        
        # Method 3: Try data dictionary content field
        if hasattr(data_obj, 'data') and data_obj.data:
            data_dict = data_obj.data
            if 'content' in data_dict:
                content = data_dict['content']
                print(f"✅ Got content from data_dict['content'] ({len(content)} chars)")
                return content
            if 'text' in data_dict:
                content = data_dict['text']
                print(f"✅ Got content from data_dict['text'] ({len(content)} chars)")
                return content
        
        # Method 4: Check if the original document object is stored
        if hasattr(data_obj, '_original_document'):
            orig_doc = data_obj._original_document
            if hasattr(orig_doc, 'page_content'):
                content = orig_doc.page_content
                print(f"✅ Got content from original document ({len(content)} chars)")
                return content
        
        # Method 5: Try string conversion as last resort
        content = str(data_obj)
        print(f"⚠️ Fallback to str(data_obj) ({len(content)} chars)")
        return content

    def extract_base64_from_mixed_content(self, content: str) -> List[str]:
        """Extract base64 strings from mixed HTML/text content"""
        base64_strings = []
        
        # Look for base64 patterns that start with common JSON prefixes
        patterns = [
            r'eyJ[A-Za-z0-9+/=]{100,}',  # At least 100 chars long
            r'[A-Za-z0-9+/=]{200,}(?=[^A-Za-z0-9+/=]|$)',  # Any base64 string 200+ chars
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                # Validate it's actually base64 JSON
                try:
                    # Try to decode and parse
                    decoded = base64.b64decode(match).decode('utf-8')
                    json_data = json.loads(decoded)
                    
                    # Check if it looks like draw.io config
                    if ('attId' in json_data or 'diagramName' in json_data or 
                        'drawio' in str(json_data).lower()):
                        print(f"✅ Found valid base64 draw.io data in mixed content ({len(match)} chars)")
                        base64_strings.append(match)
                        
                except Exception:
                    continue
        
        return base64_strings

    def is_base64_json(self, content: str) -> bool:
        """Check if content appears to be base64 encoded JSON"""
        try:
            # Check if it looks like base64
            if not content or len(content) < 10:
                print(f"🔍 Base64 check: Content too short ({len(content)} chars)")
                return False
            
            content_clean = content.strip()
            
            # Quick check: if it starts with eyJ, it's likely base64 JSON
            if content_clean.startswith('eyJ'):
                print(f"🔍 Base64 check: Starts with 'eyJ' - likely base64 JSON")
                try:
                    # Handle potential encoding issues
                    try:
                        decoded = base64.b64decode(content_clean).decode('utf-8')
                    except UnicodeDecodeError:
                        # Try with latin-1 encoding if utf-8 fails
                        decoded = base64.b64decode(content_clean).decode('latin-1')
                    except Exception as e:
                        print(f"❌ Base64 check: Decode failed with error: {e}")
                        return False
                    
                    json.loads(decoded)
                    print(f"✅ Base64 check: Successfully decoded and parsed as JSON")
                    return True
                except json.JSONDecodeError as e:
                    print(f"❌ Base64 check: JSON decode failed - likely truncated data: {e}")
                    print(f"❌ Decoded content preview: {decoded[:200] if 'decoded' in locals() else 'Failed to decode'}...")
                    return False
                except Exception as e:
                    print(f"❌ Base64 check: Failed to decode/parse: {e}")
                    return False
            
            # Check if content contains HTML tags
            if '<' in content_clean and '>' in content_clean:
                print(f"🔍 Base64 check: Contains HTML tags - not base64")
                return False
            
            # Check if it's mostly base64 characters
            import string
            base64_chars = string.ascii_letters + string.digits + '+/='
            non_base64_chars = [c for c in content_clean if c not in base64_chars]
            if len(non_base64_chars) > len(content_clean) * 0.1:  # More than 10% non-base64 chars
                print(f"🔍 Base64 check: Too many non-base64 characters ({len(non_base64_chars)}/{len(content_clean)})")
                return False
            
            # Try to decode
            try:
                try:
                    decoded = base64.b64decode(content_clean).decode('utf-8')
                except UnicodeDecodeError:
                    decoded = base64.b64decode(content_clean).decode('latin-1')
                
                json_data = json.loads(decoded)
                
                # Additional check: does it look like draw.io config?
                if 'diagramName' in json_data or 'attId' in json_data:
                    print(f"✅ Base64 check: Contains draw.io configuration keys")
                    return True
                else:
                    print(f"🔍 Base64 check: Valid JSON but no draw.io keys")
                    return True  # Still might be valid
                    
            except Exception as e:
                print(f"❌ Base64 check: Decode/parse failed: {e}")
                return False
            
        except Exception as e:
            print(f"❌ Base64 check: Unexpected error: {e}")
            return False

    def extract_drawio_from_html(self, html_content: str) -> List[Dict[str, Any]]:
        """Extract draw.io macros from HTML content (traditional method)"""
        soup = BeautifulSoup(html_content, 'html.parser')
        macros = []
        
        # Look for draw.io macro containers
        drawio_containers = soup.find_all('div', class_='conf-macro output-block', 
                                        attrs={'data-macro-name': 'drawio'})
        
        for container in drawio_containers:
            try:
                # Find the macro content div
                macro_div = container.find('div', class_='drawio-macro')
                if not macro_div:
                    continue
                    
                macro_id = macro_div.get('data-macroid', str(uuid.uuid4()))
                
                # Find the hidden data div
                data_div = container.find('div', id=f'drawio-macro-data-{macro_id}')
                if not data_div:
                    data_div = soup.find('div', id=f'drawio-macro-data-{macro_id}')
                    if not data_div:
                        continue
                
                # Extract base64 encoded data
                encoded_data = data_div.get_text().strip()
                if not encoded_data:
                    continue
                
                # Decode the base64 data
                decoded_data = base64.b64decode(encoded_data).decode('utf-8')
                macro_config = json.loads(decoded_data)
                
                macros.append({
                    'macro_id': macro_id,
                    'encoded_data': encoded_data,
                    'config': macro_config,
                    'diagram_name': macro_config.get('diagramName', f'diagram_{macro_id}'),
                    'attachment_id': macro_config.get('attId'),
                    'width': macro_config.get('width', str(self.image_width)),
                    'source': 'html_extraction'
                })
                
            except Exception as e:
                print(f"❌ Error processing HTML container: {e}")
                continue
                
        return macros

    def extract_drawio_from_base64(self, content: str, metadata: dict) -> List[Dict[str, Any]]:
        """Extract draw.io data when content is already base64 encoded JSON"""
        try:
            print(f"🔍 Decoding base64 content ({len(content)} chars)")
            
            # Handle potential encoding issues
            try:
                decoded_data = base64.b64decode(content.strip()).decode('utf-8')
            except UnicodeDecodeError:
                print(f"⚠️ UTF-8 decode failed, trying latin-1")
                decoded_data = base64.b64decode(content.strip()).decode('latin-1')
            except Exception as e:
                print(f"❌ Base64 decode failed: {e}")
                return []
            
            print(f"✅ Decoded to {len(decoded_data)} chars")
            print(f"🔍 Decoded preview: {decoded_data[:200]}...")
            
            try:
                macro_config = json.loads(decoded_data)
                print(f"✅ Parsed JSON with keys: {list(macro_config.keys())}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse failed: {e}")
                print(f"❌ Decoded content causing error: {decoded_data[:500]}...")
                return []
            
            # Check for draw.io specific keys
            diagram_name = macro_config.get('diagramName', 'Unknown')
            attachment_id = macro_config.get('attId')
            
            print(f"📄 Diagram name: {diagram_name}")
            print(f"📎 Attachment ID: {attachment_id}")
            
            if not attachment_id:
                print(f"❌ No attachment ID found in configuration")
                return []
            
            # Create a macro entry
            macro_id = str(uuid.uuid4())
            if not diagram_name or diagram_name == 'Unknown':
                diagram_name = metadata.get('title', f'diagram_{macro_id}')
            
            macro_entry = {
                'macro_id': macro_id,
                'encoded_data': content,
                'config': macro_config,
                'diagram_name': diagram_name,
                'attachment_id': attachment_id,
                'width': macro_config.get('width', str(self.image_width)),
                'source': 'base64_direct'
            }
            
            print(f"✅ Created macro entry for diagram: {diagram_name}")
            return [macro_entry]
            
        except Exception as e:
            print(f"❌ Error processing base64 content: {e}")
            import traceback
            traceback.print_exc()
            return []

    def extract_drawio_macros(self, content: str, metadata: dict, data_dict: dict = None) -> List[Dict[str, Any]]:
        """Extract all draw.io macros from content (handles HTML, base64, and enhanced Confluence data)"""
        
        print(f"🔍 DEBUG: Content length: {len(content)}")
        print(f"🔍 DEBUG: Content preview (first 500 chars):")
        print(content[:500])
        print("=" * 50)
        
        # First, check if we have enhanced draw.io data from the improved Confluence component
        if data_dict and 'drawio_macros' in data_dict:
            print("✅ Found enhanced draw.io macro data from Confluence component")
            enhanced_macros = data_dict['drawio_macros']
            
            processed_macros = []
            for macro in enhanced_macros:
                if isinstance(macro, dict):
                    # Convert enhanced macro format to our standard format
                    processed_macro = {
                        'macro_id': macro.get('macro_id', str(uuid.uuid4())),
                        'diagram_name': macro.get('diagram_name', 'Unknown Diagram'),
                        'attachment_id': macro.get('attachment_id'),
                        'source': 'enhanced_confluence'
                    }
                    
                    # If we have encoded_data, include it
                    if 'encoded_data' in macro:
                        processed_macro['encoded_data'] = macro['encoded_data']
                        
                        # Try to decode and get config
                        try:
                            decoded_data = base64.b64decode(macro['encoded_data']).decode('utf-8')
                            macro_config = json.loads(decoded_data)
                            processed_macro['config'] = macro_config
                            
                            # Get additional info from config
                            if not processed_macro['attachment_id']:
                                processed_macro['attachment_id'] = macro_config.get('attId')
                            if processed_macro['diagram_name'] == 'Unknown Diagram':
                                processed_macro['diagram_name'] = macro_config.get('diagramName', 'Unknown Diagram')
                                
                        except Exception as e:
                            print(f"⚠️ Could not decode enhanced macro data: {e}")
                    
                    processed_macros.append(processed_macro)
            
            print(f"🔍 FINAL RESULT: Found {len(processed_macros)} enhanced draw.io macros")
            return processed_macros
        
        # Check for base64 strings embedded in mixed content
        embedded_base64 = self.extract_base64_from_mixed_content(content)
        if embedded_base64:
            print(f"✅ Found {len(embedded_base64)} base64 strings in mixed content")
            macros = []
            for i, base64_str in enumerate(embedded_base64):
                try:
                    macro_list = self.extract_drawio_from_base64(base64_str, metadata)
                    macros.extend(macro_list)
                except Exception as e:
                    print(f"❌ Error processing embedded base64 {i+1}: {e}")
            
            if macros:
                print(f"🔍 FINAL RESULT: Found {len(macros)} draw.io macros from embedded base64")
                return macros
        
        # Check if content is base64 encoded JSON (from standard Confluence loader)
        if self.is_base64_json(content.strip()):
            print("✅ Detected base64 encoded JSON content")
            macros = self.extract_drawio_from_base64(content.strip(), metadata)
        else:
            print("✅ Detected HTML content, searching for draw.io macros")
            # Check for draw.io patterns in HTML
            drawio_patterns = [
                'drawio-macro',
                'data-macro-name="drawio"',
                'conf-macro output-block',
                'drawio-macro-data-'
            ]
            
            for pattern in drawio_patterns:
                if pattern in content:
                    print(f"✅ Found pattern: {pattern}")
                else:
                    print(f"❌ Missing pattern: {pattern}")
            
            macros = self.extract_drawio_from_html(content)
        
        print(f"🔍 FINAL RESULT: Found {len(macros)} valid draw.io macros")
        return macros

    def get_confluence_credentials(self, data_obj: Data = None) -> tuple:
        """Get Confluence credentials from component settings or data object"""
        # Priority 1: Use component settings if provided
        if self.confluence_username and self.confluence_token:
            return (self.confluence_username, self.confluence_token)
        
        # Priority 2: Extract from data object (passed from Enhanced Confluence component)
        if data_obj and hasattr(data_obj, 'data') and data_obj.data:
            data_dict = data_obj.data
            confluence_username = data_dict.get('confluence_username')
            confluence_token = data_dict.get('confluence_token')
            if confluence_username and confluence_token:
                return (confluence_username, confluence_token)
        
        return None

    def get_confluence_headers(self, data_obj: Data = None) -> dict:
        """Get authentication headers for Confluence API calls"""
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        
        credentials = self.get_confluence_credentials(data_obj)
        if credentials:
            username, token = credentials
            # For Confluence Cloud, use Bearer token authentication
            headers['Authorization'] = f'Bearer {token}'
        
        return headers

    def get_confluence_base_url(self, data_obj: Data) -> str:
        """Extract base URL from Confluence data object"""
        # Priority 1: Get from data object (passed from Enhanced Confluence component)
        if hasattr(data_obj, 'data') and data_obj.data:
            data_dict = data_obj.data
            base_url = data_dict.get('confluence_base_url')
            if base_url:
                print(f"✅ Using base URL from Enhanced Confluence component: {base_url}")
                return base_url
        
        # Priority 2: Try to get from metadata
        metadata = getattr(data_obj, 'metadata', {})
        if not metadata and hasattr(data_obj, 'data') and data_obj.data:
            metadata = data_obj.data.get('metadata', {})
        
        # Look for URL in various metadata fields
        base_url = metadata.get('base_url', '')
        if not base_url:
            source = metadata.get('source', '')
            if source and ('confluence' in source.lower() or 'hl7.org' in source.lower()):
                # Extract base URL from source
                import urllib.parse
                parsed = urllib.parse.urlparse(source)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Fallback - try to extract from any URL-like strings in metadata
        if not base_url:
            for key, value in metadata.items():
                if isinstance(value, str) and ('confluence' in value.lower() or 'hl7.org' in value.lower()):
                    import urllib.parse
                    try:
                        parsed = urllib.parse.urlparse(value)
                        if parsed.scheme and parsed.netloc:
                            base_url = f"{parsed.scheme}://{parsed.netloc}"
                            break
                    except:
                        continue
        
        # Default fallback
        if not base_url:
            base_url = "https://confluence.hl7.org"
            print(f"⚠️ Using default base URL: {base_url}")
        
        return base_url

    def test_confluence_access(self, data_obj: Data) -> bool:
        """Test if we can access Confluence with the current credentials"""
        try:
            base_url = self.get_confluence_base_url(data_obj)
            headers = self.get_confluence_headers(data_obj)
            
            if 'Authorization' not in headers:
                return False
            
            # Test basic API access
            test_url = f"{base_url}/rest/api/space"
            response = requests.get(test_url, headers=headers, timeout=10)
            
            return response.status_code == 200
                
        except Exception as e:
            return False

    def download_diagram_file_from_confluence(self, base_url: str, attachment_id: str, diagram_name: str, output_dir: str, data_obj: Data = None) -> Optional[str]:
        """Download diagram file directly from Confluence (usually PNG or draw.io XML)"""
        if not attachment_id or not base_url:
            print(f"❌ Missing attachment_id ({attachment_id}) or base_url ({base_url})")
            return None
        
        # First test if we can access Confluence at all
        if not self.test_confluence_access(data_obj):
            return None
            
        try:
            headers = self.get_confluence_headers(data_obj)
            
            # Get attachment info first
            attachment_url = f"{base_url}/rest/api/content/{attachment_id}"
            
            print(f"🔍 Fetching attachment info from: {attachment_url}")
            
            response = requests.get(attachment_url, headers=headers, timeout=30)
            
            # Handle different response codes
            if response.status_code == 401:
                print(f"❌ 401 Unauthorized - trying alternative approaches...")
                
                # Try accessing the parent page instead
                if hasattr(data_obj, 'metadata') and data_obj.metadata:
                    page_id = data_obj.metadata.get('id')
                    if page_id:
                        print(f"🔍 Trying to get attachment list from parent page {page_id}")
                        page_url = f"{base_url}/rest/api/content/{page_id}/child/attachment"
                        page_response = requests.get(page_url, headers=headers, timeout=30)
                        
                        if page_response.status_code == 200:
                            print(f"✅ Successfully accessed page attachments")
                            attachments = page_response.json().get('results', [])
                            
                            # Look for our specific attachment
                            for att in attachments:
                                if att.get('id') == attachment_id:
                                    print(f"✅ Found target attachment in page attachment list")
                                    attachment_info = att
                                    break
                            else:
                                print(f"❌ Target attachment {attachment_id} not found in page attachments")
                                return None
                        else:
                            print(f"❌ Could not access page attachments: {page_response.status_code}")
                            return None
                    else:
                        print(f"❌ No page ID available for alternative approach")
                        return None
                else:
                    print(f"❌ No metadata available for alternative approach")
                    return None
            elif response.status_code == 404:
                print(f"❌ 404 Not Found - attachment {attachment_id} does not exist")
                return None
            else:
                response.raise_for_status()
                attachment_info = response.json()
            attachment_title = attachment_info.get('title', 'unknown')
            print(f"✅ Got attachment info for: {attachment_title}")
            
            # Check if this has a download link
            if '_links' not in attachment_info or 'download' not in attachment_info['_links']:
                print(f"❌ No download link found in attachment")
                return None
            
            download_url = attachment_info['_links']['download']
            full_download_url = f"{base_url}{download_url}"
            
            # Create safe filename - handle draw.io files specially
            safe_name = re.sub(r'[^\w\-_.]', '_', diagram_name)
            file_extension = os.path.splitext(attachment_title)[1] if '.' in attachment_title else ''
            
            # If no extension or unknown extension, determine from content
            if not file_extension or file_extension in ['.2', '.tmp']:
                file_extension = '.xml'  # Default for draw.io files
            
            output_filename = f"{safe_name}{file_extension}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Download the file
            print(f"🔍 Downloading diagram from: {full_download_url}")
            print(f"📁 Saving to: {output_path}")
            
            diagram_response = requests.get(full_download_url, headers=headers, timeout=60)
            diagram_response.raise_for_status()
            
            # Check content type and adjust handling
            content_type = diagram_response.headers.get('content-type', '')
            print(f"📄 Content type: {content_type}")
            
            # Check if this is a draw.io XML file
            if ('drawio' in content_type or 
                diagram_response.text.strip().startswith('<mxfile') or
                diagram_response.text.strip().startswith('<?xml')):
                
                print(f"🔍 Detected draw.io XML format")
                
                # Save as XML
                xml_path = output_path.replace(file_extension, '.xml') if file_extension != '.xml' else output_path
                with open(xml_path, 'w', encoding='utf-8') as f:
                    f.write(diagram_response.text)
                
                print(f"💾 Saved draw.io XML: {xml_path}")
                
                # Try to convert to PNG using a different approach
                png_path = xml_path.replace('.xml', '.png')
                if self.convert_drawio_xml_to_png(diagram_response.text, png_path):
                    print(f"✅ Successfully converted XML to PNG: {png_path}")
                    return png_path
                else:
                    print(f"⚠️ Could not convert XML to PNG, returning XML file")
                    return xml_path
                    
            else:
                # Save as binary file (regular image)
                with open(output_path, 'wb') as f:
                    f.write(diagram_response.content)
                
                file_size = len(diagram_response.content)
                print(f"✅ Successfully downloaded diagram file ({file_size} bytes): {output_path}")
                
                if content_type.startswith('image/') or output_filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                    print(f"✅ Downloaded file appears to be an image")
                    return output_path
                else:
                    print(f"⚠️ Downloaded file may not be an image: {content_type}")
                    return output_path
            
        except requests.RequestException as e:
            print(f"❌ Error downloading diagram file: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error downloading diagram: {e}")
            return None
    
    def convert_drawio_xml_to_png(self, xml_content: str, output_path: str) -> bool:
        """Convert draw.io XML to PNG using available methods"""
        try:
            print(f"🔍 Attempting to convert draw.io XML to PNG")
            
            # Method 1: Try using Puppeteer/Chrome headless if available
            if self.try_puppeteer_conversion(xml_content, output_path):
                return True
            
            # Method 2: Try using draw.io desktop export if available
            if self.try_drawio_desktop_conversion(xml_content, output_path):
                return True
            
            # Method 3: Create a simple SVG/HTML representation
            if self.create_html_representation(xml_content, output_path):
                return True
            
            print(f"❌ All conversion methods failed")
            return False
            
        except Exception as e:
            print(f"❌ Error in XML to PNG conversion: {e}")
            return False
    
    def try_puppeteer_conversion(self, xml_content: str, output_path: str) -> bool:
        """Try to convert using Puppeteer/headless Chrome (if available)"""
        try:
            # This would require puppeteer to be installed
            # For now, return False to try other methods
            print(f"⚠️ Puppeteer conversion not implemented")
            return False
        except:
            return False
    
    def try_drawio_desktop_conversion(self, xml_content: str, output_path: str) -> bool:
        """Try to convert using draw.io desktop application (if available)"""
        try:
            import subprocess
            import tempfile
            
            # Check if draw.io desktop is available
            drawio_paths = [
                '/Applications/draw.io.app/Contents/MacOS/draw.io',  # macOS
                'C:\\Program Files\\draw.io\\draw.io.exe',  # Windows
                '/usr/bin/drawio',  # Linux
                'drawio'  # System PATH
            ]
            
            drawio_cmd = None
            for path in drawio_paths:
                try:
                    subprocess.run([path, '--version'], capture_output=True, timeout=5)
                    drawio_cmd = path
                    break
                except:
                    continue
            
            if not drawio_cmd:
                print(f"⚠️ draw.io desktop not found")
                return False
            
            # Create temporary XML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as temp_xml:
                temp_xml.write(xml_content)
                temp_xml_path = temp_xml.name
            
            try:
                # Use draw.io desktop to export
                cmd = [drawio_cmd, '--export', '--format', 'png', '--output', output_path, temp_xml_path]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                
                if result.returncode == 0 and os.path.exists(output_path):
                    print(f"✅ Successfully converted using draw.io desktop")
                    return True
                else:
                    print(f"❌ draw.io desktop conversion failed: {result.stderr.decode()}")
                    return False
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_xml_path)
                except:
                    pass
                    
        except Exception as e:
            print(f"❌ Error in draw.io desktop conversion: {e}")
            return False
    
    def create_html_representation(self, xml_content: str, output_path: str) -> bool:
        """Create an HTML representation of the diagram for viewing"""
        try:
            # Extract basic diagram information
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Get diagram title and basic info
            diagram_info = []
            mxfile = soup.find('mxfile')
            if mxfile:
                diagram_info.append(f"Diagram Host: {mxfile.get('host', 'Unknown')}")
                diagram_info.append(f"Modified: {mxfile.get('modified', 'Unknown')}")
            
            # Extract text content
            text_elements = []
            for cell in soup.find_all('mxCell'):
                value = cell.get('value', '')
                if value and value.strip():
                    clean_text = BeautifulSoup(value, 'html.parser').get_text()
                    if clean_text.strip():
                        text_elements.append(clean_text.strip())
            
            # Create HTML representation
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Draw.io Diagram</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .diagram-info {{ background: #f5f5f5; padding: 10px; margin: 10px 0; }}
                    .text-elements {{ background: #e8f4f8; padding: 10px; margin: 10px 0; }}
                    .element {{ margin: 5px 0; padding: 5px; background: white; border-left: 3px solid #007acc; }}
                </style>
            </head>
            <body>
                <h1>Draw.io Diagram Content</h1>
                <div class="diagram-info">
                    <h3>Diagram Information:</h3>
                    {"<br>".join(diagram_info)}
                </div>
                <div class="text-elements">
                    <h3>Diagram Elements:</h3>
                    {"".join(f'<div class="element">{elem}</div>' for elem in text_elements)}
                </div>
                <details>
                    <summary>Raw XML Content</summary>
                    <pre>{xml_content}</pre>
                </details>
            </body>
            </html>
            """
            
            # Save HTML file
            html_path = output_path.replace('.png', '.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"💾 Created HTML representation: {html_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error creating HTML representation: {e}")
            return False

    def get_diagram_xml_from_confluence(self, base_url: str, attachment_id: str, data_obj: Data = None) -> Optional[str]:
        """Retrieve the actual diagram XML from Confluence attachment for text extraction"""
        if not attachment_id or not base_url:
            print(f"❌ Missing attachment_id ({attachment_id}) or base_url ({base_url})")
            return None
            
        try:
            headers = self.get_confluence_headers(data_obj)
            
            # Get attachment info first
            attachment_url = f"{base_url}/rest/api/content/{attachment_id}"
            
            print(f"🔍 Fetching attachment info from: {attachment_url}")
            
            response = requests.get(attachment_url, headers=headers, timeout=30)
            
            # Handle different response codes
            if response.status_code == 401:
                print(f"❌ 401 Unauthorized - attachment may be private or credentials invalid")
                return None
            elif response.status_code == 404:
                print(f"❌ 404 Not Found - attachment {attachment_id} does not exist")
                return None
            
            response.raise_for_status()
            
            attachment_info = response.json()
            print(f"✅ Got attachment info for: {attachment_info.get('title', 'unknown')}")
            
            # Check if this is actually a draw.io diagram attachment
            if '_links' not in attachment_info or 'download' not in attachment_info['_links']:
                print(f"❌ No download link found in attachment")
                return None
            
            download_url = attachment_info['_links']['download']
            full_download_url = f"{base_url}{download_url}"
            
            # Download the actual diagram file
            print(f"🔍 Downloading diagram from: {full_download_url}")
            diagram_response = requests.get(full_download_url, headers=headers, timeout=30)
            diagram_response.raise_for_status()
            
            # Check if we got XML content
            content_type = diagram_response.headers.get('content-type', '')
            content_text = diagram_response.text.strip()
            
            if not content_text.startswith('<'):
                print(f"⚠️ Downloaded content may not be XML (content-type: {content_type})")
                print(f"⚠️ Content preview: {content_text[:200]}...")
            
            print(f"✅ Successfully downloaded diagram XML ({len(content_text)} chars)")
            return content_text
            
        except requests.RequestException as e:
            print(f"❌ Error retrieving diagram XML: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error retrieving diagram: {e}")
            return None

    def embed_image_as_base64(self, png_path: str) -> Optional[str]:
        """Convert PNG to base64 data URI for embedding"""
        try:
            if not os.path.exists(png_path):
                print(f"❌ PNG file not found: {png_path}")
                return None
                
            # Check file size if limit is set
            if self.max_image_size_kb > 0:
                file_size_kb = os.path.getsize(png_path) / 1024
                if file_size_kb > self.max_image_size_kb:
                    print(f"⚠️ Image {png_path} is {file_size_kb:.1f}KB, exceeds limit of {self.max_image_size_kb}KB")
                    return None
            
            with open(png_path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                data_uri = f"data:image/png;base64,{encoded}"
                print(f"✅ Created base64 data URI ({len(encoded)} chars)")
                return data_uri
                
        except Exception as e:
            print(f"❌ Error encoding image as base64: {e}")
            return None

    def create_image_markdown(self, diagram_name: str, base64_data: str, png_path: str) -> str:
        """Create markdown with embedded image for display"""
        if base64_data:
            return f"![{diagram_name}]({base64_data})"
        else:
            return f"[Image: {diagram_name} - File path: {png_path}]"

    def extract_text_from_diagram_xml(self, diagram_xml: str) -> str:
        """Extract comprehensive text content from draw.io diagram XML for RAG"""
        try:
            soup = BeautifulSoup(diagram_xml, 'xml')
            text_elements = []
            connections = []
            
            # Find all text elements in the diagram
            for cell in soup.find_all('mxCell'):
                value = cell.get('value', '')
                style = cell.get('style', '')
                
                if value and value.strip():
                    # Clean HTML tags if present
                    clean_text = BeautifulSoup(value, 'html.parser').get_text()
                    if clean_text.strip():
                        # Determine if this is a shape, connector, or text
                        if 'edgeStyle' in style or 'curved' in style:
                            connections.append(f"connects: {clean_text.strip()}")
                        else:
                            text_elements.append(clean_text.strip())
            
            # Combine all text with context
            result_parts = []
            if text_elements:
                result_parts.append("Diagram elements: " + " | ".join(text_elements))
            if connections:
                result_parts.append("Connections: " + " | ".join(connections))
            
            extracted_text = " || ".join(result_parts) if result_parts else ''
            print(f"✅ Extracted text from diagram ({len(extracted_text)} chars): {extracted_text[:100]}...")
            return extracted_text
            
        except Exception as e:
            print(f"❌ Error extracting text from diagram: {e}")
            return ''

    def process_confluence_data(self) -> List[Data]:
        """Process Confluence data and handle draw.io macros"""
        if not self.confluence_data:
            print("❌ No confluence data provided")
            return []
        
        print(f"🔍 DEBUG: Processing {len(self.confluence_data)} confluence documents")
        
        # Set up output directory
        output_dir = self.output_directory if self.output_directory else tempfile.mkdtemp()
        os.makedirs(output_dir, exist_ok=True)
        print(f"📁 Using output directory: {output_dir}")
        
        processed_data = []
        total_diagrams_found = 0
        total_diagrams_converted = 0
        
        for i, data_obj in enumerate(self.confluence_data):
            print(f"\n🔍 DEBUG: Processing document {i+1}/{len(self.confluence_data)}")
            
            try:
                # 🚨 FIXED: Use the new get_document_content method
                content = self.get_document_content(data_obj)
                
                # Get metadata and data dict
                metadata = {}
                data_dict = {}
                if hasattr(data_obj, 'metadata') and data_obj.metadata:
                    metadata = data_obj.metadata
                    print(f"📋 Metadata keys: {list(metadata.keys())}")
                    if 'title' in metadata:
                        print(f"📄 Document title: {metadata['title']}")
                
                if hasattr(data_obj, 'data') and data_obj.data:
                    data_dict = data_obj.data
                    print(f"📊 Data keys: {list(data_dict.keys())}")
                
                # Extract draw.io macros (handles HTML, base64, and enhanced data)
                macros = self.extract_drawio_macros(content, metadata, data_dict)
                total_diagrams_found += len(macros)
                
                if not macros:
                    # No draw.io content, pass through unchanged
                    processed_data.append(data_obj)
                    continue
                
                base_url = self.get_confluence_base_url(data_obj)
                print(f"🔗 Using base URL: {base_url}")
                
                diagram_info = []
                
                for macro in macros:
                    try:
                        print(f"\n🔄 Processing macro: {macro['diagram_name']} (ID: {macro['macro_id']})")
                        print(f"📎 Attachment ID: {macro['attachment_id']}")
                        
                        # Debug credentials
                        # self.debug_credentials(data_obj)  # Removed for security
                        
                        # Initialize variables
                        diagram_text = ""
                        png_path = None
                        base64_data = None
                        image_markdown = None
                        
                        # Process based on mode
                        if self.processing_mode in ["extract_and_convert", "extract_only"]:
                            # Try to download diagram file directly from Confluence first
                            diagram_file_path = None
                            if self.processing_mode == "extract_and_convert":
                                diagram_file_path = self.download_diagram_file_from_confluence(
                                    base_url, macro['attachment_id'], macro['diagram_name'], output_dir, data_obj
                                )
                                
                                if diagram_file_path:
                                    total_diagrams_converted += 1
                                    png_path = diagram_file_path
                                    
                                    # Create base64 embedding if requested
                                    if self.embed_images_base64:
                                        base64_data = self.embed_image_as_base64(png_path)
                                    
                                    # Create image markdown
                                    image_markdown = self.create_image_markdown(
                                        macro['diagram_name'], base64_data, png_path
                                    )
                                else:
                                    print(f"❌ Failed to download diagram file - trying embedded data approach")
                                    
                                    # If download fails, try to use embedded data to create XML file
                                    if 'encoded_data' in macro:
                                        try:
                                            print(f"🔍 Attempting to decode embedded draw.io data")
                                            decoded_data = base64.b64decode(macro['encoded_data']).decode('utf-8')
                                            macro_config = json.loads(decoded_data)
                                            
                                            # Check if this has XML data
                                            if 'xml' in macro_config:
                                                xml_content = macro_config['xml']
                                                
                                                # Save as XML file
                                                safe_name = re.sub(r'[^\w\-_.]', '_', macro['diagram_name'])
                                                xml_path = os.path.join(output_dir, f"{safe_name}.xml")
                                                
                                                with open(xml_path, 'w', encoding='utf-8') as f:
                                                    f.write(xml_content)
                                                
                                                print(f"✅ Created XML from embedded data: {xml_path}")
                                                
                                                # Try to convert to PNG
                                                png_path = xml_path.replace('.xml', '.png')
                                                if self.convert_drawio_xml_to_png(xml_content, png_path):
                                                    print(f"✅ Successfully converted embedded XML to PNG: {png_path}")
                                                    total_diagrams_converted += 1
                                                    
                                                    # Create base64 embedding if requested
                                                    if self.embed_images_base64:
                                                        base64_data = self.embed_image_as_base64(png_path)
                                                    
                                                    # Create image markdown
                                                    image_markdown = self.create_image_markdown(
                                                        macro['diagram_name'], base64_data, png_path
                                                    )
                                                else:
                                                    print(f"⚠️ Could not convert embedded XML to PNG, using XML file")
                                                    png_path = xml_path
                                                    image_markdown = f"[Diagram: {macro['diagram_name']} - XML file: {xml_path}]"
                                            else:
                                                print(f"❌ No XML data found in embedded macro config")
                                                
                                        except Exception as e:
                                            print(f"❌ Error processing embedded data: {e}")
                            
                            # Try to get XML for text extraction (use embedded data if download fails)
                            if self.include_diagram_text:
                                diagram_xml = None
                                
                                # First try downloading XML
                                if macro.get('attachment_id'):
                                    diagram_xml = self.get_diagram_xml_from_confluence(
                                        base_url, macro['attachment_id'], data_obj
                                    )
                                
                                # If download fails, try embedded data
                                if not diagram_xml and 'encoded_data' in macro:
                                    try:
                                        print(f"🔍 Using embedded data for text extraction")
                                        decoded_data = base64.b64decode(macro['encoded_data']).decode('utf-8')
                                        macro_config = json.loads(decoded_data)
                                        if 'xml' in macro_config:
                                            diagram_xml = macro_config['xml']
                                            print(f"✅ Got XML from embedded data for text extraction")
                                    except Exception as e:
                                        print(f"❌ Error extracting XML from embedded data: {e}")
                                
                                if diagram_xml:
                                    diagram_text = self.extract_text_from_diagram_xml(diagram_xml)
                                
                            diagram_info.append({
                                'macro_id': macro['macro_id'],
                                'diagram_name': macro['diagram_name'],
                                'png_path': png_path,
                                'base64_data': base64_data,
                                'image_markdown': image_markdown,
                                'diagram_text': diagram_text,
                                'attachment_id': macro['attachment_id'],
                                'file_size_kb': round(os.path.getsize(png_path) / 1024, 1) if png_path and os.path.exists(png_path) else 0,
                            })
                            
                        elif self.processing_mode == "text_description":
                            # Create text description
                            desc_text = f"[Diagram: {macro['diagram_name']}]"
                            
                            diagram_info.append({
                                'macro_id': macro['macro_id'],
                                'diagram_name': macro['diagram_name'],
                                'png_path': None,
                                'base64_data': None,
                                'image_markdown': None,
                                'diagram_text': desc_text,
                                'attachment_id': macro['attachment_id'],
                                'file_size_kb': 0,
                            })
                    
                    except Exception as e:
                        print(f"❌ Error processing macro {macro['macro_id']}: {e}")
                        continue
                
                # Create new data object with processed content
                new_data = Data()
                
                # For base64 JSON content, create a more readable text version
                if diagram_info:
                    content_parts = []
                    
                    # Add title if available
                    if metadata.get('title'):
                        content_parts.append(f"# {metadata['title']}\n")
                    
                    # Add original content if it's not just base64
                    if not self.is_base64_json(content.strip()):
                        content_parts.append(content)
                    
                    # Add diagram information
                    for diagram in diagram_info:
                        content_parts.append(f"\n## Diagram: {diagram['diagram_name']}")
                        
                        if diagram.get('diagram_text'):
                            content_parts.append(f"Content: {diagram['diagram_text']}")
                        
                        if diagram.get('image_markdown'):
                            content_parts.append(diagram['image_markdown'])
                        
                        content_parts.append("")  # Add spacing
                    
                    new_data.text = "\n".join(content_parts)
                else:
                    # No diagrams found, use original content
                    new_data.text = content
                
                # Copy metadata
                if hasattr(data_obj, 'metadata'):
                    new_data.metadata = data_obj.metadata.copy()
                    if not hasattr(new_data, 'data'):
                        new_data.data = {}
                elif hasattr(data_obj, 'data') and data_obj.data:
                    new_data.data = data_obj.data.copy()
                else:
                    new_data.data = {}
                
                # Add diagram information to data
                if diagram_info:
                    new_data.data['diagrams'] = diagram_info
                
                # Copy other attributes
                if hasattr(data_obj, 'id'):
                    new_data.id = data_obj.id
                
                processed_data.append(new_data)
                
                # Create separate chunks for diagrams if requested
                if self.create_diagram_chunks and diagram_info:
                    for diagram in diagram_info:
                        if diagram['diagram_text']:
                            diagram_chunk = Data()
                            
                            # Create contextual content for the diagram
                            diagram_content_parts = [
                                self.diagram_context_template.format(
                                    title=diagram['diagram_name'],
                                    content=diagram['diagram_text']
                                )
                            ]
                            
                            # Add image markdown if available
                            if diagram.get('image_markdown'):
                                diagram_content_parts.append(f"\n\n{diagram['image_markdown']}")
                            
                            diagram_chunk.text = '\n'.join(diagram_content_parts)
                            
                            # Copy and modify metadata
                            if hasattr(new_data, 'metadata'):
                                diagram_chunk.metadata = new_data.metadata.copy()
                            if hasattr(new_data, 'data') and new_data.data:
                                diagram_chunk.data = new_data.data.copy()
                            else:
                                diagram_chunk.data = {}
                            
                            # Add diagram-specific metadata
                            diagram_chunk.data['content_type'] = 'diagram'
                            diagram_chunk.data['diagram_name'] = diagram['diagram_name']
                            diagram_chunk.data['source_page_id'] = getattr(data_obj, 'id', '')
                            
                            # Create unique ID for diagram chunk
                            base_id = getattr(data_obj, 'id', 'unknown')
                            diagram_chunk.id = f"{base_id}_diagram_{diagram['macro_id']}"
                            
                            processed_data.append(diagram_chunk)
                
            except Exception as e:
                print(f"❌ Error processing data object: {e}")
                import traceback
                traceback.print_exc()
                # Pass through unchanged on error
                processed_data.append(data_obj)
                continue
        
        # Print summary
        print(f"\n✅ DRAWIO PROCESSOR SUMMARY")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Processing Mode: {self.processing_mode}")
        print(f"Documents Processed: {len(self.confluence_data)}")
        print(f"Documents Output: {len(processed_data)}")
        print(f"Diagrams Found: {total_diagrams_found}")
        print(f"Diagrams Converted: {total_diagrams_converted}")
        print(f"Output Directory: {output_dir}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        
        self.status = processed_data
        return processed_data