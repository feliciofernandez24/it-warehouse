# Phase 3A workbook analysis

Analysis date: 2026-11-13 (Asia/Tokyo). Source: local confidential workbook; no source upload, database connection, Django execution, importer, commit or push. Confirmed findings come from all worksheet XML and cached cell values, interpreted against repository models and migrations on develop. Proposed mappings and physical interpretations require owner approval.

## Scope and counts

All 15 worksheets are visible and inspected. There are 920 populated rows: 21 header rows, 897 candidate inventory rows and two number-only rows. Populated means at least one nonblank stored/cached value; formatted empty cells are excluded. Candidate does not mean approved or necessarily a unique physical unit. Blank gaps retain original row coordinates.

| Exact sheet name (quoted) | Purpose inferred from contents | Populated rows | Headers | Candidates | Number-only rows | Numeric Qty subtotal | Unit-bearing Qty |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 'Rack 1769' | Controllers and power supplies | 22 | 2 | 20 | none | 4 explicit units | none |
| 'Rack 845' | 2.5-inch disks/storage devices | 351 | 1 | 350 | none | none explicit | none |
| 'Rack 877' | Network modules/transceivers and quantity stock | 30 | 2 | 28 | none | 79 explicit units | none |
| 'Rack 871' | Controllers and miscellaneous quantity stock | 15 | 2 | 13 | none | 27 explicit units | none |
| 'Rack 856' | NICs, disks and power supplies | 64 | 3 | 61 | none | none explicit | none |
| 'Rack 807' | Larger disks/storage devices | 60 | 1 | 59 | none | none explicit | none |
| 'Rack 820' | RAM | 178 | 1 | 177 | none | none explicit | none |
| 'Rack 669' | Tool and battery sections | 19 | 2 | 15 | 3,25 | 1 explicit units | none |
| 'Rack 683' | Fans | 129 | 1 | 128 | none | none explicit | none |
| 'Rack 7' | Tools, connectors and casing | 10 | 1 | 9 | none | 6 explicit units | 2 Plastic, 2 Plastic, 1 Box, 3 Plastic, 5 plastic, 5 plastic |
| 'LAN Cable ' | Packaged cable | 3 | 1 | 2 | none | none explicit | 4 Box, 3 Box |
| 'Power Supply' | Boxed/above-rack power supplies | 8 | 1 | 7 | none | none explicit | none |
| 'Broken RAM' | Broken RAM handover | 3 | 1 | 2 | none | none explicit | none |
| 'Broken Controller' | Broken controller handover | 2 | 1 | 1 | none | none explicit | none |
| 'Broken Disk' | Broken disk handover | 26 | 1 | 25 | none | none explicit | none |

Numeric Qty totals are 117 across 22 rows; eight other Qty cells contain packaging units. The remaining 867 candidates have no Qty field/value. Never add inferred single units to explicit quantities as a confirmed stock total. Rack 877 row 37 alone states 73 units. Rack 7 has 17 Plastic/plastic packages and one Box in addition to six numeric units; LAN Cable has seven Box packages. Package contents and units are unconfirmed.

## Exact section headers

### 'Rack 1769'

Excel row 1: A=Column 1; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Qty; H=Assigned To; I=Location; J=Last Audit Date; K=Description.

Excel row 13: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Capacity; H=Assigned To; I=Location; J=Last Audit Date; K=Description.

### 'Rack 845'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Type; H=Capacity; I=Speed; J=Size; K=Assigned To; L=Location; M=Last Audit Date; N=Description.

### 'Rack 877'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Type; H=Capacity; I=Speed; J=Size; K=Assigned To; L=Location; M=Last Audit Date; N=Description.

Excel row 30: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Qty; H=Assigned To; I=Location; J=Last Audit Date; K=Description.

### 'Rack 871'

Excel row 1: A=Column 1; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Assigned To; H=Location; I=Last Audit Date; J=Description.

Excel row 13: A=Device Name; B=Manufacturer; C=Status; D=Qty; E=Condition; F=Assigned To; G=Location; H=Last Audit Date; I=Description.

### 'Rack 856'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Type; H=Capacity; I=Host Int; J=Ports; K=Assigned To; L=Location; M=Last Audit Date; N=Description.

Excel row 27: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Type; H=Capacity; I=Speed; J=Size; K=Assigned To; L=Location; M=Last Audit Date; N=Description.

Excel row 55: A=Device Category; B=Manufacturer; C=Serial Number; D=Status; E=Condition; F=Capacity; G=Assigned To; H=Location; I=Last Audit Date; J=Description.

### 'Rack 807'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Type; H=Capacity; I=Speed; J=Size; K=Assigned To; L=Location; M=Last Audit Date; N=Description.

### 'Rack 820'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Capacity; H=DDR; I=Assigned To; J=Location; K=Last Audit Date; L=Description.

### 'Rack 669'

Excel row 1: A=No; B=Device Name; C=Device Category; D=Status; E=Condition; F=Qty; G=Assigned To; H=Location; I=Last Audit Date; J=Description.

Excel row 10: A=No; B=Device Name; C=Device Category; D=Serial Number; E=Condition; F=Status; G=Capacity; H=Assigned To; I=Location; J=Last Audit Date; K=Description.

### 'Rack 683'

Excel row 1: A=Device Category; B=Manufacture; C=Device Name; D=Serial Number; E=Capacity; F=Type; G=Condition; H=Status; I=Assigned To; J=Location; K=Last Audit Date; L=Description.

### 'Rack 7'

Excel row 1: A=Device Category; B=Device Name; C=Status; D=Condition; E=Qty; F=Assigned To; G=Location; H=Last Audit Date; I=Description.

### 'LAN Cable '

Excel row 1: A=Device Name; B=Device Category; C=Type; D=Status; E=Condition; F=Qty; G=Assigned To; H=Location; I=Last Audit Date; J=Description.

### 'Power Supply'

Excel row 1: A=Device Category; B=Manufacturer; C=Serial Number; D=Status; E=Condition; F=Capacity; G=Assigned To; H=Location; I=Last Audit Date; J=Description.

### 'Broken RAM'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Capacity; H=DDR; I=Assigned To; J=Location; K=Last Audit Date; L=Description.

### 'Broken Controller'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Assigned To; H=Location; I=Last Audit Date; J=Description.

### 'Broken Disk'

Excel row 1: A=Device Name; B=Device Category; C=Manufacturer; D=Serial Number; E=Status; F=Condition; G=Type; H=Capacity; I=Speed; J=Size; K=Assigned To; L=Location; M=Last Audit Date; N=Description.

## Structural and formula findings

Rack 1769 switches Qty to Capacity at row 13; Rack 877 changes to Qty at row 30; Rack 871 row 13 changes both headers and column positions; Rack 856 changes at rows 27 and 55. Rack 669 row 10 swaps the Status/Condition order compared with its first section. A single-header parser would corrupt field interpretation. Rack 669 rows 3 and 25 contain only sequence numbers and need explicit ignored reasons.

Rack 807 contains five merged ranges A65:A66, B65:B66, C65:C66, D65:F65 and G65:G66 with no stored populated values there; they are layout artifacts, not five inventory records. There are 117 formulas, all location VLOOKUPs in Rack 683 J2:J118. Cached results are present; no formulas were executed or recalculated. Cache freshness cannot be established from this file. Preserve formula text and cache separately.

## Traceability and privacy

Every finding and future staged row uses exact worksheet_name and one-based excel_row_number, never a compacted dataframe index. Preserve the trailing space in 'LAN Cable ' in source identity. Store section header row and original coordinates in raw_values metadata. Confidential raw values stay in restricted staging/source storage, outside these reports and Git.
