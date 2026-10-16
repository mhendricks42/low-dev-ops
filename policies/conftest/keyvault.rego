# Key Vault rules on the project model.
package main

# Purge protection is on by default in the module; any value other than true turns it off.
deny contains {"id": "LDO_KV_PURGE", "resource": r.id, "msg": sprintf("%s: key vault purge protection must stay on", [r.id])} if {
	some r in input.resources
	r.module == "avm-res-keyvault-vault"
	"purge_protection_enabled" in object.keys(r.inputs)
	r.inputs.purge_protection_enabled != true
}
