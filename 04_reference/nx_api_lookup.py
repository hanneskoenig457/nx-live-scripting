"""Search the private, version-matched NX .NET XML documentation (signatures may differ in Python)."""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
for item in ET.parse(root/'04_reference/NXOpen.xml').iter('member'):
    if any(key in item.attrib['name'] for key in sys.argv[1:]):
        print(item.attrib['name'])
        print(' '.join(''.join(item.itertext()).split())[:650])
