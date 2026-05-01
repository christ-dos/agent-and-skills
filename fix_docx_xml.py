#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_docx_xml.py
Correction XML obligatoire après génération python-docx.
Usage:
  python fix_docx_xml.py [unpacked_dir]
Si aucun argument fourni, utilise le dossier 'unpacked' par défaut.
"""

import sys
import os
from lxml import etree
import re

BASE = sys.argv[1] if len(sys.argv) > 1 else 'unpacked'
settings_path = os.path.join(BASE, 'word', 'settings.xml')
doc_path = os.path.join(BASE, 'word', 'document.xml')

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
PPR_ORDER = [
    'pStyle','keepNext','keepLines','pageBreakBefore','framePr',
    'suppressLineNumbers','pBdr','shd','tabs','suppressAutoHyphens',
    'kinsoku','wordWrap','overflowPunct','topLinePunct','autoSpaceDE',
    'autoSpaceDN','bidi','adjustRightInd','snapToGrid','spacing','ind',
    'contextualSpacing','mirrorIndents','suppressOverlap','jc',
    'textDirection','textAlignment','textboxTightWrap','outlineLvl',
    'divId','cnfStyle','rPr','sectPr'
]


def ppr_sort_key(elem):
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    try:
        return PPR_ORDER.index(tag)
    except ValueError:
        return 999


# Fix settings.xml : zoom
try:
    with open(settings_path, 'r', encoding='utf-8') as f:
        s = f.read()
    s = re.sub(r'<w:zoom w:val="[^\"]*"/>', '<w:zoom w:percent="100"/>', s)
    with open(settings_path, 'w', encoding='utf-8') as f:
        f.write(s)
except FileNotFoundError:
    print(f"Warning: settings.xml not found at {settings_path}")

# Fix document.xml : ordre des enfants dans pPr + shd val manquant
try:
    tree = etree.parse(doc_path)
    root = tree.getroot()
    for pPr in root.iter(f'{{{W}}}pPr'):
        children = list(pPr)
        sorted_children = sorted(children, key=ppr_sort_key)
        if [c.tag for c in children] != [c.tag for c in sorted_children]:
            for child in children:
                pPr.remove(child)
            for child in sorted_children:
                pPr.append(child)
    for shd in root.iter(f'{{{W}}}shd'):
        if shd.get(f'{{{W}}}val') is None:
            shd.set(f'{{{W}}}val', 'clear')
    tree.write(doc_path, xml_declaration=True, encoding='UTF-8', standalone=True)
except FileNotFoundError:
    print(f"Warning: document.xml not found at {doc_path}")
except Exception as e:
    print(f"Error processing {doc_path}: {e}")
