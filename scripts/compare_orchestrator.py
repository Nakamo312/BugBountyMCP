#!/usr/bin/env python3
"""Compare old orchestrator handlers with new pipeline nodes"""

# Old orchestrator handlers
OLD_HANDLERS = {
    "SERVICE_EVENTS": "handle_service_event",
    "SCAN_RESULTS_BATCH": "handle_scan_results_batch",
    "SUBDOMAIN_DISCOVERED": "handle_subdomain_discovered",
    "GAU_DISCOVERED": "handle_gau_discovered",
    "KATANA_RESULTS_BATCH": "handle_katana_results_batch",
    "HOST_DISCOVERED": "handle_host_discovered",
    "JS_FILES_DISCOVERED": "handle_js_files_discovered",
    "MANTRA_RESULTS_BATCH": "handle_mantra_results_batch",
    "FFUF_RESULTS_BATCH": "handle_ffuf_results_batch",
    "DNSX_BASIC_RESULTS_BATCH": "handle_dnsx_basic_results_batch",
    "DNSX_DEEP_RESULTS_BATCH": "handle_dnsx_deep_results_batch",
    "DNSX_PTR_RESULTS_BATCH": "handle_dnsx_ptr_results_batch",
    "DNSX_FILTERED_HOSTS": "handle_dnsx_filtered_hosts",
    "CNAME_DISCOVERED": "handle_cname_discovered",
    "SUBJACK_RESULTS_BATCH": "handle_subjack_results_batch",
    "ASNMAP_RESULTS_BATCH": "handle_asnmap_results_batch",
    "ASN_DISCOVERED": "handle_asn_discovered",
    "CIDR_DISCOVERED": "handle_cidr_discovered",
    "IPS_EXPANDED": "handle_ips_expanded",
    "NAABU_RESULTS_BATCH": "handle_naabu_results_batch",
}

# New pipeline nodes
NEW_NODES = {
    "SUBDOMAIN_DISCOVERED": "SubdomainDiscoveredNode",
    "DNSX_BASIC_RESULTS_BATCH": "DNSxBasicResultsNode",
    "DNSX_FILTERED_HOSTS": "DNSxFilteredHostsNode",
    "SCAN_RESULTS_BATCH": "HTTPXResultsNode",
    "HOST_DISCOVERED": "HostDiscoveredNode",
    "GAU_DISCOVERED": "GAUDiscoveredNode",
    "KATANA_RESULTS_BATCH": "KatanaResultsNode",
    "MANTRA_RESULTS_BATCH": "MantraResultsNode",
    "FFUF_RESULTS_BATCH": "FFUFResultsNode",
    "DNSX_DEEP_RESULTS_BATCH": "DNSxDeepResultsNode",
    "DNSX_PTR_RESULTS_BATCH": "DNSxPTRResultsNode",
    "JS_FILES_DISCOVERED": "JSFilesDiscoveredNode",
    "CNAME_DISCOVERED": "CNAMEDiscoveredNode",
    "SUBJACK_RESULTS_BATCH": "SubjackResultsNode",
    "ASNMAP_RESULTS_BATCH": "ASNMapResultsNode",
    "CIDR_DISCOVERED": "CIDRDiscoveredNode",
    "IPS_EXPANDED": "IPsExpandedNode",
    "NAABU_RESULTS_BATCH": "NaabuPortsNode",
    "PORTS_DISCOVERED": "PortsDiscoveredNode",
    "TLSX_RESULTS_BATCH": "TLSxCertNode",
    "CERT_SAN_DISCOVERED": "❌ MISSING - no handler in old code",
}

print("="*80)
print("COMPARISON: Old Orchestrator vs New Pipeline Nodes")
print("="*80)

print("\n🔴 MISSING in new nodes (handlers from old orchestrator):")
missing = set(OLD_HANDLERS.keys()) - set(NEW_NODES.keys())
for event in sorted(missing):
    print(f"   - {event} ({OLD_HANDLERS[event]})")

print("\n🟢 NEW in pipeline (not in old orchestrator):")
new = set(NEW_NODES.keys()) - set(OLD_HANDLERS.keys())
for event in sorted(new):
    print(f"   - {event} ({NEW_NODES[event]})")

print("\n✅ MATCHED (same events):")
matched = set(OLD_HANDLERS.keys()) & set(NEW_NODES.keys())
for event in sorted(matched):
    print(f"   - {event}")
    print(f"      Old: {OLD_HANDLERS[event]}")
    print(f"      New: {NEW_NODES[event]}")

print("\n" + "="*80)
print(f"Summary: {len(OLD_HANDLERS)} old handlers, {len(NEW_NODES)} new nodes")
print(f"Missing: {len(missing)}, New: {len(new)}, Matched: {len(matched)}")
print("="*80)
