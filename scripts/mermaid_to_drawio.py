#!/usr/bin/env python3
"""
Convert Mermaid flowchart to draw.io JSON format
"""

import json
import re
import math
from typing import Dict, List, Tuple, Any

class MermaidToDrawIO:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.node_counter = 0
        self.edge_counter = 0
        
    def parse_mermaid(self, mermaid_content: str) -> Dict[str, Any]:
        """Parse Mermaid flowchart content and convert to draw.io format"""
        lines = mermaid_content.strip().split('\n')
        
        # Skip the first line (flowchart TD)
        content_lines = [line.strip() for line in lines[1:] if line.strip() and not line.strip().startswith('style')]
        
        # Parse all lines - nodes and edges
        for line in content_lines:
            if '-->' in line:
                # This line contains both node definitions and edges
                self._parse_edge(line)
            elif ('[' in line and ']' in line) or ('{' in line and '}' in line):
                # This line contains only a node definition
                self._parse_node(line)
        
        # Parse styling
        style_lines = [line.strip() for line in lines if line.strip().startswith('style')]
        styles = self._parse_styles(style_lines)
        
        # Generate draw.io JSON
        return self._generate_drawio_json(styles)
    
    def _parse_node(self, line: str):
        """Parse a node definition from Mermaid syntax"""
        # Skip if this is an edge
        if '-->' in line:
            return
            
        # Extract node ID and label - handle both [content] and {content} formats
        if ('[' in line and ']' in line) or ('{' in line and '}' in line):
            # Find the first bracket
            bracket_start = -1
            bracket_end = -1
            bracket_type = None
            
            if '[' in line:
                bracket_start = line.find('[')
                bracket_end = line.find(']')
                bracket_type = 'square'
            elif '{' in line:
                bracket_start = line.find('{')
                bracket_end = line.find('}')
                bracket_type = 'curly'
            
            if bracket_start > 0 and bracket_end > bracket_start:
                node_id = line[:bracket_start].strip()
                content = line[bracket_start+1:bracket_end].strip()
                
                # Clean up node ID (remove special characters)
                node_id = re.sub(r'[^a-zA-Z0-9_]', '', node_id)
                
                # Determine shape based on bracket type
                if bracket_type == 'curly':
                    shape = 'rhombus'
                else:
                    shape = 'rectangle'
                
                # Handle line breaks in content
                content = content.replace('<br/>', '\n')
                
                self.nodes[node_id] = {
                    'id': node_id,
                    'label': content,
                    'shape': shape
                }
    
    def _parse_edge(self, line: str):
        """Parse an edge definition from Mermaid syntax"""
        if '-->' in line:
            parts = line.split('-->')
            if len(parts) >= 2:
                source_part = parts[0].strip()
                target_part = parts[1].strip()
                
                # Extract source node definition
                source_id, source_content, source_shape = self._extract_node_from_part(source_part)
                if source_id and source_id not in self.nodes:
                    self.nodes[source_id] = {
                        'id': source_id,
                        'label': source_content,
                        'shape': source_shape
                    }
                
                # Handle labeled edges
                if '|' in target_part:
                    target, label = target_part.split('|', 1)
                    target = target.strip()
                    label = label.strip()
                else:
                    target = target_part
                    label = None
                
                # Extract target node definition
                target_id, target_content, target_shape = self._extract_node_from_part(target)
                if target_id and target_id not in self.nodes:
                    self.nodes[target_id] = {
                        'id': target_id,
                        'label': target_content,
                        'shape': target_shape
                    }
                
                self.edges.append({
                    'source': source_id,
                    'target': target_id,
                    'label': label
                })
    
    def _extract_node_from_part(self, part: str) -> Tuple[str, str, str]:
        """Extract node ID, content, and shape from a part of an edge definition"""
        # Clean up the part
        part = part.strip()
        
        # Find brackets
        bracket_start = -1
        bracket_end = -1
        bracket_type = None
        
        if '[' in part:
            bracket_start = part.find('[')
            bracket_end = part.find(']')
            bracket_type = 'square'
        elif '{' in part:
            bracket_start = part.find('{')
            bracket_end = part.find('}')
            bracket_type = 'curly'
        
        if bracket_start > 0 and bracket_end > bracket_start:
            node_id = part[:bracket_start].strip()
            content = part[bracket_start+1:bracket_end].strip()
            
            # Clean up node ID
            node_id = re.sub(r'[^a-zA-Z0-9_]', '', node_id)
            
            # Determine shape
            if bracket_type == 'curly':
                shape = 'rhombus'
            else:
                shape = 'rectangle'
            
            # Handle line breaks
            content = content.replace('<br/>', '\n')
            
            return node_id, content, shape
        else:
            # No brackets found, treat as simple node ID
            node_id = re.sub(r'[^a-zA-Z0-9_]', '', part)
            return node_id, node_id, 'rectangle'
    
    def _parse_styles(self, style_lines: List[str]) -> Dict[str, Dict]:
        """Parse style definitions"""
        styles = {}
        for line in style_lines:
            # Extract node ID and style properties
            match = re.match(r'style\s+(\w+)\s+fill:([^,]+),stroke:([^,]+),stroke-width:([^,]+),color:([^,]+)', line)
            if match:
                node_id, fill, stroke, stroke_width, color = match.groups()
                styles[node_id] = {
                    'fill': fill,
                    'stroke': stroke,
                    'strokeWidth': stroke_width,
                    'fontColor': color
                }
        return styles
    
    def _generate_drawio_json(self, styles: Dict[str, Dict]) -> Dict[str, Any]:
        """Generate draw.io JSON format"""
        # Calculate layout positions
        positions = self._calculate_positions()
        
        # Create draw.io cells
        cells = []
        
        # Add nodes
        for node_id, node_data in self.nodes.items():
            pos = positions.get(node_id, (100, 100))
            style = styles.get(node_id, {})
            
            cell = {
                "id": f"node_{self.node_counter}",
                "value": node_data['label'],
                "style": self._get_node_style(node_data['shape'], style),
                "vertex": 1,
                "parent": "1",
                "geometry": {
                    "x": pos[0],
                    "y": pos[1],
                    "width": 120,
                    "height": 60
                }
            }
            
            # Adjust size for decision nodes
            if node_data['shape'] == 'rhombus':
                cell["geometry"]["width"] = 100
                cell["geometry"]["height"] = 80
            
            cells.append(cell)
            self.node_counter += 1
        
        # Add edges
        for edge in self.edges:
            if edge['source'] in self.nodes and edge['target'] in self.nodes:
                cell = {
                    "id": f"edge_{self.edge_counter}",
                    "value": edge['label'] or "",
                    "style": "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;",
                    "edge": 1,
                    "parent": "1",
                    "source": f"node_{list(self.nodes.keys()).index(edge['source'])}",
                    "target": f"node_{list(self.nodes.keys()).index(edge['target'])}",
                    "geometry": {
                        "relative": 1,
                        "as": "geometry"
                    }
                }
                cells.append(cell)
                self.edge_counter += 1
        
        # Create the complete draw.io JSON structure
        drawio_json = {
            "version": "21.1.0",
            "type": "device",
            "pages": [
                {
                    "id": "0",
                    "name": "Page-1",
                    "root": {
                        "id": "1",
                        "parent": "0",
                        "children": cells
                    }
                }
            ]
        }
        
        # Alternative format for direct import
        drawio_xml = self._generate_drawio_xml(cells)
        
        return {
            "json": drawio_json,
            "xml": drawio_xml
        }
    
    def _generate_drawio_xml(self, cells: List[Dict]) -> str:
        """Generate draw.io XML format"""
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<mxfile host="app.diagrams.net" modified="2024-01-01T00:00:00.000Z" agent="5.0" version="21.1.0" etag="test" type="device">',
            '  <diagram name="Page-1" id="0">',
            '    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">',
            '      <root>',
            '        <mxCell id="0" />',
            '        <mxCell id="1" parent="0" />'
        ]
        
        for cell in cells:
            if cell.get('vertex'):
                # Node
                xml_parts.append(f'        <mxCell id="{cell["id"]}" value="{cell["value"]}" style="{cell["style"]}" vertex="1" parent="1">')
                xml_parts.append(f'          <mxGeometry x="{cell["geometry"]["x"]}" y="{cell["geometry"]["y"]}" width="{cell["geometry"]["width"]}" height="{cell["geometry"]["height"]}" as="geometry" />')
                xml_parts.append('        </mxCell>')
            elif cell.get('edge'):
                # Edge
                xml_parts.append(f'        <mxCell id="{cell["id"]}" value="{cell["value"]}" style="{cell["style"]}" edge="1" parent="1" source="{cell["source"]}" target="{cell["target"]}">')
                xml_parts.append('          <mxGeometry relative="1" as="geometry" />')
                xml_parts.append('        </mxCell>')
        
        xml_parts.extend([
            '      </root>',
            '    </mxGraphModel>',
            '  </diagram>',
            '</mxfile>'
        ])
        
        return '\n'.join(xml_parts)
    
    def _get_node_style(self, shape: str, style: Dict) -> str:
        """Generate draw.io style string for a node"""
        base_style = "rounded=1;whiteSpace=wrap;html=1;"
        
        if shape == 'rhombus':
            base_style += "rhombus;"
        else:
            base_style += "rounded=1;"
        
        # Apply custom styling
        if 'fill' in style:
            base_style += f"fillColor={style['fill']};"
        if 'stroke' in style:
            base_style += f"strokeColor={style['stroke']};"
        if 'strokeWidth' in style:
            base_style += f"strokeWidth={style['strokeWidth']};"
        if 'fontColor' in style:
            base_style += f"fontColor={style['fontColor']};"
        
        return base_style
    
    def _calculate_positions(self) -> Dict[str, Tuple[int, int]]:
        """Calculate node positions for layout"""
        positions = {}
        
        # Simple grid layout
        nodes = list(self.nodes.keys())
        if not nodes:
            return positions
            
        cols = max(1, int(math.ceil(math.sqrt(len(nodes)))))
        rows = int(math.ceil(len(nodes) / cols))
        
        for i, node_id in enumerate(nodes):
            row = i // cols
            col = i % cols
            x = 200 + col * 200
            y = 100 + row * 150
            positions[node_id] = (x, y)
        
        return positions

def main():
    # Read the Mermaid file
    mermaid_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow.mermaid"
    
    with open(mermaid_file, 'r') as f:
        mermaid_content = f.read()
    
    # Convert to draw.io format
    converter = MermaidToDrawIO()
    result = converter.parse_mermaid(mermaid_content)
    
    # Save the JSON file
    json_output_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow_drawio.json"
    
    with open(json_output_file, 'w') as f:
        json.dump(result['json'], f, indent=2)
    
    # Save the XML file
    xml_output_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow_drawio.xml"
    
    with open(xml_output_file, 'w') as f:
        f.write(result['xml'])
    
    print(f"Converted Mermaid diagram to draw.io formats:")
    print(f"  JSON: {json_output_file}")
    print(f"  XML: {xml_output_file}")
    print(f"Found {len(converter.nodes)} nodes and {len(converter.edges)} edges")

if __name__ == "__main__":
    main()
