# Network security group rules on the project model.
package main

open_sources := {"*", "Internet", "0.0.0.0/0", "Any"}

admin_ports := {"22", "3389", "*"}

deny contains {"id": sprintf("LDO_NSG_ADMIN_OPEN:%s", [key]), "resource": r.id, "msg": sprintf("%s: rule '%s' opens port %s to the internet", [r.id, key, rule.destination_port_range])} if {
	some r in input.resources
	r.module == "avm-res-network-networksecuritygroup"
	some key, rule in r.inputs.security_rules
	rule.access == "Allow"
	rule.direction == "Inbound"
	open_sources[rule.source_address_prefix]
	admin_ports[rule.destination_port_range]
}
