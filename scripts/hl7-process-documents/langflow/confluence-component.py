from langchain_community.document_loaders import ConfluenceLoader
from langchain_community.document_loaders.confluence import ContentFormat
from langflow.custom import Component
from langflow.io import BoolInput, DropdownInput, IntInput, Output, SecretStrInput, StrInput
from langflow.schema import Data
import requests
import json
import re
import uuid
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

class EnhancedConfluenceComponent(Component):
    display_name = "Enhanced Confluence (Draw.io Support)"
    description = "Confluence loader with enhanced draw.io macro extraction"
    documentation = "Enhanced version that properly extracts draw.io macros from Confluence pages"
    trace_type = "tool"
    icon = "Confluence"
    name = "EnhancedConfluence"
    
    inputs = [
        StrInput(
            name="url",
            display_name="Site URL",
            required=True,
            info="The base URL of the Confluence Space. Example: https://<company>.atlassian.net/wiki.",
        ),
        StrInput(
            name="username",
            display_name="Username",
            required=True,
            info="Atlassian User E-mail. Example: email@example.com",
        ),
        SecretStrInput(
            name="api_key",
            display_name="API Key",
            required=True,
            info="Atlassian Key. Create at: https://id.atlassian.com/manage-profile/security/api-tokens",
        ),
        StrInput(name="space_key", display_name="Space Key", required=True),
        BoolInput(name="cloud", display_name="Use Cloud?", required=True, value=True, advanced=True),
        DropdownInput(
            name="content_format",
            display_name="Content Format",
            options=[
                ContentFormat.EDITOR.value,
                ContentFormat.EXPORT_VIEW.value,
                ContentFormat.ANONYMOUS_EXPORT_VIEW.value,
                ContentFormat.STORAGE.value,
                ContentFormat.VIEW.value,
            ],
            value=ContentFormat.VIEW.value,  # Changed default to VIEW for better draw.io support
            required=True,
            advanced=True,
            info="Specify content format, defaults to VIEW for better draw.io macro extraction",
        ),
        IntInput(
            name="max_pages",
            display_name="Max Pages",
            required=False,
            value=1000,
            advanced=True,
            info="Maximum number of pages to retrieve in total, defaults 1000",
        ),
        BoolInput(
            name="include_attachments",
            display_name="Include Attachments",
            required=False,
            value=False,
            info="Whether to include attachments when loading documents",
        ),
        StrInput(
            name="page_ids",
            display_name="Page IDs",
            required=False,
            info="Comma-separated list of specific page IDs to load. Example: 123456,789012",
        ),
        StrInput(
            name="label",
            display_name="Label Filter",
            required=False,
            info="Load only pages with this specific label",
        ),
        StrInput(
            name="cql",
            display_name="CQL Query",
            required=False,
            info="Confluence Query Language (CQL) for advanced filtering. Example: title~'API' and space='DEV'",
        ),
        BoolInput(
            name="include_restricted_content",
            display_name="Include Restricted Content",
            required=False,
            value=False,
            advanced=True,
            info="Whether to include pages with restricted access",
        ),
        StrInput(
            name="parent_page_id",
            display_name="Parent Page ID",
            required=False,
            info="Load pages under this parent page ID",
        ),
        BoolInput(
            name="include_children",
            display_name="Include Child Pages",
            required=False,
            value=True,
            info="When using Parent Page ID, whether to include all descendant pages or just the parent",
        ),
        BoolInput(
            name="extract_drawio_macros",
            display_name="Extract Draw.io Macros",
            required=False,
            value=True,
            info="Whether to extract and enhance draw.io macro content",
        ),
        BoolInput(
            name="fetch_both_formats",
            display_name="Fetch Both Content Formats",
            required=False,
            value=True,
            advanced=True,
            info="Fetch both VIEW and STORAGE formats to get complete draw.io data",
        ),
        # Attachment filtering options
        StrInput(
            name="exclude_attachment_ids",
            display_name="Exclude Attachment IDs",
            required=False,
            info="Comma-separated list of attachment IDs to exclude",
        ),
        StrInput(
            name="exclude_file_types",
            display_name="Exclude File Types",
            required=False,
            info="Comma-separated list of file extensions to exclude (e.g., pdf,docx,exe)",
        ),
        StrInput(
            name="include_only_file_types",
            display_name="Include Only File Types",
            required=False,
            info="Comma-separated list of file extensions to include (e.g., txt,md,json). Overrides exclude list.",
        ),
        IntInput(
            name="max_attachment_size_mb",
            display_name="Max Attachment Size (MB)",
            required=False,
            info="Exclude attachments larger than this size in MB (0 = no limit)",
            value=0,
        ),
        StrInput(
            name="exclude_page_trees",
            display_name="Exclude Page Trees",
            required=False,
            info="Comma-separated list of page IDs to exclude along with all their children",
            advanced=True,
        ),
    ]
    
    outputs = [
        Output(name="data", display_name="Data", method="load_documents"),
    ]
    
    def build_confluence(self, content_format: ContentFormat) -> ConfluenceLoader:
        # Build kwargs for ConfluenceLoader
        kwargs = {
            "url": self.url,
            "token": self.api_key,
            "cloud": self.cloud,
            "content_format": content_format,
            "max_pages": self.max_pages,
            "include_attachments": self.include_attachments,
            "include_restricted_content": self.include_restricted_content,
        }
        
        # Add space_key, page_ids, label, parent_page_id, or cql based on what's provided
        if self.page_ids:
            # Convert comma-separated string to list of page IDs
            page_id_list = [pid.strip() for pid in self.page_ids.split(",") if pid.strip()]
            kwargs["page_ids"] = page_id_list
        elif self.parent_page_id:
            # Use CQL to control parent/child loading
            if self.include_children:
                # Try different CQL syntaxes for better compatibility
                try:
                    base_cql = f"ancestor = {self.parent_page_id}"
                    # Add space constraint if specified
                    if self.space_key:
                        kwargs["cql"] = f"space = \"{self.space_key}\" AND ({base_cql})"
                    else:
                        kwargs["cql"] = base_cql
                except:
                    # Fallback for older Confluence versions
                    kwargs["page_ids"] = [self.parent_page_id]
            else:
                base_cql = f"id = {self.parent_page_id}"
                # Add space constraint if specified
                if self.space_key:
                    kwargs["cql"] = f"space = \"{self.space_key}\" AND ({base_cql})"
                else:
                    kwargs["cql"] = base_cql
        elif self.cql:
            # Combine user CQL with space constraint if space_key is provided
            if self.space_key:
                kwargs["cql"] = f"space = \"{self.space_key}\" AND ({self.cql})"
            else:
                kwargs["cql"] = self.cql
        elif self.label:
            kwargs["label"] = self.label
            # Add space constraint for label queries if specified
            if self.space_key:
                kwargs["space_key"] = self.space_key
        else:
            # Default to space_key if no specific pages/queries specified
            kwargs["space_key"] = self.space_key
        
        return ConfluenceLoader(**kwargs)
    
    def get_page_content_directly(self, page_id: str, content_format: str = 'view') -> Optional[str]:
        """Fetch page content directly from Confluence API to get complete draw.io data"""
        try:
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            # Construct API URL for getting page content
            api_url = f"{self.url}/rest/api/content/{page_id}"
            params = {
                'expand': f'body.{content_format}',
                'status': 'current'
            }
            
            print(f"🔍 Fetching {content_format} content for page {page_id}")
            response = requests.get(api_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            content_data = response.json()
            
            if 'body' in content_data and content_format in content_data['body']:
                content_value = content_data['body'][content_format]['value']
                print(f"✅ Got {content_format} content: {len(content_value)} chars")
                return content_value
            else:
                print(f"❌ No {content_format} content found in response")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching {content_format} content for page {page_id}: {e}")
            return None
    
    def extract_drawio_macros_from_view(self, html_content: str) -> List[Dict[str, Any]]:
        """Extract draw.io macros from VIEW format HTML"""
        macros = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for draw.io macro containers in VIEW format
            drawio_containers = soup.find_all('div', class_='conf-macro output-block')
            
            for container in drawio_containers:
                if container.get('data-macro-name') == 'drawio':
                    try:
                        # Find the macro content div
                        macro_div = container.find('div', class_='drawio-macro')
                        if not macro_div:
                            continue
                            
                        macro_id = macro_div.get('data-macroid')
                        if not macro_id:
                            continue
                        
                        # Find the hidden data div with complete base64 content
                        data_div = container.find('div', id=f'drawio-macro-data-{macro_id}')
                        if not data_div:
                            # Try searching in the entire document
                            data_div = soup.find('div', id=f'drawio-macro-data-{macro_id}')
                            if not data_div:
                                print(f"❌ No data div found for macro {macro_id}")
                                continue
                        
                        # Extract the complete base64 content
                        encoded_data = data_div.get_text().strip()
                        if not encoded_data:
                            print(f"❌ Empty data div for macro {macro_id}")
                            continue
                        
                        print(f"✅ Found complete draw.io macro: {macro_id} ({len(encoded_data)} chars)")
                        
                        macros.append({
                            'macro_id': macro_id,
                            'encoded_data': encoded_data,
                            'container_html': str(container)
                        })
                        
                    except Exception as e:
                        print(f"❌ Error processing draw.io container: {e}")
                        continue
            
            print(f"🔍 Extracted {len(macros)} draw.io macros from VIEW content")
            return macros
            
        except Exception as e:
            print(f"❌ Error extracting draw.io macros from VIEW: {e}")
            return []
    
    def extract_drawio_macros_from_storage(self, storage_content: str) -> List[Dict[str, Any]]:
        """Extract draw.io macros from STORAGE format content"""
        macros = []
        try:
            # STORAGE format might have draw.io macros in different structure
            # Look for draw.io macro references
            drawio_pattern = r'<ac:structured-macro[^>]*ac:name="drawio"[^>]*>(.*?)</ac:structured-macro>'
            matches = re.finditer(drawio_pattern, storage_content, re.DOTALL)
            
            for match in matches:
                macro_content = match.group(1)
                try:
                    # Parse parameters from the macro
                    soup = BeautifulSoup(f"<root>{macro_content}</root>", 'xml')
                    
                    # Extract parameters
                    params = {}
                    for param in soup.find_all('ac:parameter'):
                        param_name = param.get('ac:name', '')
                        param_value = param.get_text().strip()
                        if param_name and param_value:
                            params[param_name] = param_value
                    
                    # Look for attachment ID and diagram name
                    att_id = params.get('attId', '')
                    diagram_name = params.get('diagramName', 'Unknown Diagram')
                    
                    if att_id:
                        print(f"✅ Found draw.io macro in STORAGE: {diagram_name} (attId: {att_id})")
                        macros.append({
                            'macro_id': f"storage_{att_id}",
                            'attachment_id': att_id,
                            'diagram_name': diagram_name,
                            'parameters': params,
                            'source': 'storage_format'
                        })
                    
                except Exception as e:
                    print(f"❌ Error parsing STORAGE macro: {e}")
                    continue
            
            print(f"🔍 Extracted {len(macros)} draw.io macros from STORAGE content")
            return macros
            
        except Exception as e:
            print(f"❌ Error extracting draw.io macros from STORAGE: {e}")
            return []
    
    def enhance_document_with_drawio(self, doc, page_id: str) -> Any:
        """Enhance document with complete draw.io macro information"""
        try:
            if not self.extract_drawio_macros:
                return doc
            
            print(f"\n🔍 Enhancing document: {doc.metadata.get('title', 'Unknown')} (ID: {page_id})")
            
            all_macros = []
            
            # First, try to extract from the current document content
            current_format = self.content_format.lower()
            if current_format == 'view':
                print(f"🔍 Extracting from current VIEW content")
                all_macros = self.extract_drawio_macros_from_view(doc.page_content)
            elif current_format == 'storage':
                print(f"🔍 Extracting from current STORAGE content")
                all_macros = self.extract_drawio_macros_from_storage(doc.page_content)
            
            # If we didn't find macros and fetch_both_formats is enabled, try API calls
            if not all_macros and self.fetch_both_formats:
                print(f"🔍 No macros found in current content, trying additional API calls")
                
                # Get VIEW content for complete draw.io macro HTML
                view_content = self.get_page_content_directly(page_id, 'view')
                if view_content:
                    view_macros = self.extract_drawio_macros_from_view(view_content)
                    all_macros.extend(view_macros)
                
                # Get STORAGE content for macro parameters
                storage_content = self.get_page_content_directly(page_id, 'storage')
                if storage_content:
                    storage_macros = self.extract_drawio_macros_from_storage(storage_content)
                    all_macros.extend(storage_macros)
            
            # If we still don't have macros, try extracting from mixed content
            if not all_macros:
                print(f"🔍 Trying to extract base64 from mixed content")
                # Look for base64 patterns in the content
                import re
                base64_pattern = r'eyJ[A-Za-z0-9+/=]{100,}'
                matches = re.findall(base64_pattern, doc.page_content)
                
                for match in matches:
                    try:
                        import base64
                        import json
                        
                        # Try to decode and validate
                        decoded = base64.b64decode(match).decode('utf-8')
                        config = json.loads(decoded)
                        
                        if 'attId' in config or 'diagramName' in config:
                            print(f"✅ Found draw.io config in mixed content")
                            macro_id = str(uuid.uuid4())
                            all_macros.append({
                                'macro_id': macro_id,
                                'encoded_data': match,
                                'config': config,
                                'diagram_name': config.get('diagramName', 'Unknown Diagram'),
                                'attachment_id': config.get('attId'),
                                'source': 'mixed_content_extraction'
                            })
                    except Exception as e:
                        print(f"⚠️ Could not decode potential base64: {e}")
                        continue
            
            if all_macros:
                print(f"✅ Found {len(all_macros)} total draw.io macros")
                
                # Add draw.io information to document metadata
                if not hasattr(doc, 'metadata'):
                    doc.metadata = {}
                
                doc.metadata['drawio_macros'] = all_macros
                doc.metadata['has_drawio'] = True
                doc.metadata['drawio_count'] = len(all_macros)
                
                # If we have macros with complete base64 data, enhance the content
                view_macros = [m for m in all_macros if 'encoded_data' in m]
                if view_macros:
                    print(f"✅ Enhanced metadata with {len(view_macros)} complete draw.io macros")
            else:
                print(f"❌ No draw.io macros found in document")
            
            return doc
            
        except Exception as e:
            print(f"❌ Error enhancing document with draw.io: {e}")
            import traceback
            traceback.print_exc()
            return doc
    
    def filter_excluded_pages(self, documents: list) -> list:
        """Filter out excluded page trees from the document list"""
        if not self.exclude_page_trees:
            return documents
            
        excluded_page_ids = set()
        if self.exclude_page_trees:
            excluded_page_ids = {pid.strip() for pid in self.exclude_page_trees.split(",") if pid.strip()}
        
        if not excluded_page_ids:
            return documents
            
        # Build a set of all excluded pages and their descendants
        all_excluded_ids = set(excluded_page_ids)
        
        # First pass: identify all pages and build parent-child relationships
        page_children = {}  # parent_id -> set of child_ids
        all_pages = {}      # page_id -> document
        
        for doc in documents:
            metadata = doc.metadata
            page_id = metadata.get('id', '')
            if page_id:
                all_pages[page_id] = doc
                parent_id = metadata.get('parent_id', metadata.get('parentId', ''))
                if parent_id:
                    if parent_id not in page_children:
                        page_children[parent_id] = set()
                    page_children[parent_id].add(page_id)
        
        # Second pass: recursively find all descendants of excluded pages
        def add_descendants(page_id):
            all_excluded_ids.add(page_id)
            if page_id in page_children:
                for child_id in page_children[page_id]:
                    add_descendants(child_id)
        
        for excluded_id in excluded_page_ids:
            add_descendants(excluded_id)
        
        # Third pass: filter out excluded pages
        filtered_docs = []
        for doc in documents:
            page_id = doc.metadata.get('id', '')
            if page_id not in all_excluded_ids:
                filtered_docs.append(doc)
                
        return filtered_docs

    def filter_attachments(self, documents: list) -> list:
        """Filter out unwanted attachments from the document list"""
        if not self.include_attachments:
            return documents
            
        filtered_docs = []
        
        # Parse filtering criteria
        excluded_ids = set()
        if self.exclude_attachment_ids:
            excluded_ids = {aid.strip() for aid in self.exclude_attachment_ids.split(",") if aid.strip()}
            
        excluded_types = set()
        if self.exclude_file_types:
            excluded_types = {ext.strip().lower().lstrip('.') for ext in self.exclude_file_types.split(",") if ext.strip()}
            
        included_types = set()
        if self.include_only_file_types:
            included_types = {ext.strip().lower().lstrip('.') for ext in self.include_only_file_types.split(",") if ext.strip()}
            
        max_size_bytes = self.max_attachment_size_mb * 1024 * 1024 if self.max_attachment_size_mb > 0 else None
        
        for doc in documents:
            # Check if this is an attachment by looking at metadata
            metadata = doc.metadata
            is_attachment = metadata.get('type') == 'attachment' or 'attachment' in metadata.get('source', '').lower()
            
            if not is_attachment:
                # Keep all non-attachment documents
                filtered_docs.append(doc)
                continue
                
            # For attachments, apply filters
            should_include = True
            
            # Check attachment ID exclusion
            attachment_id = metadata.get('id', '')
            if attachment_id in excluded_ids:
                should_include = False
                
            # Check file type filters
            if should_include:
                # Get file extension from title or filename
                filename = metadata.get('title', metadata.get('filename', ''))
                if filename and '.' in filename:
                    file_ext = filename.split('.')[-1].lower()
                    
                    # If include_only_file_types is specified, only include those types
                    if included_types:
                        should_include = file_ext in included_types
                    # Otherwise, exclude specified types
                    elif excluded_types:
                        should_include = file_ext not in excluded_types
                        
            # Check file size
            if should_include and max_size_bytes:
                file_size = metadata.get('size', 0)
                if isinstance(file_size, (int, float)) and file_size > max_size_bytes:
                    should_include = False
                    
            if should_include:
                filtered_docs.append(doc)
                
        return filtered_docs
    
    def generate_summary_report(self, original_docs, final_docs):
        """Generate a clean summary report of what was processed"""
        
        # Analyze original documents
        original_pages = 0
        original_attachments = 0
        spaces = set()
        drawio_pages = 0
        total_drawio_macros = 0
        
        for doc in original_docs:
            metadata = doc.metadata
            is_attachment = metadata.get('type') == 'attachment' or 'attachment' in metadata.get('source', '').lower()
            space_key = metadata.get('space', {}).get('key', 'Unknown') if isinstance(metadata.get('space'), dict) else metadata.get('space', 'Unknown')
            spaces.add(space_key)
            
            if is_attachment:
                original_attachments += 1
            else:
                original_pages += 1
                
            # Count draw.io macros
            if metadata.get('has_drawio'):
                drawio_pages += 1
                total_drawio_macros += metadata.get('drawio_count', 0)
        
        # Analyze final documents
        final_pages = 0
        final_attachments = 0
        
        for doc in final_docs:
            metadata = doc.metadata
            is_attachment = metadata.get('type') == 'attachment' or 'attachment' in metadata.get('source', '').lower()
            
            if is_attachment:
                final_attachments += 1
            else:
                final_pages += 1
        
        # Generate clean summary
        config_summary = []
        if hasattr(self, 'cql') and self.cql:
            if hasattr(self, 'space_key') and self.space_key:
                config_summary.append(f"CQL: space=\"{self.space_key}\" AND ({self.cql})")
            else:
                config_summary.append(f"CQL: {self.cql}")
        elif hasattr(self, 'page_ids') and self.page_ids:
            config_summary.append(f"Page IDs: {self.page_ids}")
        elif hasattr(self, 'parent_page_id') and self.parent_page_id:
            config_summary.append(f"Parent Page: {self.parent_page_id}")
        elif hasattr(self, 'label') and self.label:
            config_summary.append(f"Label: {self.label}")
        else:
            config_summary.append(f"Space: {getattr(self, 'space_key', 'Unknown')}")
        
        if self.include_attachments:
            config_summary.append("Attachments: Enabled")
        
        if self.extract_drawio_macros:
            config_summary.append("Draw.io: Enhanced")
        
        print(f"\n✅ ENHANCED CONFLUENCE LOADER SUMMARY")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Config: {' | '.join(config_summary)}")
        print(f"Spaces: {', '.join(sorted(spaces))}")
        print(f"Loaded: {original_pages} pages, {original_attachments} attachments")
        if drawio_pages > 0:
            print(f"Draw.io: {drawio_pages} pages with {total_drawio_macros} diagrams")
        if (original_pages + original_attachments) != (final_pages + final_attachments):
            print(f"Filtered: {final_pages} pages, {final_attachments} attachments (after filtering)")
        print(f"Total Documents: {len(final_docs)}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    def flatten_confluence_metadata(self, metadata: dict) -> dict:
        """Flatten Confluence metadata for vector store compatibility"""
        flattened = {}
        
        for key, value in metadata.items():
            if key == 'space' and isinstance(value, dict):
                # Flatten space object
                flattened['space_key'] = value.get('key', '')
                flattened['space_name'] = value.get('name', '')
            elif key == 'version' and isinstance(value, dict):
                # Flatten version object
                flattened['version_number'] = value.get('number', '')
                flattened['version_when'] = value.get('when', '')
                flattened['lastModified'] = value.get('when', '')  # For change detection
            elif key == 'drawio_macros':
                # Handle draw.io macros specially
                flattened['has_drawio'] = True
                flattened['drawio_count'] = len(value) if isinstance(value, list) else 0
                # Store simplified macro info
                if isinstance(value, list) and value:
                    macro_names = []
                    attachment_ids = []
                    for macro in value:
                        if isinstance(macro, dict):
                            if 'diagram_name' in macro:
                                macro_names.append(macro['diagram_name'])
                            if 'attachment_id' in macro:
                                attachment_ids.append(macro['attachment_id'])
                    if macro_names:
                        flattened['drawio_diagrams'] = ', '.join(macro_names)
                    if attachment_ids:
                        flattened['drawio_attachments'] = ', '.join(attachment_ids)
            elif isinstance(value, dict):
                # Flatten other nested objects
                for nested_key, nested_value in value.items():
                    flat_key = f"{key}_{nested_key}"
                    if isinstance(nested_value, (str, int, float, bool)):
                        flattened[flat_key] = nested_value
                    else:
                        flattened[flat_key] = str(nested_value)
            elif isinstance(value, list):
                # Convert lists to comma-separated strings (except draw.io macros)
                if key != 'drawio_macros':
                    flattened[key] = ", ".join(str(item) for item in value)
            elif isinstance(value, (str, int, float, bool)):
                # Keep simple types as-is
                flattened[key] = value
            else:
                # Convert everything else to string
                flattened[key] = str(value)
        
        return flattened

    def load_documents(self) -> list[Data]:
        import warnings
        
        print(f"🚀 Starting Enhanced Confluence Loader")
        print(f"🔧 Extract Draw.io: {self.extract_drawio_macros}")
        print(f"🔧 Fetch Both Formats: {self.fetch_both_formats}")
        print(f"🔧 Content Format: {self.content_format}")
        print(f"🔧 URL: {self.url}")
        
        # Suppress BeautifulSoup warnings during Confluence loading
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module="bs4")
            
            # Get the content format
            content_format = ContentFormat(self.content_format)
            confluence = self.build_confluence(content_format)
            original_documents = confluence.load()
        
        print(f"📄 Loaded {len(original_documents)} original documents")
        
        # Enhance documents with draw.io information
        enhanced_documents = []
        for i, doc in enumerate(original_documents):
            print(f"\n📝 Processing document {i+1}/{len(original_documents)}: {doc.metadata.get('title', 'Unknown')}")
            page_id = doc.metadata.get('id', '')
            print(f"🆔 Page ID: {page_id}")
            print(f"📄 Document type: {doc.metadata.get('type', 'page')}")
            
            if page_id and not doc.metadata.get('type') == 'attachment':
                print(f"🔄 Calling enhance_document_with_drawio for page {page_id}")
                enhanced_doc = self.enhance_document_with_drawio(doc, page_id)
                print(f"✅ Enhancement completed for page {page_id}")
            else:
                print(f"⏭️ Skipping enhancement (no page_id or is attachment)")
                enhanced_doc = doc
            enhanced_documents.append(enhanced_doc)
        
        print(f"✅ Enhanced {len(enhanced_documents)} documents")
        
        # Filter excluded page trees first
        documents = self.filter_excluded_pages(enhanced_documents)
        
        # Filter attachments if needed
        if self.include_attachments:
            documents = self.filter_attachments(documents)
        
        # Generate summary report
        self.generate_summary_report(enhanced_documents, documents)
        
        # Convert to Data objects with proper IDs for smart updates
        print(f"🔄 Converting {len(documents)} documents to Data objects...")
        data = []
        for doc in documents:
            # Use Confluence page/attachment ID as the document ID
            doc_id = doc.metadata.get('id', '')
            if not doc_id:
                # Fallback: generate ID from title and space
                title = doc.metadata.get('title', 'untitled')
                space = doc.metadata.get('space', {})
                space_key = space.get('key', 'unknown') if isinstance(space, dict) else str(space)
                doc_id = f"{space_key}_{title.replace(' ', '_')}"
            
            # Debug: Show what metadata we have before flattening
            print(f"\n🔍 Document {doc_id} metadata before flattening:")
            print(f"   - Has drawio_macros: {'drawio_macros' in doc.metadata}")
            print(f"   - Has has_drawio: {'has_drawio' in doc.metadata}")
            print(f"   - Metadata keys: {list(doc.metadata.keys())}")
            
            # Flatten metadata to avoid ChromaDB compatibility issues
            flattened_metadata = self.flatten_confluence_metadata(doc.metadata)
            
            data_obj = Data.from_document(doc)
            data_obj.id = doc_id  # Set the document ID for smart updates
            
            # Store flattened metadata in the data dictionary
            if not hasattr(data_obj, 'data') or not data_obj.data:
                data_obj.data = {}
            data_obj.data['metadata'] = flattened_metadata
            
            # 🚨 CRITICAL FIX: Store credentials in data object for DrawIO processor
            data_obj.data['confluence_username'] = self.username
            data_obj.data['confluence_token'] = self.api_key
            data_obj.data['confluence_base_url'] = self.url
            
            # Store original draw.io macro data for the DrawIO processor
            if doc.metadata.get('has_drawio') and doc.metadata.get('drawio_macros'):
                data_obj.data['drawio_macros'] = doc.metadata['drawio_macros']
                print(f"✅ Stored {len(doc.metadata['drawio_macros'])} draw.io macros in data object")
            else:
                print(f"❌ No draw.io macros found in document metadata")
            
            data.append(data_obj)
        
        self.status = data
        return data