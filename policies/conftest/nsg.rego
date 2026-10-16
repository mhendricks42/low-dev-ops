# Network security group rules on the project model.
package main

open_sources := {"*", "internet", "0.0.0.0/0", "::/0", "any"}

admin_ports := [22, 3389]

# A rule may use the singular or the plural field; both count.
values(rule, one, many) := {v | some v in array.concat([object.get(rule, one, "")], object.get(rule, many, []))} - {""}

opens_admin(port) if port == "*"

opens_admin(port) if to_number(port) in admin_ports

opens_admin(port) if {
	bounds := split(port, "-")
	count(bounds) == 2
	some admin in admin_ports
	to_number(bounds[0]) <= admin
	admin <= to_number(bounds[1])
}

deny contains {"id": sprintf("LDO_NSG_ADMIN_OPEN:%s", [key]), "resource": r.id, "msg": sprintf("%s: rule '%s' opens port %s to the internet", [r.id, key, port])} if {
	some r in input.resources
	r.module == "avm-res-network-networksecuritygroup"
	some key, rule in r.inputs.security_rules
	lower(rule.access) == "allow"
	lower(rule.direction) == "inbound"
	some source in values(rule, "source_address_prefix", "source_address_prefixes")
	lower(source) in open_sources
	some port in values(rule, "destination_port_range", "destination_port_ranges")
	opens_admin(port)
}
