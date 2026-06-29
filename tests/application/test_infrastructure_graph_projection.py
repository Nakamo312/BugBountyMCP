from uuid import uuid4

from api.application.infrastructure_graph_projection import (
    CidrContainmentIndex,
    build_infrastructure_graph,
    ip_in_cidr,
)
from api.domain.models import (
    ASNModel,
    CIDRModel,
    HostIPModel,
    HostModel,
    IPAddressModel,
    ServiceModel,
)


def test_ip_in_cidr_handles_valid_and_invalid_inputs():
    assert ip_in_cidr("10.0.0.42", "10.0.0.0/24") is True
    assert ip_in_cidr("10.0.1.42", "10.0.0.0/24") is False
    assert ip_in_cidr("not-an-ip", "10.0.0.0/24") is False
    assert ip_in_cidr("10.0.0.42", "not-a-cidr") is False


def test_cidr_index_parses_networks_once_and_preserves_first_match_order():
    program_id = uuid4()
    broad = CIDRModel(program_id=program_id, cidr="10.0.0.0/8")
    narrow = CIDRModel(program_id=program_id, cidr="10.10.0.0/16")
    invalid = CIDRModel(program_id=program_id, cidr="invalid")
    v6 = CIDRModel(program_id=program_id, cidr="2001:db8::/32")

    index = CidrContainmentIndex.from_cidrs([broad, narrow, invalid, v6])

    assert index.first_container_for("10.10.1.5") == broad.id
    assert index.first_container_for("2001:db8::1") == v6.id
    assert index.first_container_for("not-an-ip") is None


def test_build_infrastructure_graph_keeps_existing_dto_shape():
    program_id = uuid4()
    asn = ASNModel(
        program_id=program_id,
        asn_number=64512,
        organization_name="Example Org",
        country_code="DE",
    )
    cidr = CIDRModel(program_id=program_id, cidr="10.0.0.0/24", asn_id=asn.id)
    ip = IPAddressModel(program_id=program_id, address="10.0.0.5")
    host = HostModel(program_id=program_id, host="api.example.test", cname=["edge.example.test"])
    host_ip = HostIPModel(host_id=host.id, ip_id=ip.id, source="dns")
    service = ServiceModel(ip_id=ip.id, scheme="https", port=443, technologies={"nginx": True})

    graph = build_infrastructure_graph(
        asns=[asn],
        cidrs=[cidr],
        ips=[ip],
        hosts=[host],
        host_ips=[host_ip],
        services=[service],
    )

    assert graph.stats == {
        "asn_count": 1,
        "cidr_count": 1,
        "ip_count": 1,
        "host_count": 1,
        "service_count": 1,
    }
    assert {node.type for node in graph.nodes} == {"asn", "cidr", "ip", "host", "service"}
    assert {(edge.source, edge.target, edge.type) for edge in graph.edges} == {
        (f"asn-{asn.id}", f"cidr-{cidr.id}", "contains"),
        (f"cidr-{cidr.id}", f"ip-{ip.id}", "contains"),
        (f"ip-{ip.id}", f"host-{host.id}", "resolves_to"),
        (f"host-{host.id}", f"svc-{service.id}", "runs"),
    }
