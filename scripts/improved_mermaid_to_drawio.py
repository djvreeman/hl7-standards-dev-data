#!/usr/bin/env python3
"""
Improved Mermaid to Draw.io converter using mermaid-cli and better parsing
"""

import subprocess
import json
import xml.etree.ElementTree as ET
import base64
import zlib
import re
import tempfile
import os
from typing import Dict, List, Tuple, Any

class ImprovedMermaidToDrawIO:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.node_counter = 0
        self.edge_counter = 0
        
    def convert_with_mermaid_cli(self, mermaid_file: str) -> str:
        """Use mermaid-cli to generate SVG, then convert to draw.io"""
        try:
            # Generate SVG using mermaid-cli
            svg_file = mermaid_file.replace('.mermaid', '.svg')
            result = subprocess.run([
                'mmdc', '-i', mermaid_file, '-o', svg_file, '-t', 'dark'
            ], capture_output=True, text=True, check=True)
            
            print(f"Generated SVG: {svg_file}")
            return svg_file
            
        except subprocess.CalledProcessError as e:
            print(f"Error running mermaid-cli: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print("mermaid-cli not found. Please install with: npm install -g @mermaid-js/mermaid-cli")
            return None
    
    def parse_mermaid_advanced(self, mermaid_content: str) -> Dict[str, Any]:
        """Advanced Mermaid parsing that handles complex syntax better"""
        lines = mermaid_content.strip().split('\n')
        
        # Skip the first line (flowchart TD)
        content_lines = [line.strip() for line in lines[1:] if line.strip() and not line.strip().startswith('style')]
        
        # Parse all lines - nodes and edges
        for line in content_lines:
            if '-->' in line:
                self._parse_edge_advanced(line)
            elif ('[' in line and ']' in line) or ('{' in line and '}' in line):
                self._parse_node_advanced(line)
        
        # Parse styling
        style_lines = [line.strip() for line in lines if line.strip().startswith('style')]
        styles = self._parse_styles(style_lines)
        
        # Generate draw.io JSON
        return self._generate_drawio_json_improved(styles)
    
    def _parse_node_advanced(self, line: str):
        """Advanced node parsing that handles complex Mermaid syntax"""
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
                
                # Clean up node ID (remove special characters but keep meaningful ones)
                node_id = re.sub(r'[^a-zA-Z0-9_]', '', node_id)
                
                # Determine shape based on bracket type
                if bracket_type == 'curly':
                    shape = 'rhombus'
                else:
                    shape = 'rectangle'
                
                # Handle line breaks in content
                content = content.replace('<br/>', '\n')
                
                # Use content as the display label, not just the node ID
                display_label = content if content else node_id
                
                self.nodes[node_id] = {
                    'id': node_id,
                    'label': display_label,
                    'shape': shape
                }
    
    def _parse_edge_advanced(self, line: str):
        """Advanced edge parsing that handles complex Mermaid syntax"""
        if '-->' in line:
            parts = line.split('-->')
            if len(parts) >= 2:
                source_part = parts[0].strip()
                target_part = parts[1].strip()
                
                # Extract source node definition
                source_id, source_content, source_shape = self._extract_node_from_part_advanced(source_part)
                if source_id and source_id not in self.nodes:
                    display_label = source_content if source_content else source_id
                    self.nodes[source_id] = {
                        'id': source_id,
                        'label': display_label,
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
                target_id, target_content, target_shape = self._extract_node_from_part_advanced(target)
                if target_id and target_id not in self.nodes:
                    display_label = target_content if target_content else target_id
                    self.nodes[target_id] = {
                        'id': target_id,
                        'label': display_label,
                        'shape': target_shape
                    }
                
                self.edges.append({
                    'source': source_id,
                    'target': target_id,
                    'label': label
                })
    
    def _extract_node_from_part_advanced(self, part: str) -> Tuple[str, str, str]:
        """Advanced node extraction that handles complex syntax"""
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
    
    def _generate_drawio_json_improved(self, styles: Dict[str, Dict]) -> Dict[str, Any]:
        """Generate improved draw.io JSON format with better layout"""
        # Calculate layout positions using a better algorithm
        positions = self._calculate_positions_improved()
        
        # Create draw.io cells
        cells = []
        
        # Add nodes
        for node_id, node_data in self.nodes.items():
            pos = positions.get(node_id, (100, 100))
            style = styles.get(node_id, {})
            
            cell = {
                "id": f"node_{self.node_counter}",
                "value": node_data['label'],
                "style": self._get_node_style_improved(node_data['shape'], style),
                "vertex": 1,
                "parent": "1",
                "geometry": {
                    "x": pos[0],
                    "y": pos[1],
                    "width": 140,  # Wider for better text display
                    "height": 70   # Taller for better text display
                }
            }
            
            # Adjust size for decision nodes
            if node_data['shape'] == 'rhombus':
                cell["geometry"]["width"] = 120
                cell["geometry"]["height"] = 90
            
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
        
        return drawio_json
    
    def _calculate_positions_improved(self) -> Dict[str, Tuple[int, int]]:
        """Calculate node positions using a better layout algorithm"""
        positions = {}
        
        if not self.nodes:
            return positions
        
        # Create a graph structure
        graph = {node_id: [] for node_id in self.nodes.keys()}
        for edge in self.edges:
            if edge['source'] in graph and edge['target'] in graph:
                graph[edge['source']].append(edge['target'])
        
        # Find root nodes (nodes with no incoming edges)
        incoming = {node_id: 0 for node_id in self.nodes.keys()}
        for edge in self.edges:
            if edge['target'] in incoming:
                incoming[edge['target']] += 1
        
        root_nodes = [node_id for node_id, count in incoming.items() if count == 0]
        
        # Use BFS to assign layers
        layers = {}
        queue = [(node, 0) for node in root_nodes]
        visited = set()
        
        while queue:
            node, layer = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            layers[node] = layer
            
            for child in graph[node]:
                if child not in visited:
                    queue.append((child, layer + 1))
        
        # Assign positions within each layer
        layer_nodes = {}
        for node, layer in layers.items():
            if layer not in layer_nodes:
                layer_nodes[layer] = []
            layer_nodes[layer].append(node)
        
        # Position nodes
        for layer, nodes_in_layer in layer_nodes.items():
            for i, node in enumerate(nodes_in_layer):
                x = 200 + i * 250
                y = 100 + layer * 200
                positions[node] = (x, y)
        
        return positions
    
    def _get_node_style_improved(self, shape: str, style: Dict) -> str:
        """Generate improved draw.io style string for a node"""
        base_style = "rounded=1;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;"
        
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

def main():
    # Read the Mermaid file
    mermaid_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow.mermaid"
    
    with open(mermaid_file, 'r') as f:
        mermaid_content = f.read()
    
    # Test mermaid-cli approach
    converter = ImprovedMermaidToDrawIO()
    print("Testing mermaid-cli approach...")
    svg_file = converter.convert_with_mermaid_cli(mermaid_file)
    
    if svg_file:
        print(f"SVG generated: {svg_file}")
    
    # Test improved parsing approach
    print("\nTesting improved parsing approach...")
    result = converter.parse_mermaid_advanced(mermaid_content)
    
    # Save the improved JSON file
    output_file = "/Users/dvreeman/odrive/Encryptor/B2/Code/hl7-standards-dev-data/data/working/stu-expiration/stu_expiration_workflow_improved.json"
    
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Improved conversion saved: {output_file}")
    print(f"Found {len(converter.nodes)} nodes and {len(converter.edges)} edges")
    
    # Show some node examples
    print("\nNode examples:")
    for i, (node_id, node_data) in enumerate(list(converter.nodes.items())[:5]):
        print(f"  {node_id}: {node_data['label'][:50]}...")

if __name__ == "__main__":
    main()

